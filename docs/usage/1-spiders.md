## 1.Base Config
#### 1.1 Attributes
Each spider class includes several built-in attributes by default:
| Attribute | Description |
| --------- | ----------- |
| name | A unique identifier for the current spider, typically used to trace the source of produced items. |
| robot_scheme | Protocol used for requesting `robots.txt` when obeying robots rules (`http` or `https`). |
| allowed_domains | List of allowed domain names. **Note: initial requests will NOT be restricted by `allowed_domains`.** |
| settings | The `SettingsInfo` object passed in at spider startup. |
| run_py_dir | A `Path` object representing the directory path of the executing `.py` script. |
| session_id | Defaults to an empty string; used to assign a specific session ID per spider. |
| ctx_dict | Stores all loaded JavaScript execution contexts (as specified by `js_path`). Keys are filenames, values are context objects. |
| hooks | An object holding all framework-registered hook plugins as attributes. It serves as a centralized entry point for spiders to access various extension hooks exposed by the framework. This allows loose coupling and future extensibility without directly exposing internal components. "See "Hook Usage" section. |
---
#### 1.2 Methods
Every spider will include the following instance methods by default:
###### 1.2.1 use_execjs
Execute JavaScript via PyExecJS and return the result.
- **Parameters**: 
    **ctx_key**: **str**, the name of the JS file (without suffix)
    **funcname**: **str**, the name of the function to call
    **params**: **tuple**, positional arguments; must pass a tuple even if no parameters
- **Returns**: The result returned by executing the JS function
Example: given a loaded file `demo.js`:
``` js 
function count(a, b) {return a + b + 1;}
function rand() {return Math.random();}
```
Usage:
```python 
# With arguments
self.use_execjs(ctx_key="demo", funcname="count", params=(1, 2)) # => 4
# No arguments
self.use_execjs(ctx_key="demo", funcname="rand", params=(,)) # => e.g. 0.04188...
```
###### 1.2.2 parse
The default callback for handling responses from start_urls. Must be implemented by user, otherwise raises:
```python 
raise NotImplementedError("parse is not defined.")
```

###### 1.2.3 errRet
The default error handler. If a request has an errback set, this method will be used by default.

---

`scrapy_cffi` provides two spider base classes: `Spider` and `RedisSpider`, consistent with Scrapy's design — one class per spider.
## 2.Spider Mode
#### 2.1 Spider
###### 2.1.1 start_urls
- **Type**: List[str]
- **Description**: List of URLs used to construct and dispatch initial requests.
#### 2.2 RedisSpider
###### 2.2.1 redis_key
- **Type**: str
- **Description**: The name of the Redis queue from which tasks (URLs) are pulled and scheduled.

## 3.Spider Output
`scrapy_cffi` llows spider methods to yield or return any of the following supported types.
#### 3.1 When using `async def`
###### 3.1.1 Basic Types
**Request, Item, Dict, BaseException、None**
```python
async def parse(self, response: Union[HttpResponse, WebsocketResponse]):
    yield HttpRequest(...)
    yield Item(...)
    yield ValueError(...)
    yield {...}
    yield None
```
Also supports direct `return` of one object (equivalent to one `yield`):
```python
async def parse(self, response: Union[HttpResponse, WebsocketResponse]):
    if ...:
        return HttpRequest(...)
```
###### 3.1.2 Iterable Containers
**List, Tuple**
```python
async def parse(self, response):
    return [HttpRequest(...), Item(...)]
```
###### 3.1.3 Async Generator (recommended)
**types.AsyncGeneratorType, AsyncIterable**
```python
async def parse(self, response: Union[HttpResponse, WebsocketResponse]):
    if ...:
        yield HttpRequest(...)
    yield WebsocketRequest(...)

    async for req in self.create_req():
        yield req
```
#### 3.2 When using `def`
###### 3.2.1 Basic Types
```python
def parse(self, response: Union[HttpResponse, WebsocketResponse]):
    return HttpRequest(...)
```
###### 3.2.2 Iterable Containers
```python
def parse(self, response: Union[HttpResponse, WebsocketResponse]):
    return [Item(...), HttpRequest(...)]
```
###### 3.2.3 Generator
**types.GeneratorType, Iterable**
```python
def parse(self, response):
    for req in self.create_req():
        yield req
```

## 4.Hook Usage
Framework hooks allow you to interact with specific subsystems of the crawler (such as the session manager or scheduler) **without accessing their internal implementations directly**. These hooks are dynamically injected into each spider and are accessible via the `self.hooks` attribute.
Hooks are designed to provide **controlled extensibility**, enabling plugin-style behavior while preserving encapsulation.
#### 4.1 register_sessions
Registers multiple user sessions (typically cookie dicts) under a single logical group called a `session_id`. Once registered, any request using that `session_id` will **randomly rotate** among the associated sessions.

**Purpose:**
- Simulate multiple user identities.
- Rotate between different cookie pools for login-required pages.
- Avoid frequent login requests.

**Usage:**
```python 
# Register multiple cookie sessions
session_id = self.hooks.session.register_sessions({
    "user1": "cookies_dict1",
    "user2": "cookies_dict2",
    "user3": "cookies_dict3",
    "user4": "cookies_dict4"
})
# Use that session_id in requests
yield HttpRequest(
    session_id=session_id,
    ...
)
```

**Behind the scenes:**
- `session.register_sessions()` passes a mapping of `session_key -> cookies_dict` to the framework’s internal session manager.
- It returns a unique `session_id` representing this logical group.
- When a request is sent using this `session_id`, a random session from the group is selected.
- Multiple session groups can coexist and be used independently within the same spider.

**Notes on Hook Design**
- Hooks are grouped by **component responsibility**, such as `self.hooks.session`, etc.
- Each hook exposes only **selected callable features**, not direct access to core internals.
- This design ensures:
    - Clean separation of concerns.
    - Safe and controlled interaction with internal components.
    - Easier extensibility through external plugins.





## 5.Advanced Usage
#### 5.1 Override `start` method
All initial requests go through the `start` method. You may customize logic here.
**Note**: `start` must be defined as an async generator function.
###### 5.1.1 post requests
```python
async def start(self, *args, **kwargs):
    for url in self.start_urls:
        yield HttpRequest(
            session_id=self.session_id,
            url=url,
            method="POST",
            headers=self.settings.DEFAULT_HEADERS,
            data={...}
            cookies=self.settings.DEFAULT_COOKIES,
            proxies=self.settings.PROXIES,
            timeout=self.settings.TIMEOUT,
            dont_filter=self.settings.DONT_FILTER,
            callback=self.parse, 
            errback=self.errRet
        )
```
###### 5.1.2 Task Spider
```python
async def start(self, task_data, *args, **kwargs):
    for task in task_data:
        yield HttpRequest(
            session_id=self.session_id,
            url=task["url"],
            method=task["method"],
            headers=task["headers"],
            data=task["data"]
            cookies=task["cookies"],
            proxies=self.settings.PROXIES,
            timeout=self.settings.TIMEOUT,
            dont_filter=self.settings.DONT_FILTER,
            callback=self.parse, 
            errback=self.errRet
        )
```
Then you can run with:
```python 
scrapy_cffi.run_spider(settings, task_data=task_data)
```

#### 5.2 Use Redis Task Data
Similar to `scrapy-redis`, override `make_request_from_data`.
**Note**: Must be defined as an `async def.` If you want generator-style behavior, override `start` too.
```python 
async def make_request_from_data(self, data: bytes):
    task_data = data.decode('utf-8') # decode using same format used to enqueue
    task_data = json.loads(task_data)
    return HttpRequest(
        url=task_data["url"],
        method=task_data["method"],
        headers=task_data["headers"],
        data=task_data["data"]
        cookies=task_data["cookies"],
        proxies=self.settings.PROXIES,
        timeout=self.settings.TIMEOUT,
        dont_filter=self.settings.DONT_FILTER,
        callback=self.parse, 
        errback=self.errRet
    )
```

#### 5.3 Blocking Async Generator
In real-world asynchronous crawling scenarios, it's often necessary to dispatch a batch of requests and then collect their results in order to decide whether to proceed with the next step. To support this kind of **result-driven task control**, the framework provides a utility class called `ResultHolder`.

The usage pattern is as follows:
- 1.When constructing a request, the user creates a `ResultHolder` instance for each request and passes it through the request's `meta` field to the callback;
- 2.In the callback function, the user must **explicitly call** `holder.set_result(...)` to set the processing result of that request;
- 3.In the main logic, the user can use `await asyncio.gather(...)` to wait for all results from the `ResultHolder` instances. This will **pause the execution of the async generator**, until all responses are completed and their results are properly set.

Because the generator is paused while awaiting these results, it exhibits a certain **blocking behavior**, which is why we refer to it as a blocking async generator. The next-stage requests can only be generated **after all sub-tasks have completed**.

This mechanism is particularly useful in scenarios where a unified decision must be made after aggregating the results of multiple requests, such as:
- Generating a final upload request after all subtasks succeed;
- Interrupting the entire flow when any subtask fails;
- Aggregating multiple subtask results to construct the next-stage request payload.
This design allows the user to implement **synchronous-style flow control within an async generator**, making the task logic more explicit, the result dependencies clearer, and avoiding deeply nested callbacks or complex state machines.

✅ **Typical Use Cases:**
- Distributed data collection, where each subtask result needs to be aggregated for final output;
- Multi-interface login or verification flows where each API result influences the decision to continue;
- Multi-stage workflows with task dependencies, where the next stage should only start after a batch of subtasks completes.

💡 **Why “Blocking Async Generator”?**
Although the generator itself is asynchronous (i.e., it yields asynchronous requests), the presence of `await asyncio.gather(...)` introduces **pauses in execution** at certain stages, where the generator waits for all async results to complete before continuing.

We describe this behavior as blocking, but it's not a thread-level blocking — rather, it's a **controlled pause at the event loop level** using `await`.

This control pattern maintains the benefits of asynchronous concurrency, while still supporting scenarios that require strict result consistency. It is well-suited for building complex data-dependent task flows.


Full Example:
```python 
from scrapy_cffi.utils import ResultHolder

class DemoSpider(Spider):
    ...
    # Simulated input task list with two types: type 1 (simple) and type 2 (result-driven)
    tasks_list = [
        BigTask(task_type=1, task_info=[SmallTask(...), SmallTask(...)]), 
        BigTask(task_type=1, task_info=[SmallTask(...), SmallTask(...)]), 
        BigTask(task_type=1, task_info=[SmallTask(...), SmallTask(...)]), 
        BigTask(task_type=2, task_info=[SmallTask(...), SmallTask(...)])
        BigTask(task_type=2, task_info=[SmallTask(...), SmallTask(...)])
        BigTask(task_type=2, task_info=[SmallTask(...), SmallTask(...)])
    ]

    async def parse(self, response: Union[HttpResponse, WebSocketResponse]):
        # Stream all yielded requests from the task generator
        async for req in self.create_tasks(response=response):
            yield req

    async def create_tasks(
        self, 
        response: Union[HttpResponse, WebSocketResponse]
    ) -> AsyncIterable[Union[HttpResponse, WebSocketResponse]]:
        try:
            for task_data in self.tasks_list:
                task_data: BigTaskData
                if task_data.task_type == 1:
                    # Type 1: fire-and-forget, directly yield requests
                    for small_task_info in task_data.task_info:
                        ...
                        yield HttpRequest(...)
                elif task_data.task_type == 2:
                    # Type 2: result-driven, needs to gather all subtask results
                    holders: List[ResultHolder] = []
                    for small_task_info in task_data.task_info:
                        # Create a ResultHolder and bind it to each request
                        holder = ResultHolder()
                        holders.append(holder)
                        # Each request carries its own ResultHolder
                        yield self.create_task2_req(response, holder, small_task_info)

                    # Wait until all ResultHolder instances have their results
                    holders_result = await asyncio.gather(*(h.get_result() for h in holders))

                    gather_list = []
                    for single_res in holders_result:
                        # Check result validity
                        if not single_res.get("status") == 1:
                            raise ResponseError(exception=ValueError(single_res), request=None)
                        gather_list.append(single_res["data"])

                    # All subtasks succeeded, construct final request using aggregated data
                    final_data = {
                        "gather_list": gather_list,
                        ...
                    }
                    ...
                    yield HttpRequest(...)
        except Exception as e:
            # Yield an error signal if something goes wrong
            yield {"status": -1, ...}

    def create_task2_req(
        self, 
        response: WebSocketResponse, 
        holder: ResultHolder, 
        small_task_info: SmallTask, ...
    ):
        # Create intermediate request carrying holder for later result setting
        ...
        return HttpRequest(
            ...,
            meta={
                "holder": holder, # Pass holder via meta
                ...
            },
            callback=self.parse_task2_result,
            errback=self.errRet
        )

    def parse_task2_result(self, response: HttpResponse):
        try:
            holder: ResultHolder = response.meta["holder"]
            if ...:
                # Mark result as success
                holder.set_result({"status": 1, "data": ...})
            else:
                # Mark result as partial/failure
                holder.set_result({"status": 0, "data": ...})
        except Exception as e:
            # Ensure result is set even if an error occurred
            holder.set_result({"status": -1, "data": ...})
```