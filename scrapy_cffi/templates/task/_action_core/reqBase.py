import asyncio, execjs, json, os
from scrapy_cffi.utils.media import guess_content_type
from scrapy_cffi.models.media import PhotoInfo, VideoInfo
from functools import wraps
from urllib.parse import urlencode
from curl_cffi import requests
from tenacity import retry, stop_after_attempt, wait_fixed, retry_if_exception_type
from typing import TYPE_CHECKING, Callable, Awaitable, Protocol, runtime_checkable, Literal
if TYPE_CHECKING:
    from curl_cffi.requests import Response

@runtime_checkable
class RetryCapable(Protocol):
    max_fail_count: int

# 死循环重试直到上限
def custom_retry(delay_retry_time=5):
    def decorator(func: Callable[..., Awaitable[dict]]):
        @wraps(func)
        async def wrapper(self: RetryCapable, *args, **kwargs):
            while True:
                result = await func(self, *args, **kwargs)
                if result.get("status"):
                    return result
                self.max_fail_count -= 1
                if self.max_fail_count <= 0:
                    return result
                await asyncio.sleep(delay_retry_time)
        return wrapper
    return decorator

class ReqBase(object):
    def __init__(self, run_py_dir="", concurrent_quantity=None, cookies_dict={}, proxies=None, max_req_timeout=10, redis_url="", max_fail_count=5, ctx_dict={}):
        self.run_py_dir = run_py_dir
        self.concurrent_quantity = concurrent_quantity
        self.sem = asyncio.Semaphore(concurrent_quantity) if concurrent_quantity else None
        self.session = requests.AsyncSession()
        self.cookies_dict = cookies_dict
        self.update_session_cookies(cookies_dict=self.cookies_dict)
        self.proxies = proxies
        self.max_req_timeout = max_req_timeout
        self.redis_url = redis_url
        self.max_fail_count = max_fail_count
        self.ua = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/136.0.0.0 Safari/537.36"
        self.ctx_dict = ctx_dict
        self.js_path = self.run_py_dir / "js_path" if self.run_py_dir else ""
        if not self.ctx_dict and self.run_py_dir:
            js_files = os.listdir(self.js_path)
            for js_file in js_files:
                self.ctx_dict["".join(js_file.split(".")[:-1])] = execjs.compile(open(self.js_path / js_file, encoding='utf-8').read())

    def use_execjs(self, ctx_key: str="", funcname: str="", params: tuple=()) -> str:
        js_args = ",".join(json.dumps(p) for p in params)
        js_code = f"{funcname}({js_args})"
        encrypt_words = self.ctx_dict[ctx_key].eval(js_code)
        return encrypt_words

    def join_url_params(self, url, params):
        return f'{url}?{urlencode(params)}'
    
    def set_session_cookies(self, session: requests.Session, cookies_dict):
        for ck in cookies_dict:
            session.cookies.set(ck, cookies_dict[ck])

    def update_session_cookies(self, cookies_dict={}, session=None):
        assert isinstance(cookies_dict, dict)
        session = session if session else self.session
        self.set_session_cookies(session=session, cookies_dict=cookies_dict)

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_fixed(2),
        retry=retry_if_exception_type(Exception)
    )
    async def do_req(self, 
        session: requests.AsyncSession=None, 
        method: Literal["GET", "POST", "PUT", "DELETE", "OPTIONS", "HEAD", "TRACE", "PATCH"] = "GET", 
        url="", 
        headers=None, 
        data=None, 
        no_proxy=False
    ) -> "Response":
        assert url and method.upper() in {"GET", "POST", "PUT", "DELETE", "OPTIONS", "HEAD", "TRACE", "PATCH"}
        session = session if session else self.session
        proxies = None if no_proxy else self.proxies
        response = await session.request(method=method.upper(), url=url, headers=headers, data=data, timeout=self.max_req_timeout, proxies=proxies)
        return response
    
    async def update_base_photoinfo(self, photo_info: PhotoInfo):
        get_img_content_result = await self.get_img_content(inner_url=photo_info.inner_mediaurl)
        if get_img_content_result.get("status"):
            photo_data = get_img_content_result.get("data", {}).get("response_data", b'')
            if not photo_data:
                return get_img_content_result
            photo_size = len(photo_data)
            photo_type = guess_content_type(byte_data=photo_data)
            if not photo_type:
                return {"status": 0, "data": {"text": f'图片 {photo_info.inner_mediaurl} 类型识别失败', "response_data": photo_type}}
            photo_info.media_data = photo_data
            photo_info.media_size = photo_size
            photo_info.media_type = photo_type
            return {"status": 1, "data": {"text": f'图片 {photo_info.inner_mediaurl} 类型识别成功：{photo_type}', "response_data": photo_info}}
        return get_img_content_result

    async def update_base_videoinfo(self, video_info: VideoInfo):
        all_file_data = []
        part_byte_start=0
        single_part_size = 2999999 # 一个分段的字节大小
        part_byte_end = single_part_size
        while True:
            if video_info.media_size < part_byte_end: # 最后一个分段的大小 = 文件总大小 - 下一分段获取文件字节的起始索引
                part_byte_end = video_info.media_size - part_byte_start
            else:
                part_byte_end = part_byte_start + single_part_size
            custom_retry_result = await self.get_video_content(inner_url=video_info.inner_mediaurl, part_byte_start=part_byte_start, part_byte_end=part_byte_end)
            print(custom_retry_result.get("data", {}).get("text", ""))
            if not custom_retry_result.get("status"):
                return custom_retry_result
            single_part_data = custom_retry_result.get("data", {}).get("response_data", b'')
            all_file_data.append(single_part_data)
            part_byte_start = part_byte_end + 1
            if part_byte_start >= video_info.media_size:
                video_data = b''.join(all_file_data)
                if not video_data:
                    return {"status": 0, "data": {"text": f'获取{video_info.fill_text}失败，视频内容为空', "response_data": video_data}}
                video_size = len(video_data) # 字节数
                video_type = guess_content_type(byte_data=video_data)
                if not video_type:
                    return {"status": 0, "data": {"text": f'图片 {video_info.inner_mediaurl} 类型识别失败', "response_data": video_type}}
                video_info.media_data = video_data
                video_info.media_size = video_size
                video_info.media_type = video_type
                break
        return {"status": 1, "data": {"text": f'视频 {video_info.inner_mediaurl} 基础信息成功', "response_data": video_info}}

    # 获取内部图片资源内容
    @custom_retry(delay_retry_time=5)
    async def get_img_content(self, inner_url=""):
        try:
            async with requests.AsyncSession() as session:
                img_response = await session.get(inner_url)
                img_response_content = img_response.content
                return {"status": 1, "data": {"text": f"获取图片 {inner_url} 成功", "response_data": img_response_content}}
        except Exception as e:
            return {"status": 0, "data": {"text": f"获取图片 {inner_url} 失败：{e}", "response_data": ""}}
       
    # 获取内部视频资源内容（分段获取）
    @custom_retry(delay_retry_time=5)
    async def get_video_content(self, inner_url="", part_byte_start=0, part_byte_end=2999999):
        try:
            async with requests.AsyncSession() as session:
                video_response = await session.get(inner_url, headers={"Range": f"bytes={part_byte_start}-{part_byte_end}"}, timeout=self.max_req_timeout)
                video_response_content = video_response.content
                return {"status": 1, "data": {"text": f"获取视频 {inner_url} 分段 {part_byte_start}~{part_byte_end} 成功", "response_data": video_response_content}}
        except Exception as e:
            return {"status": 0, "data": {"text": f"获取视频 {inner_url} 分段 {part_byte_start}~{part_byte_end} 失败：{e}", "response_data": ""}}