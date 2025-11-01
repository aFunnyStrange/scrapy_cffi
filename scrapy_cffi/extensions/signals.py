# Core Component Signals
engine_started = object() # Engine started          SignalInfo(signal_time=time.time())
engine_stopped = object() # Engine stopped          SignalInfo(signal_time=time.time())
scheduler_empty = object() # Scheduler is empty     SignalInfo(signal_time=time.time())
task_error = object() # Task failed                 SignalInfo(signal_time=time.time(), reason=result)

# Spider Lifecycle Signals
spider_opened = object() # Spider opened     SignalInfo(spider: Spider, signal_time=time.time())
spider_closed = object() # Spider closed     SignalInfo(spider: Spider, signal_time=time.time())
spider_error = object() # Spider error       SignalInfo(response: Response, exception: BaseException, spider: Spider, signal_time=time.time())

# Request Scheduling Signals
request_scheduled = object() # Request successfully scheduled   SignalInfo(signal_time=time.time(), request=request)
request_dropped = object() # Request was dropped                SignalInfo(signal_time=time.time(), request=request, reason: str)

# Downloader Signals
request_reached_downloader = object() # Request sent to downloader  SignalInfo(signal_time=time.time(), request=request)
response_received = object() # Response received                    SignalInfo(signal_time=time.time(), request=request, response=response)

# Item Pipeline Signals
item_scraped = object() # Item scraped successfully         SignalInfo(signal_time=time.time(), item: Item, spider: Spider)
item_dropped = object() # Item was dropped                  SignalInfo(signal_time=time.time(), item: Item, reason: str)
item_error = object() # Exception during item processing    SignalInfo(signal_time=time.time(), item: Item, exception: BaseException)