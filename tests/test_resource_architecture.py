"""Verify infra, repository, service, and composition boundaries."""

import asyncio
from pathlib import Path
from unittest.mock import patch

from redis.exceptions import ConnectionError as RedisConnectionError

from scrapy_cffi import Resource
from scrapy_cffi.composition import build_resource_service
from scrapy_cffi.config import RedisInfo
from scrapy_cffi.infra.redis import RedisClient
from scrapy_cffi.settings import SettingsInfo


class FakeRedisClient:
    """Provide the Redis transport shape used by the composition test."""

    redis_mode = "single"
    cluster_nodes = []

    def __init__(self, available: bool) -> None:
        """Configure whether this fake client accepts operations."""
        self.available = available
        self.closed = False

    async def connect(self) -> None:
        """Initialize the fake transport."""

    async def close(self) -> None:
        """Record transport closure."""
        self.closed = True

    async def rpush(self, key: str, value: bytes) -> int:
        """Fail the first generation and accept the replacement."""
        del key, value
        if not self.available:
            raise RedisConnectionError("redis unavailable")
        return 1


class ArtifactResource(Resource):
    """Provide a test capability registered like a worker component."""

    name = "artifacts"
    events = []

    async def start(self) -> None:
        """Record runtime-owned startup."""
        self.events.append("start:artifacts")

    async def put(self, key: str, data: bytes) -> str:
        """Return a stable artifact reference for test consumers."""
        return "artifact://%s/%s" % (key, len(data))

    async def close(self) -> None:
        """Record runtime-owned shutdown."""
        self.events.append("close:artifacts")


def test_composition_replaces_failed_redis_client_above_infra():
    """A repository retry replaces its client through the service-owned slot."""

    async def run() -> None:
        """Exercise the asynchronous replacement flow."""
        clients = []

        def factory(info: RedisInfo) -> FakeRedisClient:
            """Return a failing first client and a healthy replacement."""
            del info
            client = FakeRedisClient(available=bool(clients))
            clients.append(client)
            return client

        settings = SettingsInfo(
            REDIS_INFO=RedisInfo(URL="redis://127.0.0.1:6379/0"),
            INFRA_RETRY_ATTEMPTS=2,
            INFRA_RETRY_DELAY=0,
        )
        with patch.object(RedisClient, "from_info", side_effect=factory):
            resources = build_resource_service(settings, asyncio.Event())
            await resources.start()
            if resources.redis is None:
                raise AssertionError("Redis repository was not assembled")
            assert await resources.redis.rpush("requests", b"payload") == 1
            assert len(clients) == 2
            assert clients[0].closed is True
            await resources.close()
            assert clients[1].closed is True

    asyncio.run(run())


def test_infrastructure_has_no_retry_or_upper_layer_imports():
    """Concrete infrastructure must remain one-shot and dependency-inward."""
    package_root = Path(__file__).resolve().parents[1] / "scrapy_cffi"
    infra_files = list((package_root / "infra").rglob("*.py"))
    assert infra_files
    for path in infra_files:
        source = path.read_text(encoding="utf-8")
        assert "utils.reconnect" not in source
        assert "service.resilience" not in source
        assert "_reconnect_controller" not in source
        assert "def _reconnect" not in source


def test_legacy_database_and_mq_implementation_modules_are_removed():
    """The removed Manager packages must not regain implementation files."""
    package_root = Path(__file__).resolve().parents[1] / "scrapy_cffi"
    for legacy_name in ("databases", "mq"):
        legacy = package_root / legacy_name
        assert not list(legacy.glob("*.py"))


def test_all_user_components_share_crawler_resource_service() -> None:
    """Spider, pipeline, interceptor, and extension see one owned registry."""
    from types import SimpleNamespace

    from scrapy_cffi.extensions import Extension
    from scrapy_cffi.interceptors import DownloadInterceptor
    from scrapy_cffi.pipelines import Pipeline
    from scrapy_cffi.spiders import Spider

    class Sessions:
        """Provide the session methods required by component constructors."""

        register_sessions_batch = staticmethod(lambda *args, **kwargs: "group")
        get_session_cookies = staticmethod(lambda *args, **kwargs: {})
        configure_rate_limit = staticmethod(lambda *args, **kwargs: None)
        acquire = staticmethod(lambda *args, **kwargs: None)
        release = staticmethod(lambda *args, **kwargs: None)
        get_or_create_session = staticmethod(lambda *args, **kwargs: None)

    class Signals:
        """Provide the signal methods required by component constructors."""

        send = staticmethod(lambda *args, **kwargs: None)
        connect = staticmethod(lambda *args, **kwargs: None)

    async def run() -> None:
        """Construct each user component around one real registry."""
        settings = SettingsInfo(
            ROBOTSTXT_OBEY=False,
            RESOURCES_PATH=[ArtifactResource],
        )
        resources = build_resource_service(settings, asyncio.Event())
        await resources.start()
        scheduler = SimpleNamespace()
        crawler = SimpleNamespace(
            settings=settings,
            run_py_dir=Path.cwd(),
            stop_event=asyncio.Event(),
            resources=resources,
            sessions=Sessions(),
            sessions_lock=asyncio.Lock(),
            signalManager=Signals(),
            scheduler=scheduler,
        )

        spider = Spider.from_crawler(crawler, scheduler=scheduler)
        pipeline = Pipeline.from_crawler(crawler)
        interceptor = DownloadInterceptor.from_crawler(crawler)
        extension = Extension.from_crawler(hooks=object(), resources=resources)

        assert spider.resources is resources
        assert pipeline.resources is resources
        assert interceptor.resources is resources
        assert extension.resources is resources
        assert spider.resources.artifacts is resources.artifacts
        assert pipeline.resources.artifacts is resources.artifacts
        assert interceptor.resources.artifacts is resources.artifacts
        assert extension.resources.artifacts is resources.artifacts
        await resources.close()

    asyncio.run(run())


def test_resource_startup_failure_rolls_back_only_started_resources() -> None:
    """A failed Resource start closes earlier dependencies in reverse order."""
    events = []

    class StartedResource(Resource):
        """Provide one successfully started dependency."""

        name = "dependency"

        async def start(self) -> None:
            """Record successful startup."""
            events.append("start:dependency")

        async def close(self) -> None:
            """Record rollback closure."""
            events.append("close:dependency")

    class BrokenResource(Resource):
        """Fail while the registry is starting."""

        name = "broken"

        async def start(self) -> None:
            """Raise a deterministic startup error."""
            events.append("start:broken")
            raise RuntimeError("broken startup")

        async def close(self) -> None:
            """Must not run because startup never completed."""
            events.append("close:broken")

    async def run() -> None:
        """Start the registry and observe its rollback behavior."""
        settings = SettingsInfo(
            RESOURCES_PATH=[StartedResource, BrokenResource],
        )
        resources = build_resource_service(settings, asyncio.Event())
        try:
            await resources.start()
        except RuntimeError as exc:
            assert str(exc) == "broken startup"
        else:
            raise AssertionError("broken Resource startup unexpectedly succeeded")
        assert resources.started is False
        await resources.close()

    asyncio.run(run())
    assert events == ["start:dependency", "start:broken", "close:dependency"]


def test_local_filesystem_resource_supports_async_artifact_io(tmp_path: Path) -> None:
    """A Resource can adapt blocking local storage with asyncio.to_thread."""

    class LocalStorageResource(Resource):
        """Provide async project-local artifact storage for the test runtime."""

        name = "local_storage"
        root = tmp_path / "artifacts"

        async def start(self) -> None:
            """Create the test-owned storage directory off the event loop."""
            await asyncio.to_thread(self.root.mkdir, parents=True, exist_ok=True)

        async def write(self, key: str, data: bytes) -> str:
            """Write one bounded artifact and return its resource key."""
            path = self.root / key
            await asyncio.to_thread(path.parent.mkdir, parents=True, exist_ok=True)
            await asyncio.to_thread(path.write_bytes, data)
            return key

        async def read(self, key: str) -> bytes:
            """Read one artifact without blocking the crawler event loop."""
            return await asyncio.to_thread((self.root / key).read_bytes)

    async def run() -> None:
        """Use the configured local resource through the shared registry."""
        settings = SettingsInfo(RESOURCES_PATH=[LocalStorageResource])
        resources = build_resource_service(settings, asyncio.Event())
        await resources.start()
        storage = resources.require("local_storage")
        assert isinstance(storage, LocalStorageResource)
        assert await storage.write("responses/1.bin", b"payload") == "responses/1.bin"
        assert await storage.read("responses/1.bin") == b"payload"
        await resources.close()

    asyncio.run(run())


def test_configured_resource_class_is_started_shared_and_closed() -> None:
    """A configured Resource becomes one runtime-scoped shared capability."""

    async def run() -> None:
        """Exercise one configured Resource through the public registry API."""
        ArtifactResource.events = []
        settings = SettingsInfo(RESOURCES_PATH=[ArtifactResource])
        resources = build_resource_service(settings, asyncio.Event())

        assert "artifacts" in resources
        assert resources.get("artifacts") is resources.require("artifacts")
        artifact_resource = resources.require("artifacts")
        assert isinstance(artifact_resource, ArtifactResource)
        assert resources.artifacts is artifact_resource
        assert resources.get_typed("artifacts", ArtifactResource) is artifact_resource
        assert resources.require_typed("artifacts", ArtifactResource) is artifact_resource
        assert resources.get_typed("missing", ArtifactResource) is None

        await resources.start()
        assert await artifact_resource.put("page", b"body") == "artifact://page/4"
        assert resources["artifacts"] is artifact_resource
        assert ArtifactResource.events == ["start:artifacts"]

        await resources.close()
        assert ArtifactResource.events == ["start:artifacts", "close:artifacts"]

    asyncio.run(run())


def test_typed_resource_access_rejects_the_wrong_concrete_class() -> None:
    """Typed getters fail explicitly instead of returning a false annotation."""

    class OtherResource(Resource):
        """Represent a different application capability."""

        name = "other"

    async def run() -> None:
        """Exercise optional and required typed mismatch behavior."""
        settings = SettingsInfo(RESOURCES_PATH=[ArtifactResource])
        resources = build_resource_service(settings, asyncio.Event())
        await resources.start()
        for getter in (resources.get_typed, resources.require_typed):
            try:
                getter("artifacts", OtherResource)
            except TypeError as exc:
                assert "ArtifactResource" in str(exc)
                assert "OtherResource" in str(exc)
            else:
                raise AssertionError("typed resource mismatch was accepted")
        await resources.close()

    asyncio.run(run())


def test_resource_class_dotted_path_remains_configuration_compatible() -> None:
    """A dotted class path resolves to the same Resource extension contract."""

    async def run() -> None:
        """Build and start a registry from an importable Resource path."""
        resource_path = "%s.%s" % (
            ArtifactResource.__module__,
            ArtifactResource.__qualname__,
        )
        settings = SettingsInfo(RESOURCES_PATH=[resource_path])
        resources = build_resource_service(settings, asyncio.Event())
        await resources.start()
        assert isinstance(resources.require("artifacts"), ArtifactResource)
        await resources.close()

    asyncio.run(run())


def test_resource_registration_order_controls_start_and_reverse_close() -> None:
    """Resource dependencies see deterministic startup and shutdown ordering."""
    events = []

    class FirstResource(Resource):
        """Record the first lifecycle."""

        name = "first"

        async def start(self) -> None:
            """Record first startup."""
            events.append("start:first")

        async def close(self) -> None:
            """Record first shutdown."""
            events.append("close:first")

    class SecondResource(Resource):
        """Record the dependent lifecycle."""

        name = "second"

        async def start(self) -> None:
            """Require the earlier resource before starting."""
            assert isinstance(self.resources.require("first"), FirstResource)
            events.append("start:second")

        async def close(self) -> None:
            """Record dependent shutdown."""
            events.append("close:second")

    async def run() -> None:
        """Start and close two ordered Resource classes."""
        settings = SettingsInfo(RESOURCES_PATH=[FirstResource, SecondResource])
        resources = build_resource_service(settings, asyncio.Event())
        await resources.start()
        await resources.close()

    asyncio.run(run())
    assert events == [
        "start:first",
        "start:second",
        "close:second",
        "close:first",
    ]


def test_resource_registration_rejects_invalid_duplicate_and_late_classes() -> None:
    """Registry construction errors fail before user work can start."""

    class DuplicateResource(Resource):
        """Collide with the artifact resource name."""

        name = "artifacts"

    async def run() -> None:
        """Exercise duplicate and late registration failures."""
        settings = SettingsInfo(RESOURCES_PATH=[ArtifactResource])
        resources = build_resource_service(settings, asyncio.Event())
        try:
            resources.register_resource(DuplicateResource(resources.context))
        except ValueError as exc:
            assert "already registered" in str(exc)
        else:
            raise AssertionError("duplicate resource registration was accepted")

        await resources.start()
        try:
            resources.register_resource(DuplicateResource(resources.context))
        except RuntimeError as exc:
            assert "before runtime startup" in str(exc)
        else:
            raise AssertionError("late resource registration was accepted")
        await resources.close()

    asyncio.run(run())
