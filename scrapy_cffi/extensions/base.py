from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from ..hooks.signals import SignalsHooks

class Extension:
    def __init__(self, hooks: "SignalsHooks"):
        self.hooks = hooks

    @classmethod
    def from_crawler(cls, hooks: "SignalsHooks"):
        extension_cls = cls(hooks)
        return extension_cls