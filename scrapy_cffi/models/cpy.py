from .base import StrictValidatedModel
from pydantic import BaseModel, Field
from typing import List, Optional
from pathlib import Path

class CPYExtension(StrictValidatedModel):
    module_name: str                   # Module name / folder name
    resource_name: Optional[str] = None  # Injected namespace name
    wrapper: Optional[str] = "wrapper.py" # Python wrapper filename
    fallback: Optional[str] = "fallback.py" # Fallback implementation filename
    build_dir: Optional[str] = "build"  # Directory for compiled shared libraries (ctypes wrapper)

class CPYExtensionsConfig(BaseModel):
    DIR: Path = Path("cpy_resources") # Root directory for all C extensions
    RESOURCES: List[CPYExtension] = Field(default_factory=list) # List of extension definitions