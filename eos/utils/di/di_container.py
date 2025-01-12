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
        self._registry: dict[type, tuple[bool, Any]] = {}  # (is_instance, value)

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
        """Get an instance of the specified type or None if not registered."""
        try:
            is_instance, value = self._registry[interface_type]
            if is_instance:
                return value

            # Lazy instantiation for factories
            instance = value()
            if not isinstance(instance, interface_type):
                raise DependencyError(
                    f"Factory produced invalid type: {type(instance).__name__} ≠ {interface_type.__name__}"
                )
            # Cache the instance
            self._registry[interface_type] = (True, instance)
            return instance

        except KeyError:
            return None
        except Exception as e:
            if isinstance(e, DependencyError):
                raise
            raise DependencyError(f"Factory creation failed: {e!s}") from e

    def remove(self, interface_type: type) -> None:
        """Remove a registration."""
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
        """Get cached type hints."""
        if func not in self._type_hints:
            hints = get_type_hints(func)
            hints.pop("return", None)
            self._type_hints[func] = hints
        return self._type_hints[func]

    def get_injectable_params(self, func: Callable) -> set[str]:
        """Get cached injectable parameters."""
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


def inject(*types: type[Any]) -> Callable:
    """Optimized dependency injection decorator that ignores missing dependencies."""
    # Pre-compute parameter names
    param_names = {t: t.__name__.lower() for t in types}

    def decorator(func) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs) -> Any:
            # Inject only missing dependencies if they are registered
            for type_, name in param_names.items():
                if name not in kwargs and (instance := _di_container.get(type_)):
                    kwargs[name] = instance
            return func(*args, **kwargs)

        return wrapper

    return decorator


def inject_all(func) -> Callable:
    """Optimized automatic dependency injection decorator that ignores missing dependencies."""

    @wraps(func)
    def wrapper(*args, **kwargs) -> Any:
        hints = _di_injection_cache.get_hints(func)
        params = _di_injection_cache.get_injectable_params(func)

        # Inject only for parameters that need it and have registered dependencies
        for name in params - set(kwargs):
            if (type_ := hints.get(name)) and (instance := _di_container.get(type_)):
                kwargs[name] = instance

        return func(*args, **kwargs)

    return wrapper


def get_di_container() -> DIContainer:
    """Get the global container instance."""
    return _di_container
