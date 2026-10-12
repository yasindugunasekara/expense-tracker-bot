from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from postgrest.exceptions import APIError

from app.core.config import get_settings
from app.core.logging import setup_logging, get_logger
from app.middleware.logging import RequestLoggingMiddleware
from app.routers import health_router, expenses_router, events_router, summary_router

# Initialize logging configuration
setup_logging()
logger = get_logger("app.main")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan context manager for startup and shutdown events."""
    settings = get_settings()
    logger.info("Starting %s v%s...", settings.APP_NAME, settings.APP_VERSION)
    yield
    logger.info("Shutting down %s...", settings.APP_NAME)


settings = get_settings()

app = FastAPI(
    title=settings.APP_NAME,
    description=settings.APP_DESCRIPTION,
    version=settings.APP_VERSION,
    lifespan=lifespan,
)

# -------------------------------
# Middleware
# -------------------------------
app.add_middleware(RequestLoggingMiddleware)


# -------------------------------
# Global Exception Handlers
# -------------------------------
@app.exception_handler(APIError)
async def supabase_api_error_handler(request: Request, exc: APIError):
    """Handle Supabase / PostgREST exceptions globally with structured responses."""
    code = getattr(exc, "code", None)
    message = getattr(exc, "message", str(exc))

    logger.error(
        "Supabase PostgREST error on %s %s: code=%s, message=%s",
        request.method,
        request.url.path,
        code,
        message,
    )

    if code == "42501":
        return JSONResponse(
            status_code=403,
            content={
                "error": "Database permission denied",
                "detail": "Violates Row-Level Security (RLS) policy. Check Supabase RLS policies or use the service_role key.",
                "code": code,
            },
        )

    return JSONResponse(
        status_code=400,
        content={
            "error": "Database operation failed",
            "detail": message,
            "code": code,
        },
    )


# -------------------------------
# Routers
# -------------------------------
app.include_router(health_router)
app.include_router(expenses_router)
app.include_router(events_router)
app.include_router(summary_router)