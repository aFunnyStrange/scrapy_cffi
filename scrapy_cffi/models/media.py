"""Define transport-neutral image, video, and audio metadata models."""

from enum import IntEnum
from typing import Dict, Optional, Union

from pydantic import Field, model_validator

from .base import BaseValidatedModel


class MediaContentType(IntEnum):
    """Keep the historical numeric media discriminators stable."""

    VIDEO = 0
    IMAGE = 1
    AUDIO = 2


class MediaBaseModel(BaseValidatedModel):
    """Store common download and upload facts for one media object."""

    inner_mediaurl: str = Field(..., min_length=1, strict=True)
    media_size: Optional[int] = Field(default=None, ge=0, strict=True)
    media_data: Optional[bytes] = Field(default=None, strict=True)
    media_type: Optional[str] = Field(default=None, strict=True)
    upload_url: Optional[str] = Field(default=None, strict=True)
    upload_headers: Optional[Dict[str, Union[str, int]]] = Field(
        default=None,
        strict=True,
    )
    upload_data: Optional[bytes] = Field(default=None, strict=True)
    fill_text: Optional[str] = Field(default=None, strict=True)


class VideoInfo(MediaBaseModel):
    """Store video transfer facts while preserving the size requirement."""

    duration: Optional[float] = Field(default=None, ge=0)
    codec_name: Optional[str] = Field(default=None, strict=True)

    @model_validator(mode="after")
    def check_video_fields(self) -> "VideoInfo":
        """Require the historical positive video size contract."""
        if self.media_size is None or self.media_size <= 0:
            raise ValueError("Video must provide media_size > 0")
        return self


class PhotoInfo(MediaBaseModel):
    """Store image transfer facts."""


class AudioInfo(MediaBaseModel):
    """Store audio transfer facts and optional probe metadata."""

    duration: Optional[float] = Field(default=None, ge=0)
    codec_name: Optional[str] = Field(default=None, strict=True)
    sample_rate: Optional[int] = Field(default=None, gt=0, strict=True)
    channels: Optional[int] = Field(default=None, gt=0, strict=True)


class MediaInfo(BaseValidatedModel):
    """Require the image, video, or audio payload selected by content type."""

    content_type: int
    video_info: Optional[VideoInfo] = None
    photo_info: Optional[PhotoInfo] = None
    audio_info: Optional[AudioInfo] = None
    media_height: Optional[int] = Field(default=0, ge=0)
    media_width: Optional[int] = Field(default=0, ge=0)

    @model_validator(mode="after")
    def validate_media(self) -> "MediaInfo":
        """Require the payload matching the selected numeric media kind."""
        field_by_type = {
            MediaContentType.VIDEO: self.video_info,
            MediaContentType.IMAGE: self.photo_info,
            MediaContentType.AUDIO: self.audio_info,
        }
        try:
            content_type = MediaContentType(self.content_type)
        except ValueError as exc:
            raise ValueError(
                "Unknown content_type: %s" % self.content_type
            ) from exc
        if field_by_type[content_type] is None:
            required_field = {
                MediaContentType.VIDEO: "video_info",
                MediaContentType.IMAGE: "photo_info",
                MediaContentType.AUDIO: "audio_info",
            }[content_type]
            raise ValueError(
                "%s must be provided for content_type=%s"
                % (required_field, int(content_type))
            )
        return self


__all__ = [
    "AudioInfo",
    "MediaBaseModel",
    "MediaContentType",
    "MediaInfo",
    "PhotoInfo",
    "VideoInfo",
]
