from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from ..hooks.signals import SignalsHooks

class Extension:
    def __init__(self, hooks: "SignalsHooks", **kwargs):
        self.hooks = hooks
        self.redisManager = kwargs.get("redisManager")
        self.mysqlManager = kwargs.get("mysqlManager")
        self.mongodbManager = kwargs.get("mongodbManager")
        self.rabbitmqManager = kwargs.get("rabbitmqManager")
        self.kafkaManager = kwargs.get("kafkaManager")

    @classmethod
    def from_crawler(cls, hooks: "SignalsHooks", **kwargs):
        return cls(hooks=hooks, **kwargs)