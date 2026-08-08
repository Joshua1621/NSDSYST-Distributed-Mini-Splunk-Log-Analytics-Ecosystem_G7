"""
Pydantic request and response models for the Gateway API.
"""

from typing import Any

from pydantic import BaseModel, Field


########################################################
# INGEST
########################################################

class IngestRequest(BaseModel):
    """
    Request model for a single batch of log lines.

    A large file is split by the client into multiple batches, each
    sent as a separate request sharing the same job_id. This keeps
    any single HTTP request, RabbitMQ message, and Worker parsing
    pass bounded to batch_size lines rather than the whole file --
    matching the spec's "streams a local file" requirement instead
    of buffering an entire file in memory at every hop.
    """

    job_id: str = Field(
        ...,
        description=(
            "Client-generated ID shared by every batch belonging "
            "to the same file upload."
        ),
    )

    filename: str = Field(
        ...,
        description="Original filename",
    )

    batch_index: int = Field(
        ...,
        ge=0,
        description=(
            "0-indexed position of this batch within the upload. "
            "Combined with each line's position inside the batch, "
            "this gives every line in the file a stable, globally "
            "unique offset used for idempotent storage."
        ),
    )

    is_final_batch: bool = Field(
        ...,
        description=(
            "True if this is the last batch for this job_id. Lets "
            "the Gateway/Worker know the full line count only once "
            "ingestion of the whole file has been accepted, without "
            "needing to know it in advance."
        ),
    )

    lines: list[str] = Field(
        ...,
        description="Raw syslog lines in this batch, in file order.",
    )


class IngestResponse(BaseModel):
    """
    Response after a batch has been accepted.
    """

    status: str

    message: str

    filename: str

    job_id: str

    batch_index: int


########################################################
# SEARCH
########################################################

class SearchResponse(BaseModel):
    """
    Generic search response.
    """

    count: int

    results: list[dict[str, Any]]


class KeywordCountResponse(BaseModel):
    """
    COUNT_KEYWORD response.
    """

    keyword: str

    count: int


########################################################
# PURGE
########################################################

class PurgeResponse(BaseModel):
    """
    PURGE response.
    """

    status: str

    deleted: int