from pydantic import model_validator
from . import StrictValidatedModel
from typing import Optional, Union

class RedisInfo(StrictValidatedModel):
    REDIS_URL: Optional[str] = None
    HOST: Optional[str] = None
    PORT: Optional[Union[str, int]] = None
    DB: Optional[Union[str, int]] = None
    USERNAME: Optional[str] = None
    PASSWORD: Optional[str] = None

    @model_validator(mode="after")
    def assemble_redis_url(self) -> "RedisInfo":
        if self.HOST and self.PORT:
            auth_part = ""
            if self.USERNAME and self.PASSWORD:
                auth_part = f"{self.USERNAME}:{self.PASSWORD}@"
            elif self.PASSWORD:
                auth_part = f":{self.PASSWORD}@"
            db_part = self.DB if self.DB is not None else 0
            self.REDIS_URL = f"redis://{auth_part}{self.HOST}:{self.PORT}/{db_part}"
        return self
    
__all__ = [
    "RedisInfo"
]