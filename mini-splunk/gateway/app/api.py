"""
Gateway API endpoints.
"""

from __future__ import annotations

from datetime import datetime
import uuid
from typing import Any

from fastapi import APIRouter, HTTPException, Query

from gateway.app.database import GatewayRepository
from gateway.app.publisher import RabbitMQPublisher
from gateway.app.schemas import (
    IngestRequest,
    IngestResponse,
    KeywordCountResponse,
    PurgeResponse,
    SearchResponse,
)

from shared.database.distributed_lock import DistributedLock
from shared.logging import get_logger

logger = get_logger("gateway.api")

router = APIRouter(
    prefix="/api",
    tags=["Gateway"],
)

publisher = RabbitMQPublisher()
repository = GatewayRepository()


########################################################
# Helper Functions
########################################################

def build_search_response(
    results: list[dict[str, Any]],
) -> SearchResponse:
    """
    Build a standardized search response.
    """

    return SearchResponse(
        count=len(results),
        results=results,
    )


########################################################
# INGEST
########################################################

@router.post(
    "/ingest",
    response_model=IngestResponse,
)
async def ingest(
    request: IngestRequest,
) -> IngestResponse:
    """
    Accept a syslog file and enqueue it for asynchronous
    processing by the Worker.
    """

    try:

        job_id = str(uuid.uuid4())

        publisher.publish(
            {
                "job_id": job_id,
                "filename": request.filename,
                "content": request.content,
                "received_at": datetime.utcnow().isoformat(),
            }
        )

        logger.info(
            "Accepted ingestion job %s",
            job_id,
        )

        return IngestResponse(
            status="accepted",
            message="File queued for processing.",
            filename=request.filename,
        )

    except Exception as exc:

        logger.exception(
            "Failed to enqueue ingestion job."
        )

        raise HTTPException(
            status_code=500,
            detail="Failed to enqueue ingestion job.",
        ) from exc


########################################################
# SEARCH_DATE
########################################################

@router.get(
    "/search/date",
    response_model=SearchResponse,
)
async def search_date(
    value: str = Query(...),
) -> SearchResponse:

    results = repository.search_date(value)

    return build_search_response(results)


########################################################
# SEARCH_HOST
########################################################

@router.get(
    "/search/host",
    response_model=SearchResponse,
)
async def search_host(
    value: str = Query(...),
) -> SearchResponse:

    results = repository.search_host(value)

    return build_search_response(results)


########################################################
# SEARCH_DAEMON
########################################################

@router.get(
    "/search/daemon",
    response_model=SearchResponse,
)
async def search_daemon(
    value: str = Query(...),
) -> SearchResponse:

    results = repository.search_daemon(value)

    return build_search_response(results)


########################################################
# SEARCH_SEVERITY
########################################################

@router.get(
    "/search/severity",
    response_model=SearchResponse,
)
async def search_severity(
    value: str = Query(...),
) -> SearchResponse:

    results = repository.search_severity(value)

    return build_search_response(results)


########################################################
# SEARCH_KEYWORD
########################################################

@router.get(
    "/search/keyword",
    response_model=SearchResponse,
)
async def search_keyword(
    value: str = Query(...),
) -> SearchResponse:

    results = repository.search_keyword(value)

    return build_search_response(results)


########################################################
# COUNT_KEYWORD
########################################################

@router.get(
    "/count/keyword",
    response_model=KeywordCountResponse,
)
async def count_keyword(
    value: str = Query(...),
) -> KeywordCountResponse:

    count = repository.count_keyword(value)

    return KeywordCountResponse(
        keyword=value,
        count=count,
    )


########################################################
# PURGE
########################################################

@router.delete(
    "/purge",
    response_model=PurgeResponse,
)
async def purge() -> PurgeResponse:
    """
    Delete all indexed log entries.

    A distributed lock is acquired before the purge to
    prevent Workers from writing while the operation is
    in progress.
    """

    acquired = False
    lock: DistributedLock | None = None

    try:

        lock = DistributedLock()

        acquired = lock.acquire()

        if not acquired:

            raise HTTPException(
                status_code=409,
                detail=(
                    "Another purge operation "
                    "is already in progress."
                ),
            )

        deleted = repository.purge()

        logger.info(
            "Purged %d log entries.",
            deleted,
        )

        return PurgeResponse(
            status="success",
            deleted=deleted,
        )

    except HTTPException:
        raise

    except Exception as exc:

        logger.exception(
            "Purge operation failed."
        )

        raise HTTPException(
            status_code=500,
            detail="Failed to purge log entries.",
        ) from exc

    finally:

        if lock is not None:

            if acquired:

                try:
                    lock.release()

                except Exception:

                    logger.exception(
                        "Failed to release distributed lock."
                    )

            lock.close()