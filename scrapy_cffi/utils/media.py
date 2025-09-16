import tempfile, os
try:
    import magic
except ImportError as e:
    raise ImportError(
        "Missing magic dependencies. "
        "Please install one of the following according to your platform:\n"
        "  Windows: pip install scrapy_cffi[windows]\n"
        "  Linux/macOS: pip install scrapy_cffi[unix]"
    ) from e

try:
    from PIL import Image
except ImportError as e:
    raise ImportError(
        "Missing Pillow dependencies. "
        "Please install: pip install Pillow"
    ) from e

try:
    from hachoir.parser import createParser
    from hachoir.metadata import extractMetadata
except ImportError as e:
    raise ImportError(
        "Missing hachoir dependencies. "
        "Please install: pip install hachoir"
    ) from e
from typing import Union

def guess_content_type(byte_data: bytes) -> str:
    try:
        max_byte_index = 2048
        if len(byte_data) < max_byte_index:
            max_byte_index = len(byte_data)
        mime = magic.Magic(mime=True)
        mime_type = mime.from_buffer(byte_data[:max_byte_index])
        return mime_type
    except Exception as e:
        return f"Failed to guess: {e}"
    
def get_image_info_from_bytes(image_bytes: bytes) -> Union[dict, str]:
    try:
        from PIL import Image
        from io import BytesIO
        with Image.open(BytesIO(image_bytes)) as img:
            image_info = {
                "format": img.format,
                "mode": img.mode,
                "width": img.width,
                "height": img.height,
            }
            return image_info
    except Exception as e:
        return f"Failed to read image: {e}"
    
def get_video_info_from_bytes(video_bytes: bytes) -> Union[dict, str]:
    import subprocess, json
    try:
        subprocess.run(["ffprobe", "-version"], stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)
    except (FileNotFoundError, subprocess.CalledProcessError) as e:
        raise RuntimeError(
            "Missing ffprobe executable. Please install FFmpeg (which includes ffprobe) on your system:\n"
            "  Linux: sudo apt install ffmpeg\n"
            "  macOS: brew install ffmpeg\n"
            "  Windows: Download from https://ffmpeg.org/download.html and add to PATH"
        ) from e

    try:
        cmd = [
            "ffprobe",
            "-v", "error",
            "-print_format", "json",
            "-show_streams",
            "-show_format",
            "-"
        ]
        result = subprocess.run(cmd, input=video_bytes, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        if result.returncode != 0:
            return f"ffprobe failed: {result.stderr.decode('utf-8')}"
        
        info = json.loads(result.stdout)
        video_stream = next((s for s in info.get("streams", []) if s.get("codec_type") == "video"), None)
        if not video_stream:
            return "No video stream found"

        width = int(video_stream.get("width", 0))
        height = int(video_stream.get("height", 0))
        duration = float(info.get("format", {}).get("duration", 0))

        return {"width": width, "height": height, "duration": duration}
    except Exception as e:
        return f"Failed to read video: {e}"
    
def get_image_info_from_tempfile(image_bytes: bytes) -> Union[dict, str]:
    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as temp:
        temp.write(image_bytes)
        temp_path = temp.name

    try:
        with Image.open(temp_path) as img:
            image_info = {
                "format": img.format,
                "mode": img.mode,
                "width": img.width,
                "height": img.height,
            }
            return image_info
    except Exception as e:
        return f"Failed to read image: {e}"
    finally:
        try:
            os.remove(temp_path)
        except Exception as e:
            print(f"Failed to delete temporary file: {e}")

def get_video_info_from_tempfile(video_bytes: bytes) -> Union[dict, str]:
    with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as temp:
        temp.write(video_bytes)
        temp_path = temp.name
    try:
        parser = createParser(temp_path)
        if not parser:
            return "Failed to parse video"
        metadata = extractMetadata(parser)
        if not metadata:
            return "Failed to extract video metadata"
        
        video_info = {}
        if metadata.has("duration"):
            video_info["duration"] = metadata.get("duration").total_seconds()
        else:
            return "Failed to get video duration"
        
        if metadata.has("width") and metadata.has("height"):
            video_info["width"] = metadata.get("width")
            video_info["height"] = metadata.get("height")
        else:
            return "Failed to get video resolution"
        return video_info
    finally:
        try:
            if parser and parser.stream:
                parser.stream.close()
        except Exception:
            pass
        try:
            os.remove(temp_path)
        except Exception as e:
            print(f"Failed to delete temporary file: {e}")
