import random
from demo_support.endpoints import DEMO_HTTP_URL
from scrapy_cffi.spiders import Spider
from scrapy_cffi.internet import HttpRequest, HttpResponse
from copy import deepcopy

class StudentSpider(Spider):
    name = "student"
    robot_scheme = "http"
    allowed_domains = ["127.0.0.1", "localhost"]

    school_id = int(random.random() * 100)
    count = 0
    start_urls = [f"{DEMO_HTTP_URL}/school/{school_id}"]

    async def parse(self, response: HttpResponse):
        response_json = response.json()
        if response_json.get("data", []):
            class_list = response_json["data"]
            for s_class in class_list:
                class_id = s_class["class_id"]
                student_ids = s_class["student_ids"]
                for tid in student_ids:
                    # The backend server is a minimal mock service with poorly designed APIs.
                    # To avoid accidental ID deduplication (e.g., overlapping student IDs across classes),
                    # we construct a unique absolute ID by combining class_id and student_id.
                    # This ensures IDs are distinct even if the original IDs are reused.
                    abs_tid = self.count + class_id * 100 + tid
                    yield HttpRequest(
                        session_id=response.session_id,
                        url=f"{DEMO_HTTP_URL}/student/{abs_tid}",
                        method="GET",
                        callback=self.parse_student,
                        errback=self.errRet,
                        meta=deepcopy({"class_id": class_id, "student_id": abs_tid})
                    )

            has_next = response_json.get("has_next")
            if has_next:
                self.count += 1000000
                yield HttpRequest(
                    session_id=response.session_id,
                    url=self.start_urls[0],
                    method="GET",
                    params={"cursor": response_json["cursor"]},
                    callback=self.parse,
                    errback=self.errRet
                )
        else:
            print(response.json())
    
    async def parse_student(self, response: HttpResponse):
        meta = response.meta
        response_json = response.json()
        meta.update({"student_info": response_json})

        img_url = f'{DEMO_HTTP_URL}{response_json["img"]}'
        yield HttpRequest(
            session_id=response.session_id,
            url=img_url,
            callback=self.collect_data,
            errback=self.errRet,
            meta=deepcopy(meta)
        )

    async def collect_data(self, response: HttpResponse):
        meta = response.meta
        response_content = response.content
        meta["student_info"]["t_pic_data"] = response_content
        yield meta
