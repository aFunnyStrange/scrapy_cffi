"""Verify mandatory Client Hints handling and session ownership."""

import asyncio
from types import SimpleNamespace

from scrapy_cffi.core.downloader.internet import HttpRequest, HttpResponse
from scrapy_cffi.core.sessions import SessionManager
from scrapy_cffi.interceptors.client_hints import ClientHintsDownloadInterceptor
from scrapy_cffi.profiles import register_profile
from scrapy_cffi.settings import SettingsInfo


class _RawResponse:
    """Provide the response surface consumed by HttpResponse."""

    def __init__(self, headers):
        """Create a successful response with caller-controlled headers."""
        self.status_code = 200
        self.content = b"ok"
        self.text = "ok"
        self.headers = headers


def _response(request: HttpRequest, headers) -> HttpResponse:
    """Wrap raw headers in the framework response type."""
    return HttpResponse(
        session_id=request.session_id,
        raw_response=_RawResponse(headers),
        request=request,
    )


def _interceptor(sessions: SessionManager) -> ClientHintsDownloadInterceptor:
    """Build the mandatory interceptor without a full crawler process."""
    return ClientHintsDownloadInterceptor(
        sessions=sessions,
        stop_event=asyncio.Event(),
        settings=sessions.settings,
    )


def test_client_hints_are_origin_session_and_profile_scoped() -> None:
    """Apply negotiated metadata only to matching subsequent requests."""
    register_profile(
        "client-hints-scope-profile",
        "native_client_hints_scope",
        client_hints={
            "Sec-CH-UA-Full-Version-List": '"Chromium";v="151.0.0.0"',
        },
    )

    async def run() -> None:
        """Negotiate once and compare the relevant isolation boundaries."""
        sessions = SessionManager(
            asyncio.Event(),
            SettingsInfo(ROBOTSTXT_OBEY=False),
        )
        interceptor = _interceptor(sessions)
        spider = SimpleNamespace()
        negotiation = HttpRequest(
            url="https://example.test/bootstrap",
            session_id="account-1",
            impersonate="client-hints-scope-profile",
        )
        response = _response(
            negotiation,
            {"Accept-CH": "Sec-CH-UA-Full-Version-List"},
        )

        assert await interceptor.response_intercept(
            negotiation,
            response,
            spider,
        ) is response

        matching = HttpRequest(
            url="https://example.test/api",
            session_id="account-1",
            impersonate="client-hints-scope-profile",
        )
        other_origin = HttpRequest(
            url="https://other.test/api",
            session_id="account-1",
            impersonate="client-hints-scope-profile",
        )
        other_session = HttpRequest(
            url="https://example.test/api",
            session_id="account-2",
            impersonate="client-hints-scope-profile",
        )
        await interceptor.request_intercept(matching, spider)
        await interceptor.request_intercept(other_origin, spider)
        await interceptor.request_intercept(other_session, spider)

        assert matching.headers["Sec-CH-UA-Full-Version-List"] == (
            '"Chromium";v="151.0.0.0"'
        )
        assert other_origin.headers == {}
        assert other_session.headers == {}

        explicit = HttpRequest(
            url="https://example.test/explicit",
            session_id="account-1",
            impersonate="client-hints-scope-profile",
            headers={"sec-ch-ua-full-version-list": '"caller-owned"'},
        )
        await interceptor.request_intercept(explicit, spider)
        assert explicit.headers == {
            "sec-ch-ua-full-version-list": '"caller-owned"'
        }

        await interceptor.response_intercept(
            negotiation,
            _response(negotiation, {"Clear-Site-Data": '"clientHints"'}),
            spider,
        )
        after_clear = HttpRequest(
            url="https://example.test/after-clear",
            session_id="account-1",
            impersonate="client-hints-scope-profile",
        )
        await interceptor.request_intercept(after_clear, spider)
        assert after_clear.headers == {}
        await sessions.close_all()

    asyncio.run(run())


def test_client_hints_interceptor_preserves_acquire_release_ownership() -> None:
    """Never reschedule or release the request owned by the downloader."""
    register_profile(
        "client-hints-lifecycle-profile",
        "native_client_hints_lifecycle",
        client_hints={"Sec-CH-UA-Arch": '"x86"'},
    )

    async def run() -> None:
        """Keep the acquired reference until the simulated downloader release."""
        sessions = SessionManager(
            asyncio.Event(),
            SettingsInfo(ROBOTSTXT_OBEY=False),
        )
        interceptor = _interceptor(sessions)
        spider = SimpleNamespace()
        request = HttpRequest(
            url="https://lifecycle.test/",
            session_id="finite-session",
            impersonate="client-hints-lifecycle-profile",
        )
        sessions.acquire(request.session_id)
        sessions.mark_end(request.session_id)

        request_result = await interceptor.request_intercept(request, spider)
        response = _response(request, {"Accept-CH": "Sec-CH-UA-Arch"})
        response_result = await interceptor.response_intercept(
            request,
            response,
            spider,
        )

        assert request_result is None
        assert response_result is response
        assert sessions._ref_counts[request.session_id] == 1
        assert request.session_id not in sessions._pending_close_set

        sessions.release(request.session_id)
        assert sessions._ref_counts[request.session_id] == 0
        assert request.session_id in sessions._pending_close_set
        await sessions.close_all()

    asyncio.run(run())


def test_spider_resolver_supplies_missing_profile_hint() -> None:
    """Allow a spider callback to provide runtime-only hint values."""

    class Spider:
        """Resolve one application-specific high-entropy hint."""

        async def resolve_client_hint(self, name, origin, response):
            """Return the value associated with the active browser build."""
            assert name == "Sec-CH-UA-Platform-Version"
            assert origin == "https://resolver.test"
            return '"15.0.0"'

    async def run() -> None:
        """Observe Accept-CH and inject the callback result next time."""
        sessions = SessionManager(
            asyncio.Event(),
            SettingsInfo(ROBOTSTXT_OBEY=False),
        )
        interceptor = _interceptor(sessions)
        negotiation = HttpRequest(
            url="https://resolver.test/",
            session_id="resolver-session",
            impersonate="vendor-profile",
        )
        await interceptor.response_intercept(
            negotiation,
            _response(
                negotiation,
                {"Accept-CH": "Sec-CH-UA-Platform-Version"},
            ),
            Spider(),
        )
        follow_up = HttpRequest(
            url="https://resolver.test/next",
            session_id="resolver-session",
            impersonate="vendor-profile",
        )
        await interceptor.request_intercept(follow_up, Spider())

        assert follow_up.headers["Sec-CH-UA-Platform-Version"] == '"15.0.0"'
        await sessions.close_all()

    asyncio.run(run())
