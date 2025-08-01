import logging
import sys
import os
import multiprocessing
from logging.handlers import TimedRotatingFileHandler, QueueHandler, QueueListener
from typing import Optional, TYPE_CHECKING
if TYPE_CHECKING:
    from ..models.api import LogInfo

class ShortNameFormatter(logging.Formatter):
    def format(self, record):
        if '.' in record.name:
            record.name = record.name.rsplit('.', 1)[-1]
        return super().format(record)

def init_logger(log_info: "LogInfo", logger_name: str) -> logging.Logger:
    """Initialize a single process logger for the current module. Recommend passing in __name__ as logger name."""
    if not logger_name or logger_name == "root":
        raise ValueError("Please pass __name__ or module-specific logger name, not root.")

    if not log_info.LOG_ENABLED:
        logging.disable(logging.CRITICAL)
        return

    log_level = getattr(logging, log_info.LOG_LEVEL, logging.DEBUG)
    log_format = log_info.LOG_FORMAT or "%(asctime)s [%(name)s] %(levelname)s: %(message)s"
    log_dateformat = log_info.LOG_DATEFORMAT
    log_file = log_info.LOG_FILE
    log_encoding = log_info.LOG_ENCODING
    log_short_names = log_info.LOG_SHORT_NAMES
    log_formatter_cls_path = log_info.LOG_FORMATTER
    with_stream = log_info.LOG_WITH_STREAM

    if log_formatter_cls_path:
        from ..utils import load_object
        log_formatter_cls = load_object(log_formatter_cls_path)
    elif log_short_names:
        log_formatter_cls = ShortNameFormatter
    else:
        log_formatter_cls = logging.Formatter

    formatter = log_formatter_cls(fmt=log_format, datefmt=log_dateformat)

    logger = logging.getLogger(logger_name)
    logger.handlers.clear()
    # logger.propagate = False

    if with_stream:
        has_stream = any(isinstance(h, logging.StreamHandler) for h in logger.handlers)
        if not has_stream:
            stream_handler = logging.StreamHandler(sys.stdout)
            stream_handler.setLevel(log_level)
            stream_handler.setFormatter(formatter)
            logger.addHandler(stream_handler)

    if log_file:
        if not os.path.isabs(log_file):
            from . import get_run_py_dir
            base_path = get_run_py_dir()
            log_file = os.path.join(base_path, log_file)
        log_dir = os.path.dirname(log_file)
        if log_dir:
            os.makedirs(log_dir, exist_ok=True)
        has_file = any(isinstance(h, TimedRotatingFileHandler) for h in logger.handlers)
        if not has_file:
            os.makedirs(os.path.dirname(log_file), exist_ok=True)
            file_handler = TimedRotatingFileHandler(
                log_file, when='D', interval=1, backupCount=15, encoding=log_encoding
            )
            file_handler.setLevel(log_level)
            file_handler.setFormatter(formatter)
            logger.addHandler(file_handler)
    logger.setLevel(log_level)
    return logger

def start_multiprocess_log_listener(
    log_info: "LogInfo",
    with_stream: bool = True,
) -> tuple[multiprocessing.Queue, QueueListener]:
    log_level = getattr(logging, log_info.LOG_LEVEL, logging.DEBUG)
    log_format = log_info.LOG_FORMAT or "%(asctime)s [%(name)s] %(levelname)s: %(message)s"
    log_dateformat = log_info.LOG_DATEFORMAT
    log_file = log_info.LOG_FILE
    log_encoding = log_info.LOG_ENCODING
    log_short_names = log_info.LOG_SHORT_NAMES
    log_formatter_cls_path = log_info.LOG_FORMATTER

    if log_formatter_cls_path:
        from ..utils import load_object
        log_formatter_cls = load_object(log_formatter_cls_path)
    elif log_short_names:
        log_formatter_cls = ShortNameFormatter
    else:
        log_formatter_cls = logging.Formatter

    formatter = log_formatter_cls(fmt=log_format, datefmt=log_dateformat)

    handlers = []

    if with_stream:
        stream_handler = logging.StreamHandler(sys.stdout)
        stream_handler.setLevel(log_level)
        stream_handler.setFormatter(formatter)
        handlers.append(stream_handler)

    if log_file:
        os.makedirs(os.path.dirname(log_file), exist_ok=True)
        file_handler = TimedRotatingFileHandler(
            log_file, when='D', interval=1, backupCount=15, encoding=log_encoding
        )
        file_handler.setLevel(log_level)
        file_handler.setFormatter(formatter)
        handlers.append(file_handler)

    log_queue = multiprocessing.Queue()

    root_logger = logging.getLogger()
    root_logger.setLevel(log_level)
    root_logger.handlers.clear()
    root_logger.addHandler(QueueHandler(log_queue))

    listener = QueueListener(log_queue, *handlers)
    listener.start()

    return log_queue, listener

def init_logger_multiprocessing(
    logger_name: str, 
    log_level="DEBUG", 
    log_queue: Optional[multiprocessing.Queue] = None, 
    with_stream=True,
    formatter: Optional[logging.Formatter] = None,
    extra_handlers=None
) -> logging.Logger:
    logger = logging.getLogger(logger_name)
    logger.setLevel(getattr(logging, log_level.upper(), logging.DEBUG))
    logger.handlers.clear()
    logger.propagate = False
    if formatter is None:
        formatter = logging.Formatter('%(asctime)s - %(filename)s:%(lineno)d - %(levelname)s - %(message)s')
    if with_stream:
        stream_handler = logging.StreamHandler()
        stream_handler.setLevel(logging.NOTSET)
        stream_handler.setFormatter(formatter)
        logger.addHandler(stream_handler)
    if log_queue:
        queue_handler = QueueHandler(log_queue)
        logger.addHandler(queue_handler)
    if extra_handlers:
        for h in extra_handlers:
            logger.addHandler(h)
    return logger