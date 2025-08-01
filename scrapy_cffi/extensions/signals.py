# Core Component Signals
engine_started = object() # Engine started          SingalInfo(signal_time=time.time())
engine_stopped = object() # Engine stopped          SingalInfo(signal_time=time.time())
scheduler_empty = object() # Scheduler is empty     SingalInfo(signal_time=time.time())
task_error = object() # Task failed                 SingalInfo(signal_time=time.time(), reason=result)

# Spider Lifecycle Signals
spider_opened = object() # Spider opened     SingalInfo(spider: Spider, signal_time=time.time())
spider_closed = object() # Spider closed     SingalInfo(spider: Spider, signal_time=time.time())
spider_error = object() # Spider error       SingalInfo(response: Response, exception: BaseException, spider: Spider, signal_time=time.time())

# Request Scheduling Signals
request_scheduled = object() # Request successfully scheduled   SingalInfo(signal_time=time.time(), request=request)
request_dropped = object() # Request was dropped                SingalInfo(signal_time=time.time(), request=request, reason: str)

# Downloader Signals
request_reached_downloader = object() # Request sent to downloader  SingalInfo(signal_time=time.time(), request=request)
response_received = object() # Response received                    SingalInfo(signal_time=time.time(), request=request, response=response)

# Item Pipeline Signals
item_scraped = object() # Item scraped successfully         SingalInfo(signal_time=time.time(), item: Item, spider: Spider)
item_dropped = object() # Item was dropped                  SingalInfo(signal_time=time.time(), item: Item, reason: str)
item_error = object() # Exception during item processing    SingalInfo(signal_time=time.time(), item: Item, exception: BaseException)