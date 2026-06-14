"""
Scaffold ctypes C extension module directories for new projects.

Copies framework templates without native binaries in ``build/``.
"""

from __future__ import annotations

import os
import shutil
from pathlib import Path
from typing import Sequence

from .paths import get_framework_cpy_root

NATIVE_SUFFIXES = {".dll", ".so", ".dylib", ".pyd"}
MODULE_MARKERS = ("wrapper.py", "fallback.py")
DEFAULT_SCAFFOLD_MODULES: Sequence[str] = ("bloom",)

_CPY_README = """\
# cpy_resources

Optional ctypes C extension modules for this project.

Created by `scrapy-cffi startproject`. Each subfolder (e.g. `bloom/`) contains
`wrapper.py`, `fallback.py`, and an empty `build/` directory for your compiled
`.dll` / `.so` / `.dylib` files.

## Build & install

1. Compile native libs into `bloom/build/` (see `bloom/BUILD.md`).
2. Project-local use: keep binaries here — loader checks this directory first.
3. Machine-wide use: `scrapy-cffi cinstall bloom --require-binary`

Docs: scrapy_cffi docs `usage/12-cpython.md`.
"""


def is_module_dir(path: Path) -> bool:
    return path.is_dir() and any((path / name).exists() for name in MODULE_MARKERS)


def _scaffold_copy_ignore(dirpath: str, names: list[str]) -> set[str]:
    ignored: set[str] = set()
    if os.path.basename(dirpath) == "build":
        for name in names:
            if Path(name).suffix.lower() in NATIVE_SUFFIXES:
                ignored.add(name)
    for name in names:
        if name == "__pycache__" or name.endswith((".pyc", ".pyo")):
            ignored.add(name)
    return ignored


def copy_module_scaffold(src: Path, dst: Path, *, force: bool = False) -> None:
    if dst.exists():
        if not force:
            raise FileExistsError(
                f"Module directory already exists: {dst}. Use --force to overwrite."
            )
        shutil.rmtree(dst)
    shutil.copytree(src, dst, ignore=_scaffold_copy_ignore)


def scaffold_module(module_name: str, dst: Path, *, force: bool = False) -> Path:
    src = get_framework_cpy_root() / module_name
    if not is_module_dir(src):
        raise FileNotFoundError(f"No framework cpy template for module: {module_name}")
    dst.parent.mkdir(parents=True, exist_ok=True)
    copy_module_scaffold(src, dst, force=force)
    return dst


def scaffold_project_cpy_resources(
    project_dir: Path,
    modules: Sequence[str] = DEFAULT_SCAFFOLD_MODULES,
    *,
    force: bool = False,
) -> Path:
    cpy_root = project_dir / "cpy_resources"
    cpy_root.mkdir(parents=True, exist_ok=True)
    for name in modules:
        scaffold_module(name, cpy_root / name, force=force)
    readme = cpy_root / "README.md"
    if force or not readme.exists():
        readme.write_text(_CPY_README, encoding="utf-8")
    return cpy_root


__all__ = [
    "DEFAULT_SCAFFOLD_MODULES",
    "is_module_dir",
    "scaffold_module",
    "scaffold_project_cpy_resources",
]
