import asyncio

from .redis import RedisSpider
from ..core.downloader.internet import Request


class KafkaSpider(RedisSpider):
    """Consumes start requests from Kafka and schedules follow-ups to Kafka."""

    name = "kafkaSpider"
    kafka_topic = None
    kafka_start_topic = None
    kafka_group = None
    kafka_start_group = None

    async def start(self, *args, **kwargs):
        accepted_count = 0
        while not self.stop_event.is_set():
            get_req_task = asyncio.create_task(self.hooks.scheduler.get_start_req(spider=self))
            stop_task = asyncio.create_task(self.stop_event.wait())
            tasks = {get_req_task, stop_task}
            try:
                done, pending = await asyncio.wait(
                    tasks,
                    return_when=asyncio.FIRST_COMPLETED,
                )
            except asyncio.CancelledError:
                for task in tasks:
                    task.cancel()
                await asyncio.gather(*tasks, return_exceptions=True)
                raise
            for task in pending:
                task.cancel()
            if pending:
                await asyncio.gather(*pending, return_exceptions=True)
            if stop_task in done:
                await asyncio.gather(get_req_task, return_exceptions=True)
                break

            message = get_req_task.result()
            if message is None:
                continue
            if message.value.startswith(b"SCF1"):
                request = Request.from_bytes(message.value)
            else:
                request = await self.make_request_from_data(message.value)
            if request:
                self.hooks.scheduler.attach_start_req(request=request, message=message)
                yield request
                accepted_count += 1
                if self.start_request_limit_reached(accepted_count):
                    return
            else:
                await self.hooks.scheduler.ack_start_req(spider=self, message=message)


__all__ = ["KafkaSpider"]
