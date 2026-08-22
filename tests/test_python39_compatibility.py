"""Verify the declared Python 3.9 runtime and compatibility contracts."""

import ast
import asyncio
import tempfile
from pathlib import Path
from types import SimpleNamespace

import toml

from scrapy_cffi import Resource


ROOT = Path(__file__).resolve().parents[1]


class CompatibilityResource(Resource):
    """Provide an importable Resource for settings serialization tests."""

    name = "compatibility"


def _annotation_nodes(tree):
    """Yield every annotation node from a parsed Python syntax tree."""
    for node in ast.walk(tree):
        if isinstance(node, ast.AnnAssign):
            yield node.annotation
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            arguments = node.args.posonlyargs + node.args.args + node.args.kwonlyargs
            for argument in arguments:
                if argument.annotation:
                    yield argument.annotation
            if node.args.vararg and node.args.vararg.annotation:
                yield node.args.vararg.annotation
            if node.args.kwarg and node.args.kwarg.annotation:
                yield node.args.kwarg.annotation
            if node.returns:
                yield node.returns


def test_package_source_uses_python39_compatible_syntax_and_annotations():
    """All package modules must parse on 3.9 and avoid PEP 604 unions."""
    incompatible_unions = []
    for path in (ROOT / "scrapy_cffi").rglob("*.py"):
        source = path.read_text(encoding="utf-8-sig")
        tree = ast.parse(source, filename=str(path), feature_version=(3, 9))
        for annotation in _annotation_nodes(tree):
            for child in ast.walk(annotation):
                if isinstance(child, ast.BinOp) and isinstance(child.op, ast.BitOr):
                    incompatible_unions.append((path, child.lineno))

    assert incompatible_unions == []


def test_package_metadata_declares_real_python_minimum():
    """Package metadata must retain the qualified Python and optional extras."""
    project = toml.loads(
        (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    )["project"]
    assert project["requires-python"] == ">=3.9"
    assert "curl_cffi>=0.7.4,<0.14; python_version < '3.10'" in project["dependencies"]
    assert "curl_cffi>=0.7.4,<0.16; python_version >= '3.10'" in project["dependencies"]
    assert "python-dotenv" in project["dependencies"]
    assert "dotenv" not in project["dependencies"]
    extras = project["optional-dependencies"]
    assert "aio-pika>=9.0" in extras["rabbitmq"]
    assert "aiokafka>=0.8.1" in extras["kafka"]
    assert "asyncmy>=0.2" in extras["mysql"]
    assert "pyblackboxprotobuf>=0.1.0,<0.2" in extras["protobuf"]
    assert "pytest>=8.0" in extras["verification"]
    assert "fastapi>=0.115" in extras["verification"]
    assert "uvicorn>=0.30" in extras["verification"]
    assert "websockets>=15.0,<16" in extras["verification"]


def test_runtime_and_package_versions_match():
    """The importable version must match the distribution metadata."""
    from scrapy_cffi import __version__

    project = toml.loads(
        (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    )["project"]
    assert __version__ == project["version"]


def test_interceptor_none_response_continues_and_unhandled_exception_survives():
    """Compatibility handling must preserve empty middleware responses."""
    from scrapy_cffi.core.downloader.internet import Request, Response
    from scrapy_cffi.interceptors.chains import (
        ChainNextEnum,
        InterruptibleChainManager,
    )

    class Middleware:
        """Provide no-op response and exception interceptor hooks."""

        async def response_intercept(self, **kwargs):
            """Leave a successful response unchanged."""
            return None

        async def exception_intercept(self, **kwargs):
            """Leave an unhandled exception unchanged."""
            return None

    async def run():
        """Exercise both compatible interceptor paths."""
        manager = InterruptibleChainManager.__new__(InterruptibleChainManager)
        node = SimpleNamespace(instance=Middleware(), prev=None)
        manager.chain_tail = node
        request = Request(url="https://example.com")
        response = Response(request=request)

        async def identity(value):
            """Return a callback value without modification."""
            return value

        response_result = await manager.response_intercept_chain(
            request=request,
            response=response,
            spider=None,
            callback=identity,
        )
        assert response_result.next == ChainNextEnum.SPIDER
        assert response_result.response is response

        error = RuntimeError("boom")
        exception_result = await manager.exception_intercept_chain(
            request=request,
            exception=error,
            spider=None,
            callback=identity,
        )
        assert exception_result.next == ChainNextEnum.EXCEPTION
        assert exception_result.exception is error

    asyncio.run(run())


def test_class_based_settings_export_to_recoverable_env_paths():
    """Class-based settings must serialize to importable dotted paths."""
    from scrapy_cffi.pipelines import Pipeline
    from scrapy_cffi.platform import CurlCffiHttpSession
    from scrapy_cffi.scheduler import RedisScheduler
    from scrapy_cffi.settings import SettingsInfo
    from scrapy_cffi.spiders import RedisSpider
    from scrapy_cffi.utils.envConfig import env_to_settings, settings_to_env

    settings = SettingsInfo(
        SPIDERS_PATH=RedisSpider,
        SCHEDULER=RedisScheduler,
        ITEM_PIPELINES_PATH=[Pipeline],
        HTTP_SESSION_FACTORY=CurlCffiHttpSession,
        RESOURCES_PATH=[CompatibilityResource],
    )
    with tempfile.TemporaryDirectory() as directory:
        env_path = Path(directory) / ".env"
        settings_to_env(settings, env_path)
        env_text = env_path.read_text(encoding="utf-8")
        restored = env_to_settings(env_path, SettingsInfo)

    assert "<class" not in env_text
    assert "scrapy_cffi.core.scheduler.redis.RedisScheduler" in env_text
    assert "scrapy_cffi.platform.curl_cffi.CurlCffiHttpSession" in env_text
    assert "test_python39_compatibility.CompatibilityResource" in env_text
    assert restored.SCHEDULER == "scrapy_cffi.core.scheduler.redis.RedisScheduler"
    assert restored.HTTP_SESSION_FACTORY == "scrapy_cffi.platform.curl_cffi.CurlCffiHttpSession"
    assert restored.ITEM_PIPELINES_PATH.value == [Pipeline]
    assert restored.RESOURCES_PATH == [
        "test_python39_compatibility.CompatibilityResource"
    ]
