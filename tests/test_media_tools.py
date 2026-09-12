"""Verify media requests and tools stay bounded inside one asyncio loop."""

import asyncio
import importlib.util
import io
import shutil
import wave
from types import SimpleNamespace

import pytest

from scrapy_cffi.core.downloader.internet import MediaRequest
from scrapy_cffi.core.sessions import SessionWrapper
from scrapy_cffi.models.media import AudioInfo, MediaContentType, MediaInfo
from scrapy_cffi.utils.ffmpeg import FFmpegProcessState, FFmpegResult
from scrapy_cffi.utils.media import (
    MediaProbe,
    get_audio_info_from_bytes_async,
    guess_content_type,
    inspect_image_bytes_async,
)


class _ImmediateLimiter:
    """Provide the limiter operation used by media requests."""

    async def wait(self) -> None:
        """Return immediately without introducing a polling delay."""


class _RangeSession:
    """Serve deterministic byte ranges and capture request headers."""

    def __init__(self, content: bytes) -> None:
        """Store one immutable source body."""
        self.content = content
        self.calls = []

    async def request(self, method, **kwargs):
        """Return the requested inclusive range or the complete body."""
        self.calls.append((method, kwargs))
        range_value = (kwargs.get("headers") or {}).get("Range")
        if range_value:
            start_text, end_text = range_value.removeprefix("bytes=").split("-")
            content = self.content[int(start_text):int(end_text) + 1]
        else:
            content = self.content
        return SimpleNamespace(
            status_code=206 if range_value else 200,
            content=content,
            text="",
            headers={},
        )


def _media_wrapper(content: bytes) -> SessionWrapper:
    """Construct the narrow SessionWrapper surface used by range tests."""
    wrapper = SessionWrapper.__new__(SessionWrapper)
    wrapper.stop_event = asyncio.Event()
    wrapper.request_limiter = _ImmediateLimiter()
    wrapper.session = _RangeSession(content)
    wrapper.settings = SimpleNamespace(MAX_REQ_TIMES=2, DELAY_REQ_TIME=0)
    wrapper._impersonate_resolver = lambda value: value
    return wrapper


def _wav_bytes() -> bytes:
    """Create a tiny PCM WAV payload using only the Python standard library."""
    output = io.BytesIO()
    with wave.open(output, "wb") as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(8000)
        wav_file.writeframes(b"\x00\x00" * 800)
    return output.getvalue()


def test_media_request_uses_inclusive_sequential_ranges_without_mutation():
    """Download every byte once without adding hidden concurrent work."""

    async def run() -> None:
        """Drive range completion from actual response events."""
        wrapper = _media_wrapper(b"abcdef")
        headers = {"Accept": "audio/*"}
        request = MediaRequest(
            url="https://media.test/audio.wav",
            headers=headers,
            media_size=6,
            single_part_size=2,
            max_media_size=6,
        )
        response = await wrapper.media_req(request)

        assert response.content == b"abcdef"
        assert request.headers == headers
        assert [
            call[1]["headers"]["Range"]
            for call in wrapper.session.calls
        ] == ["bytes=0-1", "bytes=2-3", "bytes=4-5"]

    asyncio.run(run())


def test_media_request_with_unknown_size_uses_one_ordinary_request():
    """Avoid fabricating ranges when the caller does not know media size."""

    async def run() -> None:
        """Observe one transport request with no Range header."""
        wrapper = _media_wrapper(b"audio")
        response = await wrapper.media_req(
            MediaRequest(url="https://media.test/audio", media_size=0)
        )
        assert response.content == b"audio"
        assert len(wrapper.session.calls) == 1
        assert "Range" not in (wrapper.session.calls[0][1]["headers"] or {})

    asyncio.run(run())


def test_media_request_validates_download_bounds():
    """Reject invalid chunk and total-size limits before network I/O."""
    with pytest.raises(ValueError, match="single_part_size"):
        MediaRequest(single_part_size=0)
    with pytest.raises(ValueError, match="media_size must"):
        MediaRequest(media_size=-1)
    with pytest.raises(ValueError, match="exceeds max_media_size"):
        MediaRequest(media_size=10, max_media_size=5)


@pytest.mark.parametrize("override", [None, 3])
def test_media_retries_each_range_without_replaying_completed_bytes(override):
    """Give every range its full budget while preserving assembled bytes."""
    async def run() -> None:
        """Fail each range until its last permitted attempt."""
        wrapper = _media_wrapper(b"abcdef")
        attempts = override or wrapper.settings.MAX_REQ_TIMES
        seen = []
        original = wrapper.session.request

        async def flaky_request(method, **kwargs):
            """Record all attempts and fail the first attempts of each range."""
            byte_range = kwargs["headers"]["Range"]
            seen.append(byte_range)
            if seen.count(byte_range) < attempts:
                raise TimeoutError("temporary range failure")
            return await original(method, **kwargs)

        wrapper.session.request = flaky_request
        request = MediaRequest(
            media_size=6, single_part_size=2,
            max_retry_times=override, retry_delay=0,
            headers={"Accept": "video/*"},
        )
        response = await wrapper.do_request(request)
        assert response.content == b"abcdef"
        assert seen == [part for part in (
            "bytes=0-1", "bytes=2-3", "bytes=4-5"
        ) for _ in range(attempts)]
        assert request.headers == {"Accept": "video/*"}

    asyncio.run(run())


@pytest.mark.parametrize("error,expected_attempts", [
    (ConnectionError, 3), (ValueError, 1), (asyncio.CancelledError, 1),
])
def test_media_failed_range_never_restarts_download(error, expected_attempts):
    """Exhaustion, programming errors, and cancellation never replay a file."""
    async def run() -> None:
        """Fail the second range and prove the third is never requested."""
        wrapper = _media_wrapper(b"abcdef")
        seen = []
        original = wrapper.session.request

        async def failing_request(method, **kwargs):
            """Only the first range can complete."""
            byte_range = kwargs["headers"]["Range"]
            seen.append(byte_range)
            if byte_range == "bytes=2-3":
                raise error("range failed")
            return await original(method, **kwargs)

        wrapper.session.request = failing_request
        with pytest.raises(error):
            await wrapper.do_request(MediaRequest(
                media_size=6, single_part_size=2,
                max_retry_times=3, retry_delay=0,
            ))
        assert seen == ["bytes=0-1"] + ["bytes=2-3"] * expected_attempts

    asyncio.run(run())


def test_unknown_size_media_has_one_retry_budget():
    """An unknown-size download still retries without multiplying attempts."""
    async def run() -> None:
        """Exhaust a single ordinary request's configured budget."""
        wrapper = _media_wrapper(b"abcd")
        seen = []

        async def failing_request(method, **kwargs):
            """Fail every ordinary transport request."""
            seen.append(kwargs)
            raise ConnectionError("offline")

        wrapper.session.request = failing_request
        with pytest.raises(ConnectionError):
            await wrapper.do_request(MediaRequest(max_retry_times=3, retry_delay=0))
        assert len(seen) == 3
        assert all("Range" not in (call["headers"] or {}) for call in seen)

    asyncio.run(run())


def test_downloader_media_budget_covers_all_ranges():
    """Allow full attempts for every range without changing HTTP or streams."""
    from scrapy_cffi.core.downloader.fetch import Downloader
    from scrapy_cffi.internet import HttpRequest

    downloader = Downloader.__new__(Downloader)
    downloader.settings = SimpleNamespace(
        TIMEOUT=10, MAX_REQ_TIMES=2, DELAY_REQ_TIME=3,
    )
    assert downloader._request_deadline(HttpRequest(timeout=10)) == 25
    assert downloader._request_deadline(MediaRequest(timeout=10)) == 25
    assert downloader._request_deadline(MediaRequest(
        timeout=10, media_size=5, single_part_size=2,
        max_retry_times=3, retry_delay=0,
    )) == 96
    assert downloader._request_deadline(MediaRequest(
        timeout=10, media_size=5, single_part_size=2, stream=True,
    )) == 25


@pytest.mark.parametrize("exhaust", [False, True])
def test_media_range_retry_through_downloader_error_and_success_paths(exhaust):
    """Deliver either a complete body or one typed failure and release session."""
    from scrapy_cffi.core.downloader.fetch import Downloader
    from scrapy_cffi.exceptions import RequestTimeoutError
    from scrapy_cffi.platform.http import HttpTimeoutError
    from scrapy_cffi.settings import SettingsInfo

    async def run() -> None:
        """Exercise Downloader and SessionWrapper together on a range failure."""
        wrapper = _media_wrapper(b"abcdef")
        original = wrapper.session.request
        seen = []
        released = []
        results = []

        async def flaky_request(method, **kwargs):
            """Fail only the middle range once or until exhaustion."""
            byte_range = kwargs["headers"]["Range"]
            seen.append(byte_range)
            if byte_range == "bytes=2-3" and (exhaust or seen.count(byte_range) == 1):
                raise HttpTimeoutError("slow range")
            return await original(method, **kwargs)

        async def callback(response, request):
            """Capture the result delivered to the engine boundary."""
            results.append((response, request))

        wrapper.session.request = flaky_request
        downloader = Downloader(
            stop_event=wrapper.stop_event,
            settings=SettingsInfo(MAX_REQ_TIMES=2, DELAY_REQ_TIME=0),
            sessions=SimpleNamespace(
                get_or_create_session=lambda **kwargs: wrapper,
                release=lambda **kwargs: released.append(kwargs),
            ),
            sessions_lock=asyncio.Lock(),
            signalManager=SimpleNamespace(send=lambda **kwargs: None),
        )
        request = MediaRequest(media_size=6, single_part_size=2)
        await downloader.fetch_http(request, callback)
        assert len(results) == len(released) == 1
        response, returned_request = results[0]
        assert returned_request is request
        if exhaust:
            assert isinstance(response, RequestTimeoutError)
            assert response.attempts == 2
            assert seen == ["bytes=0-1", "bytes=2-3", "bytes=2-3"]
        else:
            assert response.content == b"abcdef"
            assert seen == ["bytes=0-1", "bytes=2-3", "bytes=2-3", "bytes=4-5"]

    asyncio.run(run())


def test_unknown_size_media_applies_received_body_bound():
    """Enforce the memory limit after an ordinary unknown-size response."""

    async def run() -> None:
        """Reject a body larger than the caller's explicit bound."""
        wrapper = _media_wrapper(b"oversized")
        with pytest.raises(ValueError, match="max_media_size"):
            await wrapper.media_req(
                MediaRequest(media_size=0, max_media_size=4)
            )

    asyncio.run(run())


def test_known_size_media_rejects_incomplete_range_response():
    """Do not label a short body as a complete known-size media response."""

    class _ShortRangeSession(_RangeSession):
        """Return an empty final range to simulate transport truncation."""

        async def request(self, method, **kwargs):
            """Delegate capture but truncate the second range body."""
            response = await super().request(method, **kwargs)
            if len(self.calls) == 2:
                response.content = b""
            return response

    async def run() -> None:
        """Observe the final byte-count validation failure."""
        wrapper = _media_wrapper(b"abcd")
        wrapper.session = _ShortRangeSession(b"abcd")
        with pytest.raises(ValueError, match="does not match"):
            await wrapper.media_req(
                MediaRequest(media_size=4, single_part_size=2)
            )

    asyncio.run(run())


def test_known_size_media_accepts_one_complete_non_range_response():
    """Accept servers that ignore Range but return the exact complete body."""

    class _FullBodySession(_RangeSession):
        """Ignore the Range header and return one complete HTTP 200 body."""

        async def request(self, method, **kwargs):
            """Capture the call and expose the complete source body."""
            self.calls.append((method, kwargs))
            return SimpleNamespace(
                status_code=200,
                content=self.content,
                text="",
                headers={},
            )

    async def run() -> None:
        """Finish from the first exact-size response without duplication."""
        wrapper = _media_wrapper(b"abcd")
        wrapper.session = _FullBodySession(b"abcd")
        response = await wrapper.media_req(
            MediaRequest(media_size=4, single_part_size=2)
        )
        assert response.content == b"abcd"
        assert len(wrapper.session.calls) == 1

    asyncio.run(run())


def test_audio_model_is_additive_to_historical_media_discriminators():
    """Accept audio type 2 while retaining video 0 and image 1 values."""
    audio = AudioInfo(
        inner_mediaurl="https://media.test/audio.wav",
        media_size=1644,
        sample_rate=8000,
        channels=1,
    )
    media = MediaInfo(
        content_type=MediaContentType.AUDIO,
        audio_info=audio,
    )
    assert media.audio_info is audio
    assert int(MediaContentType.VIDEO) == 0
    assert int(MediaContentType.IMAGE) == 1


def test_mime_sniffing_uses_lazy_cross_platform_dependency():
    """Recognize common magic bytes after selecting the optional tool."""
    assert guess_content_type(b"\x89PNG\r\n\x1a\n" + b"\x00" * 32) == "image/png"


@pytest.mark.skipif(
    importlib.util.find_spec("PIL") is None,
    reason="Pillow media extra is not installed",
)
def test_async_image_inspection_uses_cross_platform_library():
    """Inspect Pillow data through the asynchronous to-thread facade."""

    async def run() -> None:
        """Create and inspect one in-memory image without filesystem state."""
        from PIL import Image

        output = io.BytesIO()
        Image.new("RGB", (3, 2)).save(output, format="PNG")
        info = await inspect_image_bytes_async(output.getvalue())
        assert info["format"] == "PNG"
        assert info["width"] == 3
        assert info["height"] == 2

    asyncio.run(run())


def test_media_probe_normalizes_audio_without_leaking_ffprobe_json():
    """Translate vendor JSON into stable immutable stream metadata."""

    async def run() -> None:
        """Inject one completed process result into the probe owner."""
        probe = MediaProbe(executable="unused")

        async def fake_run(*args, **kwargs):
            """Return representative ffprobe JSON without starting a process."""
            return FFmpegResult(
                task_id="probe",
                command=("unused",),
                state=FFmpegProcessState.SUCCEEDED,
                returncode=0,
                pid=1,
                stdout_tail=(
                    b'{"format":{"format_name":"wav","duration":"0.1"},'
                    b'"streams":[{"index":0,"codec_type":"audio",'
                    b'"codec_name":"pcm_s16le","sample_rate":"8000",'
                    b'"channels":1}]}'
                ),
                stderr_tail=b"",
                started_at=1.0,
                ended_at=2.0,
            )

        probe._manager.run = fake_run
        result = await probe.probe_bytes(_wav_bytes())
        assert result.format_name == "wav"
        assert result.duration == 0.1
        assert result.audio_streams[0].sample_rate == 8000
        assert result.size == len(_wav_bytes())
        await probe.close()

    asyncio.run(run())


@pytest.mark.skipif(shutil.which("ffprobe") is None, reason="ffprobe is absent")
def test_real_ffprobe_short_audio_task():
    """Probe a standard-library WAV through one real asynchronous subprocess."""

    async def run() -> None:
        """Verify audio facts and explicit context-managed cleanup."""
        info = await get_audio_info_from_bytes_async(
            _wav_bytes(),
            input_format="wav",
            timeout=10,
        )
        assert info["codec_name"] == "pcm_s16le"
        assert info["sample_rate"] == 8000
        assert info["channels"] == 1

    asyncio.run(run())
