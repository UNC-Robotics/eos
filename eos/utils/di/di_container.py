from typing import Any, TypeVar, get_type_hints
from collections.abc import Callable
from functools import wraps
import inspect
from weakref import WeakKeyDictionary

T = TypeVar("T")


class DependencyError(Exception):
    """Base class for dependency injection errors."""


class DIContainer:
    """Dependency injection container."""

    def __init__(self):
        # Maps interface types to a tuple: (is_instance, value)
        # - If is_instance is True, value is the concrete instance.
        # - Otherwise, value is a factory callable that creates the instance.
        self._registry: dict[type, tuple[bool, Any]] = {}

    def register(self, interface_type: type[T], instance: T) -> None:
        """Register a concrete instance for the given interface type."""
        if not isinstance(instance, interface_type):
            raise DependencyError(f"Type mismatch: {type(instance).__name__} ≠ {interface_type.__name__}")

        self._registry[interface_type] = (True, instance)

    def register_factory(self, interface_type: type[T], factory: Callable[[], T]) -> None:
        """Register a factory function that creates instances of the given interface type."""
        if not callable(factory):
            raise DependencyError("Factory must be callable")

        self._registry[interface_type] = (False, factory)

    def get(self, interface_type: type[T]) -> T | None:
        """Retrieve an instance of the given interface type, instantiating via a factory if necessary."""
        entry = self._registry.get(interface_type)
        if entry is None:
            return None

        is_instance, value = entry
        if is_instance:
            return value

        # Instantiate using the factory and cache the result.
        instance = value()
        if not isinstance(instance, interface_type):
            raise DependencyError(
                f"Factory produced invalid type: {type(instance).__name__} ≠ {interface_type.__name__}"
            )
        self._registry[interface_type] = (True, instance)
        return instance

    def remove(self, interface_type: type) -> None:
        """Remove the registration for the given interface type."""
        self._registry.pop(interface_type, None)

    def clear(self) -> None:
        """Clear all registrations."""
        self._registry.clear()


class DICache:
    """Cache for dependency injection metadata."""

    def __init__(self):
        self._type_hints: WeakKeyDictionary[Callable, dict[str, type]] = WeakKeyDictionary()
        self._injectable_params: WeakKeyDictionary[Callable, set[str]] = WeakKeyDictionary()

    def get_hints(self, func: Callable) -> dict[str, type]:
        """Retrieve and cache the type hints for a function."""
        if func not in self._type_hints:
            hints = get_type_hints(func)
            hints.pop("return", None)
            self._type_hints[func] = hints
        return self._type_hints[func]

    def get_injectable_params(self, func: Callable) -> set[str]:
        """
        Retrieve and cache the names of parameters that are injectable,
        excluding 'self', 'cls', and parameters with default values.
        """
        if func not in self._injectable_params:
            sig = inspect.signature(func)
            params = {
                name
                for name, param in sig.parameters.items()
                if name not in ("self", "cls") and param.default == inspect.Parameter.empty
            }
            self._injectable_params[func] = params
        return self._injectable_params[func]


_di_container = DIContainer()
_di_injection_cache = DICache()


def inject(func: Callable) -> Callable:
    """
    Dependency injection decorator that automatically injects dependencies based on type hints.

    Usage:
        @inject
        def my_func(service: Service): ...
    """

    @wraps(func)
    def wrapper(*args, **kwargs) -> Any:
        hints = _di_injection_cache.get_hints(func)
        injectable = _di_injection_cache.get_injectable_params(func)
        for param in injectable - kwargs.keys():
            if (expected_type := hints.get(param)) and ((instance := _di_container.get(expected_type)) is not None):
                kwargs[param] = instance
        return func(*args, **kwargs)

    return wrapper


def get_di_container() -> DIContainer:
    """Get the global container instance."""
    return _di_container
