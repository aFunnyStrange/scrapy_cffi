"""
Utility submodules for scrapy_cffi.

Recommended (tool / script) imports — only load what you need::

    from scrapy_cffi.utils.algorithm import do_sha1
    from scrapy_cffi.utils.jsonLoad import extract_json_chain
    from scrapy_cffi.utils.media import guess_content_type
    from scrapy_cffi.utils.envConfig import settings_to_env, env_to_settings
    from scrapy_cffi.utils.fd import FDUtil

Framework bootstrap (still available from barrel)::

    from scrapy_cffi.utils import load_object, init_logger, RobotsManager

Legacy barrel ``from scrapy_cffi.utils import X`` uses lazy ``__getattr__`` (see ``_exports``).
"""

from typing import TYPE_CHECKING, Any

from ._exports import __all__, resolve_utils_export

if TYPE_CHECKING:
    from .algorithm import create_uniqueId, do_otp, do_sha1, get_node
    from .common import (
        ResultHolder,
        async_context_factory,
        convert_to_toml,
        get_all_spiders_cls,
        get_all_spiders_name,
        get_class_name,
        get_or_create_loop,
        get_run_py_dir,
        load_object,
        load_settings_from_py,
        load_settings_with_path,
        run_with_timeout,
        setup_uvloop_once,
        to_scrapy_settings_py,
    )
    from .concurrency import (
        CallFunction,
        ProcessManager,
        ProcessTaskManager,
        ThreadFuture,
        run_coroutine_in_new_loop,
        run_coroutine_in_thread,
        safe_call,
    )
    from .email import Email
    from .envConfig import (
        env_to_settings,
        load_env_settings,
        settings_to_env,
    )
    from .fd import FDUtil
    from .jsonLoad import JSONExtractor, JSONScanner, extract_json_chain, extract_nested_objects
    from .log import (
        KafkaLoggingHandler,
        ShortNameFormatter,
        init_logger,
        init_logger_multiprocessing,
        start_multiprocess_log_listener,
    )
    from .protobuf import ProtobufFactory
    from .robot import RobotsManager, RobotsTxtRules, parse_robots_txt


def __getattr__(name: str) -> Any:
    """Resolve one legacy barrel export without eager-importing all utilities."""
    return resolve_utils_export(name)


def __dir__():
    """Return the complete lazy public surface for interactive tooling."""
    return list(__all__)
