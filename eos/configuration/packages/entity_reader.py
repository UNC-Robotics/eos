import os
from pathlib import Path
from typing import Any, TypeVar

import jinja2
import yaml
from pydantic import BaseModel

from eos.configuration.exceptions import EosConfigurationError
from eos.configuration.packages.entities import EntityType, EntityConfigType, ENTITY_INFO
from eos.logging.logger import log

T = TypeVar("T", bound=BaseModel)


class EntityReader:
    """
    Reads and parses entity configurations (labs, experiments, tasks, devices) from files.
    """

    def __init__(self, user_dir: Path):
        self._user_dir = user_dir

    def read_entity(self, file_path: str, entity_type: EntityType) -> EntityConfigType:
        return self._read_config(file_path, ENTITY_INFO[entity_type].config_type, f"{entity_type.name}")

    def read_all_entities(
        self, base_dir: str, entity_type: EntityType
    ) -> tuple[dict[str, EntityConfigType], dict[Path, str]]:
        entity_info = ENTITY_INFO[entity_type]
        configs = {}
        dirs_to_types = {}

        for root, _, files in os.walk(base_dir):
            if entity_info.config_file_name not in files:
                continue

            entity_subdir = Path(root).relative_to(base_dir)
            config_file_path = Path(root) / entity_info.config_file_name

            try:
                structured_config = self.read_entity(str(config_file_path), entity_type)
                entity_type_name = structured_config.type
                configs[entity_type_name] = structured_config
                dirs_to_types[entity_subdir] = entity_type_name

                log.debug(
                    f"Loaded {entity_type.name.capitalize()} specification from directory '{entity_subdir}' of type "
                    f"'{entity_type_name}'"
                )
                log.debug(f"{entity_type.name.capitalize()} configuration '{entity_type_name}': {structured_config}")
            except EosConfigurationError as e:
                log.error(f"Error loading {entity_type.name.lower()} configuration from '{config_file_path}': {e}")
                raise

        return configs, dirs_to_types

    def _read_config(self, file_path: str, config_type: type[EntityConfigType], config_name: str) -> EntityConfigType:
        try:
            config_data = self._render_jinja_yaml(file_path)
            return self._parse_yaml(yaml.dump(config_data), config_type)
        except OSError as e:
            raise EosConfigurationError(f"Error reading configuration file '{file_path}': {e!s}") from e
        except jinja2.exceptions.TemplateError as e:
            raise EosConfigurationError(f"Error in Jinja2 template for '{config_name.lower()}': {e!s}") from e
        except Exception as e:
            raise EosConfigurationError(f"Error processing {config_name.lower()} configuration: {e!s}") from e

    def _render_jinja_yaml(self, file_path: str) -> dict[str, Any]:
        """
        Render a YAML file with Jinja2 templating.
        """
        try:
            with Path(file_path).open() as f:
                raw_content = f.read()
        except OSError as e:
            raise EosConfigurationError(f"Error reading file '{file_path}': {e}") from e

        try:
            env = jinja2.Environment(
                loader=jinja2.FileSystemLoader(Path(self._user_dir)),  # user directory
                undefined=jinja2.StrictUndefined,
                autoescape=True,
            )

            template = env.from_string(raw_content)
            rendered_content = template.render()

            return yaml.safe_load(rendered_content)
        except yaml.YAMLError as e:
            raise EosConfigurationError(f"Error parsing YAML in {file_path}: {e}") from e
        except jinja2.exceptions.TemplateError as e:
            raise EosConfigurationError(f"Error in Jinja2 template processing: {e}") from e

    @staticmethod
    def _parse_yaml(yaml_string: str, model_class: type[T]) -> T:
        """
        Parse a YAML string into a Pydantic model instance.

        Args:
            yaml_string: YAML content as a string
            model_class: The Pydantic model class to parse into

        Returns:
            An instance of the provided Pydantic model class

        Raises:
            ValidationError: If the YAML data doesn't match the model schema
            yaml.YAMLError: If the YAML string is invalid
        """
        yaml_data = yaml.safe_load(yaml_string)
        return model_class.model_validate(yaml_data)
