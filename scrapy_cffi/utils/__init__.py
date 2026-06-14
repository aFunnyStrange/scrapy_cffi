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

from ._exports import __all__, resolve_utils_export


def __getattr__(name: str):
    return resolve_utils_export(name)


def __dir__():
    return list(__all__)
