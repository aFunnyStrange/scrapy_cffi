import sys, warnings
from pathlib import Path
import importlib.util
from types import ModuleType
from typing import Optional, TYPE_CHECKING, List
if TYPE_CHECKING:
    from ..models.api import CPYExtension

class CExtensionLoader:
    def __init__(self, resource_dir: Optional[Path] = None):
        self.user_base = (Path(sys.argv[0]).parent / resource_dir) if resource_dir else None
        self.framework_base = Path(__file__).parent / "cpy_resources"

    def _load_py_module(self, path: Path, module_name: str) -> ModuleType:
        spec = importlib.util.spec_from_file_location(module_name, path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    def _load_ctypes_wrapper(self, wrapper_path: Path) -> ModuleType:
        # wrapper.py 内部负责 ctypes 动态库加载
        spec = importlib.util.spec_from_file_location(wrapper_path.stem, wrapper_path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    def _try_load_path(self, path: Path, cfg: "CPYExtension") -> Optional[ModuleType]:
        # 1. wrapper.py
        wrapper_path = path / (cfg.wrapper or "wrapper.py")
        if wrapper_path.exists():
            try:
                return self._load_ctypes_wrapper(wrapper_path)
            except Exception as e:
                pass

        # 2. fallback.py
        fallback_path = path / (cfg.fallback or "fallback.py")
        if fallback_path.exists():
            try:
                return self._load_py_module(fallback_path, cfg.module_name)
            except Exception as e:
                pass

        return None

    def load_module(self, cfg: "CPYExtension") -> Optional[ModuleType]:
        paths_to_try = []
        module_folder = cfg.module_name

        if self.user_base:
            paths_to_try.append(self.user_base / module_folder)
        if self.framework_base:
            paths_to_try.append(self.framework_base / module_folder)

        for path in paths_to_try:
            module = self._try_load_path(path, cfg)
            if module:
                return module

        warnings.warn(f"Cannot load module {cfg.module_name} from user or framework directories.")
        return None

    def load_all(self, configs: List["CPYExtension"], inject_globals=True) -> dict[str, Optional[ModuleType]]:
        loaded = {}
        for cfg in configs:
            mod = self.load_module(cfg)
            name = cfg.resource_name or cfg.module_name
            loaded[name] = mod
            if inject_globals and mod:
                globals()[name] = mod
                sys.modules[name] = mod
        return loaded
