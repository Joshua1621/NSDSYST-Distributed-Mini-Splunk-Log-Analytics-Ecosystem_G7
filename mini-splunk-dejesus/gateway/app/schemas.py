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
    Request model for log ingestion.
    """

    filename: str = Field(
        ...,
        description="Original filename",
    )

    content: str = Field(
        ...,
        description="Complete syslog file contents",
    )


class IngestResponse(BaseModel):
    """
    Response after a successful upload.
    """

    status: str

    message: str

    filename: str


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