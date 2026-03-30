"""Request-ID middleware: accept upstream X-Request-ID or generate UUID4.

Per D-04:
- Reads X-Request-ID header from incoming request
- If absent, generates UUID4
- Binds request_id to Loguru context via logger.contextualize()
- Sets X-Request-ID response header
- Health/readiness endpoints excluded
"""
import uuid

from loguru import logger
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

EXCLUDED_PATHS = {"/health/live", "/health/ready"}


class RequestIDMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        if request.url.path in EXCLUDED_PATHS:
            return await call_next(request)

        request_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())

        with logger.contextualize(request_id=request_id):
            response = await call_next(request)

        response.headers["X-Request-ID"] = request_id
        return response
