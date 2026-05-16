"""FastAPI application for Leviathan Sidecar Observer Mode.

Provides REST API endpoints for:
- Node status and health checks
- Security audit for AI agent actions (Runtime Guardian)
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import TYPE_CHECKING

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

if TYPE_CHECKING:
    from config.settings import APIConfig

logger = logging.getLogger(__name__)


class AppState:
    """Application state container for shared resources."""

    def __init__(self):
        self.chain_client = None
        self.llm = None
        self.shared_law = None
        self.sessions: dict[str, dict] = {}  # session_token -> session data
        self.voters: dict[str, dict] = {}  # voter_address -> voter data


# Global app state (initialized during lifespan)
app_state = AppState()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan context manager for startup/shutdown events."""
    # Startup
    logger.info("Starting Leviathan Sidecar API (Observer Mode)")
    logger.info(f"CORS origins: {app.state.cors_origins}")

    # Initialize shared resources here (chain client, LLM, etc.)
    # These will be passed in via app.state during create_app()

    yield

    # Shutdown
    logger.info("Shutting down Leviathan Sidecar API")
    # Cleanup resources if needed
    app_state.sessions.clear()
    logger.info("Cleared active sessions")


def create_app(
    config: "APIConfig | None" = None,
    cors_origins: list[str] | None = None,
) -> FastAPI:
    """Create and configure the FastAPI application.

    Args:
        config: Optional API configuration.
        cors_origins: List of allowed CORS origins for Flutter/mobile clients.

    Returns:
        Configured FastAPI application.
    """
    # Default CORS origins for development
    if cors_origins is None:
        cors_origins = [
            "http://localhost:*",
            "http://localhost:3000",
            "http://localhost:8080",
            "http://127.0.0.1:*",
            "capacitor://localhost",  # Capacitor/Ionic mobile
            "http://localhost",
        ]

    app = FastAPI(
        title="Leviathan Sidecar API",
        description="Observer Mode API for security auditing and status monitoring",
        version="2.0.0",
        lifespan=lifespan,
    )

    # Store config in app state for access in lifespan
    app.state.cors_origins = cors_origins
    app.state.config = config

    # Add CORS middleware for Flutter/mobile clients
    app.add_middleware(
        CORSMiddleware,
        allow_origins=cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Register exception handlers
    app.add_exception_handler(ValueError, value_error_handler)
    app.add_exception_handler(Exception, generic_error_handler)

    # Register routes
    _register_routes(app)

    logger.info("FastAPI application created")
    return app


async def value_error_handler(request: Request, exc: ValueError) -> JSONResponse:
    """Handle ValueError exceptions with 400 Bad Request."""
    logger.warning(f"Value error: {exc}")
    return JSONResponse(
        status_code=400,
        content={
            "status": "error",
            "error": "bad_request",
            "detail": str(exc),
        },
    )


async def generic_error_handler(request: Request, exc: Exception) -> JSONResponse:
    """Handle unexpected exceptions with 500 Internal Server Error."""
    logger.error(f"Unexpected error: {exc}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={
            "status": "error",
            "error": "internal_error",
            "detail": "An unexpected error occurred",
        },
    )


def _register_routes(app: FastAPI):
    """Register API route handlers."""
    from api.routes import audit, status

    app.include_router(status.router, prefix="/api/v1", tags=["status"])
    app.include_router(audit.router, prefix="/api/v1", tags=["security"])

    # Health check at root
    @app.get("/health")
    async def health_check():
        """Simple health check endpoint."""
        return {"status": "ok", "mode": "observer"}


# Convenience function to run the server directly
def run_server(host: str = "0.0.0.0", port: int = 8080):
    """Run the API server with uvicorn.

    Args:
        host: Host to bind to.
        port: Port to listen on.
    """
    import uvicorn

    app = create_app()
    uvicorn.run(app, host=host, port=port)


if __name__ == "__main__":
    import sys

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8080
    run_server(port=port)
