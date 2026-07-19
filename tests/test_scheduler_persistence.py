from __future__ import annotations

import asyncio
from http.cookiejar import Cookie


class FakeRedisHash:
    def __init__(self):
        self.data = {}
        self.queues = {}
        self.redis_mode = "single"
        self._redis_url = []

    async def hset(self, key, field, value):
        self.data.setdefault(key, {})[field] = value
        return 1

    async def hget(self, key, field):
        return self.data.get(key, {}).get(field)

    async def rpush(self, key, value):
        self.queues.setdefault(key, []).append(value)
        return len(self.queues[key])

    async def dequeue_request(self, queue_key):
        queue = self.queues.get(queue_key, [])
        return queue.pop(0) if queue else None

    async def llen(self, key):
        return len(self.queues.get(key, []))


def _cookie(name="token", value="secret"):
    return Cookie(
        version=0,
        name=name,
        value=value,
        port=None,
        port_specified=False,
        domain=".example.com",
        domain_specified=True,
        domain_initial_dot=True,
        path="/api",
        path_specified=True,
        secure=True,
        expires=2_000_000_000,
        discard=False,
        comment=None,
        comment_url=None,
        rest={"HttpOnly": None, "SameSite": "Lax"},
        rfc2109=False,
    )


def test_request_state_codec_round_trip_and_adaptive_compression():
    from scrapy_cffi.core.downloader.internet import HttpRequest, Request
    from scrapy_cffi.utils.state_codec import decode_state, encode_state

    assert encode_state({"x": "y"})[:5] == b"SCF1J"
    assert encode_state({"x": "y" * 1000})[:5] == b"SCF1Z"
    assert decode_state(encode_state({"unicode": "中文"})) == {"unicode": "中文"}

    request = HttpRequest(
        url="https://example.com/api",
        data=b"payload" * 100,
        cookies={"request-cookie": "ok"},
        meta={"large": "a" * 2000},
    )
    restored = Request.from_bytes(request.to_bytes())
    assert restored.url == request.url
    assert restored.data == request.data
    assert restored.cookies == request.cookies
    assert restored.meta == request.meta


def test_state_codec_rejects_oversized_raw_and_compressed_payloads():
    import zlib

    from scrapy_cffi.utils.state_codec import decode_state, encode_state

    try:
        encode_state({"value": "too-large"}, max_size=4)
    except ValueError as exc:
        assert "size limit" in str(exc)
    else:
        raise AssertionError("oversized state was accepted")

    compressed = b"SCF1Z" + zlib.compress(b'"' + (b"x" * 1024) + b'"')
    try:
        decode_state(compressed, max_size=32)
    except ValueError as exc:
        assert "decompressed scheduler state" in str(exc)
    else:
        raise AssertionError("compressed oversized state was accepted")


def test_session_cookie_hash_round_trip_preserves_cookie_attributes():
    from scrapy_cffi.core.sessions import SessionManager
    from scrapy_cffi.settings import SettingsInfo

    async def run():
        redis = FakeRedisHash()
        settings = SettingsInfo(ROBOTSTXT_OBEY=False)
        source = SessionManager(asyncio.Event(), settings)
        source_wrapper = source.get_or_create_session("account-1")
        source_wrapper.session.cookies.jar.set_cookie(_cookie())

        assert await source.persist_session(redis, "demo_req:sessions", "account-1")
        payload = redis.data["demo_req:sessions"]["S:account-1"]
        assert payload.startswith(b"SCF1")

        target = SessionManager(asyncio.Event(), settings)
        assert await target.restore_session(redis, "demo_req:sessions", "account-1")
        restored = list(target.get_or_create_session("account-1").session.cookies.jar)[0]
        assert restored.name == "token"
        assert restored.value == "secret"
        assert restored.domain == ".example.com"
        assert restored.path == "/api"
        assert restored.secure is True
        assert restored.expires == 2_000_000_000
        assert restored._rest["SameSite"] == "Lax"

        # A field is loaded only once; current in-process cookies stay authoritative.
        assert not await target.restore_session(redis, "demo_req:sessions", "account-1")
        await source.close_all()
        await target.close_all()

    asyncio.run(run())


def test_group_session_cookie_round_trip():
    from scrapy_cffi.core.sessions import SessionManager
    from scrapy_cffi.settings import SettingsInfo

    async def run():
        redis = FakeRedisHash()
        settings = SettingsInfo(ROBOTSTXT_OBEY=False)
        source = SessionManager(asyncio.Event(), settings)
        source.register_sessions_batch(
            {"one": {"token": "1"}, "two": {"token": "2"}},
            group_id="pool",
        )
        assert await source.persist_session(redis, "demo_req:sessions", "pool")

        target = SessionManager(asyncio.Event(), settings)
        assert await target.restore_session(redis, "demo_req:sessions", "pool")
        cookies = target.get_session_cookies("pool")
        assert cookies == {"one": {"token": "1"}, "two": {"token": "2"}}
        await source.close_all()
        await target.close_all()

    asyncio.run(run())


def test_redis_scheduler_persists_before_enqueue_and_restores_after_dequeue():
    from unittest.mock import MagicMock

    from scrapy_cffi.core.downloader.internet import HttpRequest
    from scrapy_cffi.core.scheduler.redis import RedisScheduler
    from scrapy_cffi.core.sessions import SessionManager
    from scrapy_cffi.settings import SettingsInfo

    class Spider:
        name = "demo"

    async def run():
        redis = FakeRedisHash()
        settings = SettingsInfo(ROBOTSTXT_OBEY=False, SCHEDULER_PERSIST=True)
        source_sessions = SessionManager(asyncio.Event(), settings)
        source_sessions.get_or_create_session("account").session.cookies.set("token", "fresh")
        source = RedisScheduler(
            spiders_name=["demo"],
            stop_event=asyncio.Event(),
            settings=settings,
            sessions=source_sessions,
            sessions_lock=asyncio.Lock(),
            signalManager=MagicMock(),
            redisManager=redis,
        )
        request = HttpRequest(
            session_id="account",
            url="https://example.com",
            dont_filter=True,
        )
        assert await source.put(request, Spider())
        assert "demo_req:sessions" in redis.data

        target_sessions = SessionManager(asyncio.Event(), settings)
        target = RedisScheduler(
            spiders_name=["demo"],
            stop_event=asyncio.Event(),
            settings=settings,
            sessions=target_sessions,
            sessions_lock=asyncio.Lock(),
            signalManager=MagicMock(),
            redisManager=redis,
        )
        restored_request = await target.get(Spider())
        assert restored_request.session_id == "account"
        cookies = target_sessions.get_session_cookies("account")
        assert cookies == {"account": {"token": "fresh"}}
        await source_sessions.close_all()
        await target_sessions.close_all()

    asyncio.run(run())
