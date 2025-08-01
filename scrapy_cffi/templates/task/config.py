platform = 0
concurrent_quantity = 20
max_req_timeout = 30
task_params = ["some_action", "collect"]
publish_baseurl = "http://127.0.0.1:8002/files"
get_task_url = "http://127.0.0.1:8002/task"
update_result_url = "http://127.0.0.1:8002/update"
proxies = {"http": "proxy_url", "https": "proxy_url"}
headers = {
    "Authorization": "Authorization",
    "Content-Type": "application/json"
}
