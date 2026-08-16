"""Inspect TLS fingerprints through public diagnostic JSON endpoints."""

import json

from scrapy_cffi.exceptions import Failure
from scrapy_cffi.internet import HttpRequest, HttpResponse
from scrapy_cffi.spiders import Spider
from scrapy_cffi.utils import init_logger


class TlsSpider(Spider):
    """Request TLS inspection endpoints with explicitly selected profiles."""

    name = "tlsSpider"
    allowed_domains = [
        "tls.peet.ws",
        "tls.browserleaks.com",
        "www.howsmyssl.com",
    ]
    tls_check_urls = (
        "https://tls.peet.ws/api/all",
        "https://tls.browserleaks.com/json",
        "https://www.howsmyssl.com/a/check",
    )
    # Add curl_cffi built-ins or aliases declared in
    # profiles/artifacts/<runtime>/scrapy_cffi_profiles.toml.
    impersonate_profiles = (None,)

    def __init__(self, *args, **kwargs) -> None:
        """Initialize the spider and its bounded diagnostic logger."""
        super().__init__(*args, **kwargs)
        self.logger = init_logger(
            log_info=self.settings.LOG_INFO,
            logger_name=__name__,
        )

    async def start(self):
        """Schedule each profile through its own reusable HTTP session."""
        for impersonate in self.impersonate_profiles:
            profile_name = impersonate or "curl_cffi-default"
            session_id = f"tls-profile:{profile_name}"
            for url in self.tls_check_urls:
                yield HttpRequest(
                    session_id=session_id,
                    url=url,
                    timeout=self.settings.TIMEOUT,
                    dont_filter=True,
                    impersonate=impersonate,
                    callback=self.parse,
                    errback=self.errRet,
                    meta={"impersonate": profile_name},
                )

    async def parse(self, response: HttpResponse):
        """Yield one JSON-safe diagnostic result."""
        try:
            payload = json.loads(response.text)
        except json.JSONDecodeError:
            payload = {"raw": response.text[:1000]}
        summary = {
            "url": response.request.url,
            "impersonate": response.meta["impersonate"],
            "session_id": response.session_id,
            "status_code": response.status_code,
        }
        if response.request.url == "https://tls.peet.ws/api/all":
            tls = payload.get("tls", {})
            http2 = payload.get("http2", {})
            summary.update(
                {
                    "user_agent": payload.get("user_agent"),
                    "ja3_hash": tls.get("ja3_hash"),
                    "ja4": tls.get("ja4"),
                    "akamai_hash": http2.get("akamai_fingerprint_hash"),
                    "tls_session_id": tls.get("session_id"),
                }
            )
        elif response.request.url == "https://www.howsmyssl.com/a/check":
            summary.update(
                {
                    "tls_version": payload.get("tls_version"),
                    "rating": payload.get("rating"),
                    "post_quantum": payload.get("post_quantum_key_agreement"),
                }
            )
        self.logger.info(
            "TLS diagnostic: %s",
            json.dumps(summary, ensure_ascii=False, sort_keys=True),
        )
        yield {
            "url": response.request.url,
            "impersonate": response.meta["impersonate"],
            "session_id": response.session_id,
            "status_code": response.status_code,
            "tls": payload,
        }

    async def errRet(self, failure: Failure):
        """Log a bounded failure with its explicitly selected profile."""
        request = getattr(failure, "request", None)
        profile = (
            request.meta.get("impersonate", "unknown")
            if request is not None
            else "unknown"
        )
        self.logger.warning(
            "TLS diagnostic failed: profile=%s url=%s error=%s",
            profile,
            getattr(request, "url", "unknown"),
            str(failure),
        )
        yield None
