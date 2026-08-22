"""Provide the framework-neutral asynchronous resource registry."""

import asyncio
import importlib
import inspect
from dataclasses import dataclass
from typing import (
    TYPE_CHECKING,
    Any,
    Awaitable,
    Callable,
    Dict,
    Generic,
    Iterable,
    List,
    Optional,
    Protocol,
    Tuple,
    Type,
    TypeVar,
    Union,
)

if TYPE_CHECKING:
    from logging import Logger

    from ..settings import SettingsInfo


T = TypeVar("T")
ResourceFactoryResult = Union[T, Awaitable[T]]
ResourceFactory = Callable[["ResourceContext"], ResourceFactoryResult[T]]
ResourceCloserResult = Union[None, Awaitable[None]]
ResourceCloser = Callable[[T], ResourceCloserResult]
ResourceFactoryTarget = Union[str, ResourceFactory[Any]]


class ResourceLifecycle(Protocol):
    """Describe lifecycle operations owned by the runtime registry."""

    async def start(self) -> None:
        """Start the registered resource."""
        ...

    async def close(self) -> None:
        """Close the registered resource."""
        ...


class Resource:
    """Base class for one user-defined runtime-scoped shared capability."""

    name = ""

    def __init__(self, context: "ResourceContext") -> None:
        """Bind the resource to immutable runtime construction context."""
        self.context = context
        self.settings = context.settings
        self.stop_event = context.stop_event
        self.resources = context.resources
        self.logger = context.logger

    @classmethod
    def from_runtime(cls, context: "ResourceContext") -> "Resource":
        """Construct a resource from the framework-owned runtime context."""
        return cls(context)

    async def start(self) -> None:
        """Initialize the shared capability before worker components run."""

    async def close(self) -> None:
        """Release the shared capability during runtime shutdown."""


ResourceTarget = Union[str, Type[Resource]]


@dataclass(frozen=True)
class ResourceSpec(Generic[T]):
    """Configure one user-defined resource factory and optional closer."""

    factory: ResourceFactoryTarget
    closer: Optional[ResourceCloser[T]] = None


@dataclass(frozen=True)
class ResourceContext:
    """Expose runtime-owned state to a user resource factory."""

    settings: Optional["SettingsInfo"]
    stop_event: Optional[asyncio.Event]
    resources: "ResourceService"
    logger: Optional["Logger"] = None


class _FactoryResource(Generic[T]):
    """Own one value constructed by a user callback."""

    def __init__(
        self,
        context: ResourceContext,
        factory: ResourceFactory[T],
        closer: Optional[ResourceCloser[T]],
    ) -> None:
        """Store callbacks without invoking user code during registration."""
        self._context = context
        self._factory = factory
        self._closer = closer
        self._value: Optional[T] = None
        self._started = False

    def get(self) -> T:
        """Return the started value or raise a lifecycle error."""
        if not self._started:
            raise RuntimeError("Resource factory has not been started")
        return self._value  # type: ignore[return-value]

    async def start(self) -> None:
        """Invoke the factory once and retain its resulting capability."""
        if self._started:
            return
        result = self._factory(self._context)
        if inspect.isawaitable(result):
            result = await result
        if result is None:
            raise RuntimeError("Resource factory returned None")
        self._value = result
        self._started = True

    async def close(self) -> None:
        """Close and forget the current callback-created value."""
        if not self._started:
            return
        value = self._value
        self._value = None
        self._started = False
        if value is None:
            return
        if self._closer is not None:
            result = self._closer(value)
            if inspect.isawaitable(result):
                await result
            return
        close = getattr(value, "close", None)
        if close is not None:
            result = close()
            if inspect.isawaitable(result):
                await result


@dataclass
class _ResourceEntry:
    """Bind a lifecycle owner to the capability exposed to consumers."""

    lifecycle: ResourceLifecycle
    value: Optional[object] = None
    value_getter: Optional[Callable[[], object]] = None

    def get(self) -> object:
        """Resolve the currently exposed resource value."""
        if self.value_getter is not None:
            return self.value_getter()
        return self.value


class ResourceService:
    """Own runtime resources and expose them to every mounted worker component."""

    _BUILTIN_NAMES = {
        "redis",
        "mysql",
        "postgres",
        "mongodb",
        "rabbitmq",
        "kafka",
    }

    def __init__(
        self,
        logger: Optional["Logger"] = None,
        *,
        settings: Optional["SettingsInfo"] = None,
        stop_event: Optional[asyncio.Event] = None,
    ) -> None:
        """Initialize a registry while preserving the legacy logger position."""
        self._logger = logger
        self.redis: Optional[object] = None
        self.mysql: Optional[object] = None
        self.postgres: Optional[object] = None
        self.mongodb: Optional[object] = None
        self.rabbitmq: Optional[object] = None
        self.kafka: Optional[object] = None
        self._entries: Dict[str, _ResourceEntry] = {}
        self._active_names: List[str] = []
        self._lifecycle_lock = asyncio.Lock()
        self._starting = False
        self._started = False
        self.context = ResourceContext(
            settings=settings,
            stop_event=stop_event,
            resources=self,
            logger=logger,
        )

    @property
    def started(self) -> bool:
        """Return whether every registered resource has started."""
        return self._started

    @property
    def names(self) -> Iterable[str]:
        """Return resource names in deterministic registration order."""
        return tuple(self._entries)

    def register(
        self,
        name: str,
        lifecycle: ResourceLifecycle,
        resource: object,
    ) -> None:
        """Register a preassembled capability and its lifecycle owner."""
        self._validate_registration(name)
        self._entries[name] = _ResourceEntry(lifecycle=lifecycle, value=resource)
        if name in self._BUILTIN_NAMES:
            setattr(self, name, resource)

    def register_factory(
        self,
        name: str,
        factory: ResourceFactoryTarget,
        closer: Optional[ResourceCloser[Any]] = None,
    ) -> None:
        """Register user construction and cleanup callbacks for one resource."""
        self._validate_registration(name)
        resolved_factory = self._resolve_factory(factory)
        lifecycle = _FactoryResource(self.context, resolved_factory, closer)
        self._entries[name] = _ResourceEntry(
            lifecycle=lifecycle,
            value_getter=lifecycle.get,
        )

    def register_spec(self, name: str, spec: ResourceSpec[Any]) -> None:
        """Register one declarative user resource specification."""
        self.register_factory(name, spec.factory, closer=spec.closer)

    def register_resource(self, resource: Resource) -> None:
        """Register one user-defined Resource instance by its declared name."""
        name = resource.name.strip()
        if not name:
            raise ValueError("Resource subclasses must declare a non-empty name")
        self.register(name, resource, resource)

    def register_classes(self, targets: Iterable[ResourceTarget]) -> None:
        """Resolve and register configured Resource subclasses in order."""
        for target in targets:
            resource_cls = self._resolve_resource_class(target)
            resource = resource_cls.from_runtime(self.context)
            if not isinstance(resource, Resource):
                raise TypeError("Resource.from_runtime() must return a Resource instance")
            self.register_resource(resource)

    def get(self, name: str, default: Optional[T] = None) -> Union[object, T]:
        """Return a registered resource or a caller-provided default."""
        entry = self._entries.get(name)
        if entry is None:
            return default
        try:
            return entry.get()
        except RuntimeError:
            return default

    def require(self, name: str) -> object:
        """Return one started resource or raise a descriptive error."""
        entry = self._entries.get(name)
        if entry is None:
            raise KeyError("Resource %r is not registered" % name)
        try:
            return entry.get()
        except RuntimeError as exc:
            raise RuntimeError("Resource %r is not started" % name) from exc

    def get_typed(
        self,
        name: str,
        resource_type: Type[T],
    ) -> Optional[T]:
        """Return an optional resource with an IDE-visible concrete type.

        Raises:
            TypeError: The registered resource does not match ``resource_type``.
        """
        resource = self.get(name)
        if resource is None:
            return None
        if not isinstance(resource, resource_type):
            raise TypeError(
                "Resource %r has type %s; expected %s"
                % (
                    name,
                    type(resource).__name__,
                    resource_type.__name__,
                )
            )
        return resource

    def require_typed(
        self,
        name: str,
        resource_type: Type[T],
    ) -> T:
        """Return a required resource with an IDE-visible concrete type.

        Raises:
            KeyError: No resource is registered under ``name``.
            RuntimeError: A callback-created resource has not started.
            TypeError: The registered resource does not match ``resource_type``.
        """
        resource = self.require(name)
        if not isinstance(resource, resource_type):
            raise TypeError(
                "Resource %r has type %s; expected %s"
                % (
                    name,
                    type(resource).__name__,
                    resource_type.__name__,
                )
            )
        return resource

    def __contains__(self, name: object) -> bool:
        """Return whether a resource name is registered."""
        return isinstance(name, str) and name in self._entries

    def __getitem__(self, name: str) -> object:
        """Return one required resource through mapping syntax."""
        return self.require(name)

    def __getattr__(self, name: str) -> object:
        """Expose custom resources with the same syntax as built-in resources."""
        entries = self.__dict__.get("_entries", {})
        entry = entries.get(name)
        if entry is None:
            raise AttributeError(
                "%s has no resource %r" % (type(self).__name__, name)
            )
        return entry.get()

    async def start(self) -> None:
        """Start resources in registration order and roll back on failure."""
        async with self._lifecycle_lock:
            if self._started:
                return
            self._starting = True
            started = []
            try:
                for name, entry in self._entries.items():
                    await entry.lifecycle.start()
                    started.append((name, entry))
                    self._active_names.append(name)
            except BaseException:
                await self._close_entries(started)
                self._active_names.clear()
                raise
            finally:
                self._starting = False
            self._started = True

    async def close(self) -> None:
        """Close every resource in reverse registration order."""
        async with self._lifecycle_lock:
            entries = [
                (name, self._entries[name])
                for name in self._active_names
            ]
            self._active_names.clear()
            try:
                await self._close_entries(entries)
            finally:
                self._started = False

    async def _close_entries(
        self,
        entries: Iterable[Tuple[str, _ResourceEntry]],
    ) -> None:
        """Close independent entries without hiding sibling failures."""
        reversed_entries = list(reversed(list(entries)))
        if not reversed_entries:
            return
        results = await asyncio.gather(
            *(entry.lifecycle.close() for _, entry in reversed_entries),
            return_exceptions=True,
        )
        cancellation = next(
            (
                result
                for result in results
                if isinstance(result, asyncio.CancelledError)
            ),
            None,
        )
        for (name, _), result in zip(reversed_entries, results):
            if isinstance(result, BaseException) and self._logger is not None:
                self._logger.error("Failed to close %s resource: %r", name, result)
        if cancellation is not None:
            raise cancellation

    def _validate_registration(self, name: str) -> None:
        """Reject late, empty, and duplicate registrations."""
        if self._started or self._starting:
            raise RuntimeError("Resources must be registered before runtime startup")
        if not isinstance(name, str) or not name.strip():
            raise ValueError("Resource name must be a non-empty string")
        if name != name.strip() or name.startswith("_"):
            raise ValueError("Resource name must not contain surrounding or private syntax")
        if hasattr(type(self), name):
            raise ValueError("Resource name %r conflicts with the registry API" % name)
        if name in self._entries:
            raise ValueError("Resource %s is already registered" % name)

    @staticmethod
    def _resolve_factory(factory: ResourceFactoryTarget) -> ResourceFactory[Any]:
        """Resolve a callable or dotted import path without importing vendors early."""
        if callable(factory):
            return factory
        module_name, separator, attribute = factory.rpartition(".")
        if not separator:
            raise ValueError("Resource factory path must include a module and attribute")
        resolved = getattr(importlib.import_module(module_name), attribute)
        if not callable(resolved):
            raise TypeError("Resource factory %r is not callable" % factory)
        return resolved

    @staticmethod
    def _resolve_resource_class(target: ResourceTarget) -> Type[Resource]:
        """Resolve and validate one configured Resource subclass."""
        resolved = target
        if isinstance(target, str):
            module_name, separator, attribute = target.rpartition(".")
            if not separator:
                raise ValueError("Resource path must include a module and class")
            resolved = getattr(importlib.import_module(module_name), attribute)
        if not isinstance(resolved, type) or not issubclass(resolved, Resource):
            raise TypeError("Configured resource must inherit scrapy_cffi.runtime.Resource")
        return resolved


__all__ = [
    "ResourceCloser",
    "ResourceContext",
    "Resource",
    "ResourceFactory",
    "ResourceFactoryTarget",
    "ResourceLifecycle",
    "ResourceService",
    "ResourceSpec",
    "ResourceTarget",
]
