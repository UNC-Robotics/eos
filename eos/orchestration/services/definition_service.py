from sqlalchemy import select

from eos.configuration.entities.definition import Definition, DefinitionModel
from eos.database.abstract_sql_db_interface import AsyncDbSession


class DefinitionService:
    """Service for querying definitions from the database."""

    async def get_definitions(self, db: AsyncDbSession, def_type: str | None = None) -> list[Definition]:
        """Get all definitions, optionally filtered by type.

        :param db: Database session
        :param def_type: Optional type filter (task, device, lab, experiment)
        :return: List of definitions
        """
        stmt = select(DefinitionModel).where(DefinitionModel.type == def_type) if def_type else select(DefinitionModel)
        result = await db.execute(stmt)
        models = result.scalars().all()

        return [Definition.model_validate(model) for model in models]

    async def get_definition(self, db: AsyncDbSession, def_type: str, name: str) -> Definition | None:
        """Get a single definition by type and name.

        :param db: Database session
        :param def_type: Definition type (task, device, lab, experiment)
        :param name: Definition name
        :return: Definition if found, None otherwise
        """
        stmt = select(DefinitionModel).where(
            DefinitionModel.type == def_type,
            DefinitionModel.name == name,
        )

        result = await db.execute(stmt)
        model = result.scalar_one_or_none()

        if model is None:
            return None

        return Definition.model_validate(model)
