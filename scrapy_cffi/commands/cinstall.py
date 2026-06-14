"""
Install user-built ctypes C extension modules into the system cpy store.

Example::

    scrapy-cffi cinstall bloom --source ./cpy_resources/bloom
    scrapy-cffi cinstall --list
"""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import List, Optional

from ..cpy.scaffold import is_module_dir, scaffold_module
from ..cpy.paths import get_framework_cpy_root, get_system_cpy_root

NATIVE_SUFFIXES = {".dll", ".so", ".dylib", ".pyd"}


def _is_module_dir(path: Path) -> bool:
    return is_module_dir(path)


def _native_libs(build_dir: Path) -> List[Path]:
    if not build_dir.is_dir():
        return []
    out: List[Path] = []
    for p in build_dir.iterdir():
        if not p.is_file():
            continue
        if p.suffix.lower() in NATIVE_SUFFIXES:
            out.append(p)
    return out


def resolve_module_source(module_name: str, source: Optional[str] = None) -> Path:
    if source:
        src = Path(source).expanduser().resolve()
        if not _is_module_dir(src):
            raise FileNotFoundError(
                f"Source is not a cpy module directory (need wrapper.py or fallback.py): {src}"
            )
        return src

    project = Path.cwd() / "cpy_resources" / module_name
    if _is_module_dir(project):
        return project.resolve()

    framework = get_framework_cpy_root() / module_name
    if _is_module_dir(framework):
        return framework.resolve()

    raise FileNotFoundError(
        f"Cannot find module '{module_name}'. "
        f"Use --source PATH, place files under ./cpy_resources/{module_name}/, "
        f"or run: scrapy-cffi cinstall --init {module_name}"
    )


def copy_module_tree(src: Path, dst: Path, *, force: bool = False) -> None:
    if dst.exists():
        if not force:
            raise FileExistsError(
                f"Module already installed at {dst}. Use --force to overwrite."
            )
        shutil.rmtree(dst)
    shutil.copytree(
        src,
        dst,
        ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "*.pyo"),
    )


def list_installed() -> List[str]:
    root = get_system_cpy_root()
    if not root.is_dir():
        return []
    return sorted(
        p.name for p in root.iterdir() if p.is_dir() and _is_module_dir(p)
    )


def run(
    module_name: Optional[str] = None,
    *,
    source: Optional[str] = None,
    force: bool = False,
    list_modules: bool = False,
    show_path: bool = False,
    remove: Optional[str] = None,
    init: Optional[str] = None,
    require_binary: bool = False,
) -> None:
    if show_path:
        print(get_system_cpy_root())
        return

    if list_modules:
        root = get_system_cpy_root()
        names = list_installed()
        print(f"System cpy root: {root}")
        if not names:
            print("No modules installed.")
            return
        for name in names:
            libs = _native_libs(root / name / "build")
            tag = "native" if libs else "fallback-only"
            print(f"  {name} ({tag})")
        return

    if remove:
        target = get_system_cpy_root() / remove
        if not target.is_dir():
            print(f"Module not installed: {remove}")
            return
        shutil.rmtree(target)
        print(f"Removed: {target}")
        return

    if init:
        dst = Path.cwd() / "cpy_resources" / init
        if dst.exists() and not force:
            raise FileExistsError(
                f"Already exists: {dst}. Use --force to overwrite scaffold."
            )
        scaffold_module(init, dst, force=True)
        print(f"Scaffolded project module: {dst}")
        print("Build native libs into build/, then: scrapy-cffi cinstall", init)
        return

    if not module_name:
        raise SystemExit(
            "Usage: scrapy-cffi cinstall <module> [--source PATH]\n"
            "       scrapy-cffi cinstall --init <module>\n"
            "       scrapy-cffi cinstall --list | --path | --remove <module>"
        )

    src = resolve_module_source(module_name, source=source)
    build_dir = src / "build"
    natives = _native_libs(build_dir)
    if require_binary and not natives:
        raise FileNotFoundError(
            f"No native library in {build_dir}. "
            f"Expected lib*.dll / lib*.so / lib*.dylib (or use without --require-binary)."
        )

    root = get_system_cpy_root()
    root.mkdir(parents=True, exist_ok=True)
    dst = root / module_name
    copy_module_tree(src, dst, force=force)

    print(f"Installed '{module_name}' → {dst}")
    if natives:
        print("Native libraries:")
        for lib in natives:
            print(f"  {lib.name}")
    else:
        print(
            "Warning: no native library in build/ — runtime will use fallback.py "
            "until you rebuild and re-run cinstall."
        )
