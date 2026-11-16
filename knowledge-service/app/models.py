"""Response model of knowledge-service.

Pipeline step: infrastructure.
"""

from pydantic import BaseModel


class ContentResponse(BaseModel):
    """Every knowledge endpoint returns the Markdown text of one document."""

    content: str
