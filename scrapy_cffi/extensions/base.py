from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from ..hooks.signals import SignalsHooks

class Extension:
    def __init__(self, hooks: "SignalsHooks", **kwargs):
        self.hooks = hooks
        self.resources = kwargs.get("resources")

    @classmethod
    def from_crawler(cls, hooks: "SignalsHooks", **kwargs):
        return cls(hooks=hooks, **kwargs)
