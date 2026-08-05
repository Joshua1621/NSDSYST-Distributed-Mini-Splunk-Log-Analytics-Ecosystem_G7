"""
Mini-Splunk Gateway entry point.
"""

from fastapi import FastAPI

from gateway.app.api import (
    router as api_router,
    repository,
)

from gateway.app.health import (
    router as health_router,
)

from shared.logging import get_logger

logger = get_logger("gateway")

app = FastAPI(
    title="Mini-Splunk Gateway",
    version="1.0.0",
)

app.include_router(health_router)

app.include_router(api_router)


@app.on_event("startup")
async def startup() -> None:
    """
    Gateway startup event.
    """

    logger.info("Gateway started.")


@app.on_event("shutdown")
async def shutdown() -> None:
    """
    Gateway shutdown event.
    """

    repository.close()

    logger.info("Gateway stopped.")