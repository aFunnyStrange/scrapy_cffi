from ..core.downloader.internet import Request, WebSocketRequest, HttpResponse

class Failure(BaseException):
    def __init__(self, exception: BaseException):
        self.exception = exception

    def __str__(self):
        return f"<Failure exception={repr(self.exception)}>"

class RequestFailure(Failure):
    def __init__(self, exception: BaseException, request: Request):
        super().__init__(exception)
        self.request = request

    def __str__(self):
        return f"<{self.__class__.__name__} request={self.request.url} exception={repr(self.exception)}>"

class ResponseFailure(RequestFailure):
    def __init__(self, exception: BaseException, response: HttpResponse, request: Request):
        super().__init__(exception, request)
        self.response = response

    def __str__(self):
        return f"<{self.__class__.__name__} request={self.request.url} response.status_code={self.response.status_code}>"

class DownloadError(RequestFailure):
    pass

class IgnoreResponse(ResponseFailure):
    def __str__(self):
        return f"<IgnoreResponse request={self.request.url} non-200 response: response.status_code={self.response.status_code}>"

class ResponseError(ResponseFailure):
    pass

class SessionEndError(RequestFailure):
    def __str__(self):
        if isinstance(self.request, WebSocketRequest):
            return f"<SessionEndError websocket_id={self.request.websocket_id}: connection closed>"
        return f"<SessionEndError session_id={self.request.session_id}: session closed>"

class BlockRequestError(RequestFailure):
    def __str__(self):
        return f"<BlockRequestError request={self.request.url}: blocked by robots.txt>"

class FilterDomainRequestError(RequestFailure):
    def __str__(self):
        return f"<FilterDomainRequestError request={self.request.url}: not in allow_domains>"
