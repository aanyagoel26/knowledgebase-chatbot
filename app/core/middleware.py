import time
import traceback

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware

from app.core.logger import logger


class RequestLoggingMiddleware(BaseHTTPMiddleware):

    async def dispatch(self, request: Request, call_next):
        start_time = time.time()

        try:
            response = await call_next(request)

            process_time = round(time.time() - start_time, 4)

            logger.info(
                "REQUEST | method=%s | path=%s | status=%s | time=%ss",
                request.method,
                request.url.path,
                response.status_code,
                process_time
            )

            return response

        except Exception as error:
            process_time = round(time.time() - start_time, 4)

            logger.error(
                "REQUEST FAILED | method=%s | path=%s | time=%ss | error=%s",
                request.method,
                request.url.path,
                process_time,
                str(error)
            )

            logger.error(traceback.format_exc())

            raise