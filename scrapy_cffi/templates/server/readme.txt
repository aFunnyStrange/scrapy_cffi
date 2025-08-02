Note: In run_all_spiders mode, all spiders share the same scheduler instance. 
As a result, different spiders from separate tasks may compete for the same queue of tasks. 
Please ensure that you understand this behavior and use run_all_spiders mode appropriately.

Example: Suppose one spider relies on WebSocket communication and submits a request with 
an associated callback expecting a specific response. If the scheduler deduplicates the request 
and another spider’s engine processes it instead, the response may be delivered to the wrong spider. 
This can result in the WebSocket-based spider never receiving the expected response and continuously 
listening, causing the program to hang indefinitely.

1.start all server in dir "demo_server"
2.run runner.py