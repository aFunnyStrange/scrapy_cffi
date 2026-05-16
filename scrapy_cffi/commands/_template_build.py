from pathlib import Path
from typing import Iterable, Optional
import shutil


TEXT_SUFFIXES = {
    ".py",
    ".md",
    ".txt",
    ".yml",
    ".yaml",
    ".toml",
    ".ini",
    ".j2",
    ".json",
    ".html",
    ".htm",
    ".css",
    ".js",
    ".sh",
}


def read_text_template(path: Path) -> str:
    raw = path.read_bytes()
    if not raw:
        return ""
    if raw.startswith(b"\xff\xfe") or raw.startswith(b"\xfe\xff"):
        return raw.decode("utf-16")
    if raw.startswith(b"\xef\xbb\xbf"):
        return raw[3:].decode("utf-8")
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError:
        return raw.decode("utf-16-le")


def write_utf8_file(path: Path, text: str) -> None:
    text_lf = text.replace("\r\n", "\n").replace("\r", "\n")
    path.write_bytes(text_lf.encode("utf-8"))


def copytree_merge_text_safe(src: Path, dst: Path, skip_files: Optional[Iterable[str]] = None) -> None:
    src = Path(src)
    dst = Path(dst)
    skip = set(skip_files or [])
    if not src.is_dir():
        raise ValueError(f"not a directory: {src}")
    if not dst.exists():
        dst.mkdir(parents=True)

    for item in src.iterdir():
        if item.name in skip:
            continue
        src_path = src / item.name
        dst_path = dst / item.name
        if src_path.is_dir():
            copytree_merge_text_safe(src_path, dst_path, skip_files=skip)
            continue
        if src_path.suffix.lower() in TEXT_SUFFIXES:
            write_utf8_file(dst_path, read_text_template(src_path))
        else:
            shutil.copy2(src_path, dst_path)
