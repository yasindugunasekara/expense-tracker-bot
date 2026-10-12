import time
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response
from app.core.logging import get_logger

logger = get_logger("app.middleware.request")


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """Middleware to log incoming HTTP requests, process time, and status codes."""

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        start_time = time.perf_counter()
        client_host = request.client.host if request.client else "unknown"
        method = request.method
        path = request.url.path
        query = request.url.query

        endpoint_str = f"{path}?{query}" if query else path
        logger.info("Incoming request: %s %s from %s", method, endpoint_str, client_host)

        try:
            response = await call_next(request)
            process_time_ms = (time.perf_counter() - start_time) * 1000.0
            response.headers["X-Process-Time"] = f"{process_time_ms:.2f}ms"

            if response.status_code >= 500:
                logger.error(
                    "Completed request: %s %s -> Status %d (%.2fms)",
                    method,
                    endpoint_str,
                    response.status_code,
                    process_time_ms,
                )
            elif response.status_code >= 400:
                logger.warning(
                    "Completed request: %s %s -> Status %d (%.2fms)",
                    method,
                    endpoint_str,
                    response.status_code,
                    process_time_ms,
                )
            else:
                logger.info(
                    "Completed request: %s %s -> Status %d (%.2fms)",
                    method,
                    endpoint_str,
                    response.status_code,
                    process_time_ms,
                )
            return response
        except Exception as exc:
            process_time_ms = (time.perf_counter() - start_time) * 1000.0
            logger.exception(
                "Unhandled exception processing %s %s after %.2fms: %s",
                method,
                endpoint_str,
                process_time_ms,
                exc,
            )
            raise
