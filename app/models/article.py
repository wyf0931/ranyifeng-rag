from sqlmodel import SQLModel, Field, Relationship
from typing import Optional, List
from datetime import datetime


class Article(SQLModel, table=True):
    __tablename__ = "articles"

    id: Optional[int] = Field(default=None, primary_key=True)
    title: str = Field(index=True, description="Article title")
    link: str = Field(unique=True, index=True, description="Article URL (unique)")
    number: str = Field(index=True, description="Issue number")

    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    items: List["Item"] = Relationship(back_populates="article")
