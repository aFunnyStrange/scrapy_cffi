from . import BaseValidatedModel
from pydantic import Field, model_validator
from typing import Optional, Union, Dict
    
# Base class for image/video
class MediaBaseModel(BaseValidatedModel):
    inner_mediaurl: str = Field(..., min_length=1, strict=True)
    media_size: Optional[int] = Field(default=None, strict=True)

    media_data: Optional[bytes] = Field(default=None, strict=True) # Raw bytes of the image/video
    media_type: Optional[str] = Field(default=None, strict=True) # MIME type of the image or video cover (e.g., "image/png")

    upload_url: Optional[str] = Field(default=None, strict=True)
    upload_headers: Optional[Dict[str, Union[str, int]]] = Field(default=None, strict=True)
    upload_data: Optional[bytes] = Field(default=None, strict=True)
    fill_text: Optional[str] = Field(default=None, strict=True)

class VideoInfo(MediaBaseModel):
    @model_validator(mode='after')
    def check_video_fields(self):
        if self.media_size is None or self.media_size <= 0:
            raise ValueError("Video must provide media_size > 0")
        return self

class PhotoInfo(MediaBaseModel):
    pass

class MediaInfo(BaseValidatedModel):
    content_type: int # 0 = video, 1 = image
    video_info: Optional[VideoInfo] = None
    photo_info: Optional[PhotoInfo] = None
    media_height: Optional[int] = 0 # Optional height of the uploaded image
    media_width: Optional[int] = 0 # Optional width of the uploaded image

    @model_validator(mode="after")
    def validate_media(self):
        if self.content_type not in [0, 1]:
            raise ValueError(f"Unknown content_type: {self.content_type}")
        if self.content_type == 0 and not self.video_info:
            raise ValueError("video_info must be provided for content_type=0 (video)")
        if self.content_type == 1 and not self.photo_info:
            raise ValueError("photo_info must be provided for content_type=1 (image)")
        return self
