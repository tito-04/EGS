from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from app.core.config import settings
from app.core.observability import (
    configure_observability,
    initialize_request_context,
    log_request,
    now_monotonic,
)
from app.core.rate_limit import limiter
from app.core.redis_client import init_redis, close_redis
from app.db import init_db
from app.api.v1 import auth
from app.api.ui import router as ui_router


# Create FastAPI app
app = FastAPI(
    title="Auth Service",
    description="🔐 Authentication Service - JWT-based user management for EGS",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc"
)

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)


@app.middleware("http")
async def request_context_middleware(request, call_next):
    request_id, correlation_id = initialize_request_context(request)
    started_at = now_monotonic()

    response = await call_next(request)

    response.headers["X-Request-ID"] = request_id
    response.headers["X-Correlation-ID"] = correlation_id
    log_request(request, response.status_code, (now_monotonic() - started_at) * 1000)
    return response

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_redirect_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount("/static", StaticFiles(directory="app/static"), name="static")


# Event handlers
@app.on_event("startup")
async def startup_event():
    """Initialize database on startup."""
    try:
        configure_observability(settings.LOG_LEVEL)
        settings.validate_security_configuration()
        await init_db()
        await init_redis()
        print("✅ Database initialized successfully")
    except Exception as e:
        print(f"❌ Database initialization failed: {e}")
        raise


@app.on_event("shutdown")
async def shutdown_event():
    """Release resources on shutdown."""
    await close_redis()


# Health check endpoint
@app.get("/health")
async def health_check():
    """Simple health check endpoint."""
    return {
        "status": "healthy",
        "service": settings.SERVICE_NAME,
        "version": "1.0.0"
    }


# Include routers
app.include_router(auth.router, prefix=settings.API_V1_STR)
app.include_router(ui_router)


# Root endpoint
@app.get("/")
async def root():
    """Root endpoint with service information."""
    return {
        "message": "🔐 Auth Service v1.0.0",
        "docs": "/docs",
        "health": "/health",
        "api": "/api/v1",
        "login": "/ui/login?client_id=flash-sale&redirect_uri=http://localhost:3000/callback"
    }


# Global exception handler
@app.exception_handler(Exception)
async def global_exception_handler(request, exc):
    """Handle uncaught exceptions."""
    response = JSONResponse(
        status_code=500,
        content={"detail": "Internal server error"}
    )
    request_id = getattr(request.state, "request_id", "")
    correlation_id = getattr(request.state, "correlation_id", request_id)
    if request_id:
        response.headers["X-Request-ID"] = request_id
    if correlation_id:
        response.headers["X-Correlation-ID"] = correlation_id
    return response


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=8000,
        reload=settings.DEBUG
    )
