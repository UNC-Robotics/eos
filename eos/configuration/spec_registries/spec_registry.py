from typing import Generic, TypeVar
from pathlib import Path

from eos.utils.singleton import Singleton

T = TypeVar("T")  # Specification type
C = TypeVar("C")  # Configuration type


class SpecRegistry(Generic[T, C], metaclass=Singleton):
    """
    A generic registry for storing and retrieving specifications.
    """

    def __init__(
        self,
        specifications: dict[str, T],
        dirs_to_types: dict[str, str],
    ):
        self._specifications = specifications.copy()
        self._dirs_to_types = dirs_to_types.copy()

    def get_all_specs(self) -> dict[str, T]:
        return self._specifications

    def get_spec_by_type(self, spec_type: str) -> T | None:
        return self._specifications.get(spec_type)

    def get_spec_by_config(self, config: C) -> T | None:
        return self._specifications.get(config.type)

    def get_spec_by_dir(self, dir_path: str) -> str:
        return self._dirs_to_types.get(dir_path)

    def get_dir_by_type(self, spec_type: str) -> Path | None:
        """
        Return the directory key (including package prefix) for the given type,
        if present in this registry. Keys are stored as Path-like objects.
        """
        for dir_key, type_name in self._dirs_to_types.items():
            if type_name == spec_type:
                # dir_key may be a Path or string; normalize to Path
                return Path(dir_key)
        return None

    def spec_exists_by_config(self, config: C) -> bool:
        return config.type in self._specifications

    def spec_exists_by_type(self, spec_type: str) -> bool:
        return spec_type in self._specifications
