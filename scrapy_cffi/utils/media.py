"""Inspect media with lazy cross-platform libraries and bounded ffprobe tasks."""

import asyncio
import json
import logging
import os
import tempfile
from dataclasses import dataclass, replace
from io import BytesIO
from typing import Any, Dict, List, Optional, Tuple, Union

from .ffmpeg import (
    FFmpegProcessManager,
    FFmpegProcessState,
    FFmpegResult,
)


logger = logging.getLogger(__name__)


class MediaInspectionError(RuntimeError):
    """Report invalid media data or a failed inspection backend."""


class MediaDependencyError(MediaInspectionError, ImportError):
    """Report a missing optional library only when its tool is selected."""


class MediaProbeError(MediaInspectionError):
    """Report a failed or malformed ffprobe invocation."""


@dataclass(frozen=True)
class MediaStreamInfo:
    """Represent stable metadata for one audio, video, or other stream."""

    index: int
    kind: str
    codec_name: Optional[str] = None
    duration: Optional[float] = None
    bit_rate: Optional[int] = None
    width: Optional[int] = None
    height: Optional[int] = None
    sample_rate: Optional[int] = None
    channels: Optional[int] = None


@dataclass(frozen=True)
class MediaProbeResult:
    """Represent normalized container and stream facts returned by ffprobe."""

    format_name: Optional[str]
    duration: Optional[float]
    size: Optional[int]
    bit_rate: Optional[int]
    streams: Tuple[MediaStreamInfo, ...]

    @property
    def video_streams(self) -> Tuple[MediaStreamInfo, ...]:
        """Return only video streams while retaining their source order."""
        return tuple(stream for stream in self.streams if stream.kind == "video")

    @property
    def audio_streams(self) -> Tuple[MediaStreamInfo, ...]:
        """Return only audio streams while retaining their source order."""
        return tuple(stream for stream in self.streams if stream.kind == "audio")


class MediaProbe:
    """Own a bounded set of short asynchronous ffprobe subprocesses.

    This utility has no crawler integration or background worker. Applications
    may construct one in ``runner.py`` and explicitly pass it to their spiders.
    """

    def __init__(
        self,
        max_processes: Optional[int] = 2,
        executable: Union[str, os.PathLike] = "ffprobe",
        timeout: float = 15.0,
        max_output_size: int = 4 * 1024 * 1024,
    ) -> None:
        """Configure subprocess concurrency, timeout, and JSON output bound."""
        if timeout <= 0:
            raise ValueError("timeout must be positive")
        if max_output_size <= 0:
            raise ValueError("max_output_size must be positive")
        self.timeout = timeout
        self.max_output_size = max_output_size
        self._manager = FFmpegProcessManager(
            max_processes=max_processes,
            executable=executable,
            stdout_limit=max_output_size,
            stderr_limit=64 * 1024,
        )

    @classmethod
    def from_settings(cls, settings: object, **kwargs: object) -> "MediaProbe":
        """Build a probe from framework process limits and ffprobe path."""
        return cls(
            max_processes=getattr(settings, "FFMPEG_MAX_PROCESSES"),
            executable=getattr(settings, "FFPROBE_EXECUTABLE"),
            **kwargs,
        )

    async def probe_bytes(
        self,
        media_data: bytes,
        input_format: Optional[str] = None,
    ) -> MediaProbeResult:
        """Inspect in-memory media without writing a temporary file."""
        if not media_data:
            raise ValueError("media_data must not be empty")
        args: List[str] = ["-v", "error"]
        if input_format:
            args.extend(["-f", input_format])
        args.extend(
            [
                "-print_format",
                "json",
                "-show_streams",
                "-show_format",
                "pipe:0",
            ]
        )
        process_result = await self._manager.run(
            *args,
            input_data=media_data,
            timeout=self.timeout,
        )
        probe_result = self._decode_result(process_result)
        if probe_result.size is None:
            probe_result = replace(probe_result, size=len(media_data))
        return probe_result

    async def probe_file(
        self,
        media_path: Union[str, os.PathLike],
    ) -> MediaProbeResult:
        """Inspect a path while leaving filesystem ownership with the caller."""
        path = os.fspath(media_path)
        if not path:
            raise ValueError("media_path must not be empty")
        process_result = await self._manager.run(
            "-v",
            "error",
            "-print_format",
            "json",
            "-show_streams",
            "-show_format",
            path,
            timeout=self.timeout,
        )
        return self._decode_result(process_result)

    async def close(self) -> None:
        """Stop every probe still owned by this explicitly managed utility."""
        await self._manager.close()

    async def __aenter__(self) -> "MediaProbe":
        """Return this probe owner without starting a subprocess."""
        return self

    async def __aexit__(self, exc_type, exc, traceback) -> None:
        """Close subprocesses retained by this context."""
        await self.close()

    def _decode_result(self, result: FFmpegResult) -> MediaProbeResult:
        """Translate ffprobe JSON into framework-owned stable metadata."""
        if result.state != FFmpegProcessState.SUCCEEDED:
            detail = result.stderr_tail.decode("utf-8", errors="replace")
            raise MediaProbeError(
                "ffprobe failed with state %s and code %s: %s"
                % (result.state.value, result.returncode, detail[-2048:])
            )
        try:
            payload = json.loads(result.stdout_tail.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise MediaProbeError(
                "ffprobe returned invalid or oversized JSON output"
            ) from exc
        if not isinstance(payload, dict):
            raise MediaProbeError("ffprobe JSON root must be an object")
        return _normalize_probe_payload(payload)


def _optional_float(value: Any) -> Optional[float]:
    """Convert one optional ffprobe scalar to a float."""
    if value in (None, "", "N/A"):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _optional_int(value: Any) -> Optional[int]:
    """Convert one optional ffprobe scalar to an integer."""
    if value in (None, "", "N/A"):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _normalize_probe_payload(payload: Dict[str, Any]) -> MediaProbeResult:
    """Normalize vendor JSON without exposing its mapping shape to callers."""
    format_payload = payload.get("format")
    if not isinstance(format_payload, dict):
        format_payload = {}
    streams_payload = payload.get("streams")
    if not isinstance(streams_payload, list):
        streams_payload = []

    streams = []
    for position, stream_payload in enumerate(streams_payload):
        if not isinstance(stream_payload, dict):
            continue
        stream_index = _optional_int(stream_payload.get("index"))
        streams.append(
            MediaStreamInfo(
                index=position if stream_index is None else stream_index,
                kind=str(stream_payload.get("codec_type") or "unknown"),
                codec_name=_optional_text(stream_payload.get("codec_name")),
                duration=_optional_float(stream_payload.get("duration")),
                bit_rate=_optional_int(stream_payload.get("bit_rate")),
                width=_optional_int(stream_payload.get("width")),
                height=_optional_int(stream_payload.get("height")),
                sample_rate=_optional_int(stream_payload.get("sample_rate")),
                channels=_optional_int(stream_payload.get("channels")),
            )
        )

    duration = _optional_float(format_payload.get("duration"))
    if duration is None:
        stream_durations = [
            stream.duration
            for stream in streams
            if stream.duration is not None
        ]
        duration = max(stream_durations) if stream_durations else None
    return MediaProbeResult(
        format_name=_optional_text(format_payload.get("format_name")),
        duration=duration,
        size=_optional_int(format_payload.get("size")),
        bit_rate=_optional_int(format_payload.get("bit_rate")),
        streams=tuple(streams),
    )


def _optional_text(value: Any) -> Optional[str]:
    """Convert one optional metadata scalar to non-empty text."""
    if value in (None, ""):
        return None
    return str(value)


def _load_filetype():
    """Load the optional pure-Python MIME detector on first use."""
    try:
        import filetype
    except ImportError as exc:
        raise MediaDependencyError(
            "MIME sniffing requires: pip install scrapy_cffi[media]"
        ) from exc
    return filetype


def _load_pillow_image():
    """Load Pillow on first use without affecting core framework imports."""
    try:
        from PIL import Image
    except ImportError as exc:
        raise MediaDependencyError(
            "Image inspection requires: pip install scrapy_cffi[media]"
        ) from exc
    return Image


def _load_hachoir():
    """Load hachoir on first use for the legacy synchronous probe path."""
    try:
        from hachoir.metadata import extractMetadata
        from hachoir.parser import createParser
    except ImportError as exc:
        raise MediaDependencyError(
            "Synchronous media inspection requires: "
            "pip install scrapy_cffi[media]"
        ) from exc
    return createParser, extractMetadata


def guess_content_type(byte_data: bytes) -> str:
    """Guess a MIME type from magic bytes using the optional filetype library."""
    if not isinstance(byte_data, bytes):
        raise TypeError("byte_data must be bytes")
    kind = _load_filetype().guess(byte_data[:8192])
    return kind.mime if kind is not None else "application/octet-stream"


def inspect_image_bytes(image_bytes: bytes) -> Dict[str, Union[str, int, None]]:
    """Return image format and dimensions or raise a typed inspection error."""
    if not image_bytes:
        raise ValueError("image_bytes must not be empty")
    image_class = _load_pillow_image()
    try:
        with image_class.open(BytesIO(image_bytes)) as image:
            return {
                "format": image.format,
                "mode": image.mode,
                "width": image.width,
                "height": image.height,
            }
    except Exception as exc:
        raise MediaInspectionError("failed to inspect image bytes") from exc


async def inspect_image_bytes_async(
    image_bytes: bytes,
) -> Dict[str, Union[str, int, None]]:
    """Run Pillow inspection outside the crawler event-loop thread."""
    return await asyncio.to_thread(inspect_image_bytes, image_bytes)


def get_image_info_from_bytes(image_bytes: bytes) -> Union[dict, str]:
    """Preserve the legacy mapping-or-error-text image helper contract."""
    try:
        return inspect_image_bytes(image_bytes)
    except (MediaInspectionError, ValueError) as exc:
        return "Failed to read image: %s" % exc


def get_image_info_from_tempfile(image_bytes: bytes) -> Union[dict, str]:
    """Preserve the old name while avoiding an unnecessary temporary file."""
    return get_image_info_from_bytes(image_bytes)


def _inspect_hachoir_tempfile(
    media_bytes: bytes,
    suffix: str,
) -> Dict[str, Union[float, int]]:
    """Inspect media synchronously for legacy callers using hachoir."""
    if not media_bytes:
        raise ValueError("media_bytes must not be empty")
    create_parser, extract_metadata = _load_hachoir()
    temp_path = ""
    parser = None
    try:
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as temp:
            temp.write(media_bytes)
            temp_path = temp.name
        parser = create_parser(temp_path)
        if parser is None:
            raise MediaInspectionError("hachoir could not parse media")
        metadata = extract_metadata(parser)
        if metadata is None:
            raise MediaInspectionError("hachoir returned no metadata")
        result: Dict[str, Union[float, int]] = {}
        if metadata.has("duration"):
            result["duration"] = metadata.get("duration").total_seconds()
        if metadata.has("width"):
            result["width"] = int(metadata.get("width"))
        if metadata.has("height"):
            result["height"] = int(metadata.get("height"))
        if not result:
            raise MediaInspectionError("hachoir returned no supported metadata")
        return result
    finally:
        if parser is not None and parser.stream is not None:
            try:
                parser.stream.close()
            except Exception:
                logger.warning("Failed to close hachoir media stream")
        if temp_path:
            try:
                os.unlink(temp_path)
            except FileNotFoundError:
                pass
            except OSError:
                logger.warning("Failed to remove media inspection tempfile")


def get_video_info_from_bytes(video_bytes: bytes) -> Union[dict, str]:
    """Preserve synchronous video inspection through cross-platform hachoir."""
    try:
        return _inspect_hachoir_tempfile(video_bytes, suffix=".mp4")
    except (MediaInspectionError, ValueError) as exc:
        return "Failed to read video: %s" % exc


def get_video_info_from_tempfile(video_bytes: bytes) -> Union[dict, str]:
    """Preserve the historical temporary-file video helper name."""
    return get_video_info_from_bytes(video_bytes)


async def inspect_video_bytes_async(
    video_bytes: bytes,
) -> Dict[str, Union[float, int]]:
    """Run optional hachoir parsing outside the crawler event-loop thread."""
    return await asyncio.to_thread(
        _inspect_hachoir_tempfile,
        video_bytes,
        ".mp4",
    )


async def probe_media_bytes(
    media_data: bytes,
    input_format: Optional[str] = None,
    executable: Union[str, os.PathLike] = "ffprobe",
    timeout: float = 15.0,
) -> MediaProbeResult:
    """Run one short ffprobe task with no retained crawler-owned service."""
    async with MediaProbe(
        max_processes=1,
        executable=executable,
        timeout=timeout,
    ) as probe:
        return await probe.probe_bytes(media_data, input_format=input_format)


async def get_video_info_from_bytes_async(
    video_bytes: bytes,
    executable: Union[str, os.PathLike] = "ffprobe",
    timeout: float = 15.0,
) -> Dict[str, Union[str, float, int, None]]:
    """Return normalized first-video-stream facts through asynchronous ffprobe."""
    result = await probe_media_bytes(
        video_bytes,
        executable=executable,
        timeout=timeout,
    )
    if not result.video_streams:
        raise MediaProbeError("no video stream found")
    stream = result.video_streams[0]
    return {
        "width": stream.width,
        "height": stream.height,
        "duration": stream.duration or result.duration,
        "codec_name": stream.codec_name,
    }


async def get_audio_info_from_bytes_async(
    audio_bytes: bytes,
    input_format: Optional[str] = None,
    executable: Union[str, os.PathLike] = "ffprobe",
    timeout: float = 15.0,
) -> Dict[str, Union[str, float, int, None]]:
    """Return normalized first-audio-stream facts through asynchronous ffprobe."""
    result = await probe_media_bytes(
        audio_bytes,
        input_format=input_format,
        executable=executable,
        timeout=timeout,
    )
    if not result.audio_streams:
        raise MediaProbeError("no audio stream found")
    stream = result.audio_streams[0]
    return {
        "duration": stream.duration or result.duration,
        "codec_name": stream.codec_name,
        "sample_rate": stream.sample_rate,
        "channels": stream.channels,
        "bit_rate": stream.bit_rate or result.bit_rate,
    }


__all__ = [
    "MediaDependencyError",
    "MediaInspectionError",
    "MediaProbe",
    "MediaProbeError",
    "MediaProbeResult",
    "MediaStreamInfo",
    "get_audio_info_from_bytes_async",
    "get_image_info_from_bytes",
    "get_image_info_from_tempfile",
    "get_video_info_from_bytes",
    "get_video_info_from_bytes_async",
    "get_video_info_from_tempfile",
    "guess_content_type",
    "inspect_image_bytes",
    "inspect_image_bytes_async",
    "inspect_video_bytes_async",
    "probe_media_bytes",
]
