from sqlmodel import SQLModel, Field, Relationship, Column
from sqlalchemy import TEXT, JSON
from typing import Optional, List
from datetime import datetime


class Article(SQLModel, table=True):
    __tablename__ = "articles"

    id: Optional[int] = Field(default=None, primary_key=True)
    title: str = Field(index=True, description="Article title")
    link: str = Field(unique=True, index=True, description="Article URL (unique)")
    number: str = Field(index=True, description="Issue number")

    # New fields for trafilatura content
    keywords: List[str] = Field(default=[], sa_column=Column(JSON), description="Article keywords")
    md_content: Optional[str] = Field(default=None, sa_column=Column(TEXT), description="Markdown content")

    # Parsing status: imported → analyzing → success/fail
    status: str = Field(
        default="imported",
        description="Article parsing status (imported/analyzing/success/fail)"
    )

    # LLM parsing usage metrics (all optional)
    parse_duration: Optional[float] = Field(default=None, description="Parsing duration in seconds")
    parse_input_tokens: Optional[int] = Field(default=None, description="Input tokens used")
    parse_output_tokens: Optional[int] = Field(default=None, description="Output tokens generated")
    parse_cached_tokens: Optional[int] = Field(default=None, description="Cached tokens")
    parse_output_length: Optional[int] = Field(default=None, description="Output length in characters")

    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    items: List["Item"] = Relationship(back_populates="article")
