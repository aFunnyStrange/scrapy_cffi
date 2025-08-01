# just a simple server for the demo project, without using the static dir.
import uvicorn, random, time, string
from fastapi import FastAPI, Request, HTTPException, Response
from fastapi.responses import PlainTextResponse, JSONResponse

app = FastAPI()

@app.exception_handler(HTTPException)
async def custom_http_exception_handler(request: Request, exc: HTTPException):
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "data": [],
            "msg": exc.detail,
            "re_code": exc.status_code,
            "success": False,
        },
    )

def random_cookie():
    return ''.join(random.choices(string.ascii_letters + string.digits, k=50))

@app.get("/")
async def get_root(request: Request, response: Response):
    query_params = dict(request.query_params)
    response.set_cookie(key="demo_cookie", value=random_cookie(), httponly=True, path="/")
    return {"method": "GET", "params": query_params}

@app.get("/robots.txt", response_class=PlainTextResponse)
async def robot_url(request: Request):
    has_rebots = 1 if random.random() < 0.6 else 0
    if has_rebots:
        allow_all = 1 if random.random() < 0.6 else 0
        if allow_all:
            return ""
        return random.choice([
            "User-agent: *\nDisallow: /", 
            "User-agent: *\nDisallow: /teacher", 
            "User-agent: *\nDisallow: /student", 
            "User-agent: *\nDisallow: /files", 
        ])
    else:
        raise HTTPException(status_code=404, detail="not found")

def random_task_id():
    return int(str(time.time() + random.random() * 10 + random.random() * 100).replace(".", ""))

def random_str():
    return ''.join(random.choices(string.ascii_letters, k=random.randint(6, 20)))

@app.get("/task")
async def get_tasks(request: Request, response: Response):
    response.set_cookie(key="demo_cookie", value=random_cookie(), httponly=True, path="/")
    has_task = 1 if random.random() < 0.8 else 0
    task_type = request.query_params.get("type")
    if has_task:
        if task_type == "collect":
            small_task_type = random.choice(["school_collect", "teacher_collect", "student_collect"])
        elif task_type == "some_action":
            small_task_type = task_type
        else:
            return {"data": {"details": [], "platform": 0, "task_type": "task_type"}, "msg": "fail", "success": False}
        tasks_list = []
        tasks_count = random.randint(2, 5)
        # tasks_count = random.randint(10, 100)
        if small_task_type == "school_collect":
            task_key = "school_id"
        elif small_task_type == "teacher_collect":
            task_key = "teacher_id"
        elif small_task_type == "student_collect":
            task_key = "student_id"
        else:
            task_key = "action_id"
        for i in range(tasks_count):
            tasks_list.append({
                'small_task_id': random_task_id(), 
                'smail_task_type': small_task_type, 
                'small_task_info': {task_key: random.randint(30, 150), "extra_data": random_str()}
            })
        return {
            'data': {
                'details':tasks_list, 
                'platform': 0, 
                'task_id': random_task_id(), 
                'task_type': task_type
            }, 
            'msg': 'success', 're_code': 0, 'success': True
        }
    else:
        return {"data": {"details": [], "platform": 0, "task_type": task_type}, "msg": "success", "success": True}

@app.post("/update")
async def update_result(request: Request):
    try:
        data = await request.json()
        return {"data": {"details": [], "platform": 0}, "msg": "success", "success": True}
    except BaseException as e:
        return {"data": {"details": [], "platform": 0}, "msg": "fail", "success": False}

@app.get("/files/{img}", response_class=PlainTextResponse)
async def files_url(img: str, request: Request, response: Response):
    random_bytes = bytes([random.randint(0, 255) for _ in range(1024)])
    response.set_cookie(key="demo_cookie", value=random_cookie(), httponly=True, path="/")
    return Response(content=random_bytes, media_type="image/png")

def random_ids(start: int, end: int) -> list[int]:
    ids = []
    count = random.randint(start, end)
    for i in range(count):
        ids.append(i)
    return ids

@app.get("/school/{school_id}")
async def school_url(request: Request, school_id: int, response: Response):
    response.set_cookie(key="demo_cookie", value=random_cookie(), httponly=True, path="/")
    status = 1 if random.random() < 0.8 else 0
    if status and school_id > 0:
        has_next = 1 if random.random() < 0.6 else 0
        cursor = ""
        if has_next:
            cursor = f'{random_str()}{random_str()}{random_str()}'
        school_id += random.randint(100, 300)
        data_count = random.randint(10, int(str(school_id)[:2]))
        data_list = []
        for i in range(data_count):
            data_list.append({"class_id": i, "teacher_ids": random_ids(1, 5), "student_ids": random_ids(30, 50), "has_next": has_next, "cursor": cursor})
        return {"data": data_list, "msg": "success", "success": True}
    else:
        raise HTTPException(status_code=404, detail="not found")

@app.get("/teacher/{teacher_id}")
async def teacher_url(request: Request, teacher_id: int, response: Response):
    response.set_cookie(key="demo_cookie", value=random_cookie(), httponly=True, path="/")
    return {"teacher_id": teacher_id, "name": random_str(), "age": random.randint(6, 25), "gender": random.choice(["man", "lady"]), "img": f"/files/{random.randint(50000, 90000)}.png"}

@app.get("/student/{student_id}")
async def student_url(request: Request, student_id: int, response: Response):
    response.set_cookie(key="demo_cookie", value=random_cookie(), httponly=True, path="/")
    return {"student_id": student_id, "name": random_str(), "age": random.randint(6, 25), "gender": random.choice(["boy", "girl"]), "img": f"/files/{random.randint(50000, 90000)}.png"}

if __name__ == "__main__":
    uvicorn.run("fastApiServer:app", port=8002, reload=True) # debug=True