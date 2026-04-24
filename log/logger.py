import logging
import inspect
from functools import wraps
from typing import Optional


def get_logger(name: Optional[str] = None):
    if name is None:
        frame = inspect.currentframe().f_back
        module = inspect.getmodule(frame)
        name = module.__name__ if module else 'unknown'

    return logging.getLogger(name)


def log_execution(logger_name: str = None):
    def decorator(func):
        @wraps(func)
        async def async_wrapper(*args, **kwargs):
            logger = get_logger(logger_name or func.__module__)
            logger.debug(f"Начало выполнения {func.__name__}")
            try:
                result = await func(*args, **kwargs)
                logger.debug(f"Успешное завершение {func.__name__}")
                return result
            except Exception as e:
                logger.error(f"Ошибка в {func.__name__}: {str(e)}", exc_info=True)
                raise

        return async_wrapper

    return decorator