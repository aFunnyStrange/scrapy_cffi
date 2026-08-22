"""Define the minimal lifecycle shared by optional runtime extensions."""

from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from ..hooks.signals import SignalsHooks

class Extension:
    """Provide construction and optional asynchronous shutdown hooks."""

    def __init__(self, hooks: "SignalsHooks", **kwargs):
        """Retain stable hooks and the optional resource registry."""
        self.hooks = hooks
        self.resources = kwargs.get("resources")

    @classmethod
    def from_crawler(cls, hooks: "SignalsHooks", **kwargs):
        """Construct an extension from framework-owned capabilities."""
        return cls(hooks=hooks, **kwargs)

    async def close(self) -> None:
        """Release extension-owned background activity when present."""
