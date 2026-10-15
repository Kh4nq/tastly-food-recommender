"""Explicit pipeline settings; importing this module reads no environment/files."""

from pydantic import Field

from common.constants import DEFAULT_RANKING_TOP_K, DEFAULT_RETRIEVAL_TOP_K
from common.schemas import Schema


class PipelineConfig(Schema):
    retrieval_top_k: int = Field(default=DEFAULT_RETRIEVAL_TOP_K, gt=0, strict=True)
    ranking_top_k: int = Field(default=DEFAULT_RANKING_TOP_K, gt=0, strict=True)
