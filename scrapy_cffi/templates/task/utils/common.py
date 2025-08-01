import random, os, logging
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from pathlib import Path

def some_common_function():
    a = random.random()
    b = random.random()
    return random.choice([10, 50, 100]) * a + b

def init_logger(run_py_dir: "Path", log_name: str, log_level="DEBUG", log_dir="", with_stream=True) -> logging.Logger:
    from logging.handlers import TimedRotatingFileHandler
    log_base_path = run_py_dir / 'logs' / log_dir if log_dir else run_py_dir / 'logs'
    os.makedirs(log_base_path, exist_ok=True)

    logger = logging.getLogger(log_name)
    logger.setLevel(getattr(logging, log_level.upper(), logging.DEBUG))
    logger.handlers.clear()
    logger.propagate = False
    formatter = logging.Formatter('%(asctime)s - %(filename)s:%(lineno)d - %(levelname)s - %(message)s')
    file_handler = TimedRotatingFileHandler(log_base_path / f'{log_name}.log', when='D', interval=1, backupCount=15, encoding='utf-8')
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)
    if with_stream:
        stream_handler = logging.StreamHandler()
        stream_handler.setLevel(logging.NOTSET)
        stream_handler.setFormatter(formatter)
        logger.addHandler(stream_handler)
    return logger

def start_log_listener(run_py_dir: "Path", log_queue, log_name, log_dir=None):
    from logging.handlers import TimedRotatingFileHandler, QueueListener
    log_base_path = run_py_dir / 'logs' / log_dir if log_dir else run_py_dir / 'logs'
    os.makedirs(log_base_path, exist_ok=True)
    handler = TimedRotatingFileHandler(
        os.path.join(log_base_path, f'{log_name}.log'), when='D', interval=1, backupCount=15, encoding='utf-8'
    )
    formatter = logging.Formatter('%(asctime)s - %(filename)s:%(lineno)d - %(levelname)s - %(message)s')
    handler.setFormatter(formatter)
    listener = QueueListener(log_queue, handler)
    listener.start()
    return listener