from sqlmodel import SQLModel, Field, Relationship, Column
from sqlalchemy import JSON, String
from typing import Optional, List, Dict, Any
from datetime import datetime


class Item(SQLModel, table=True):
    __tablename__ = "items"

    id: Optional[int] = Field(default=None, primary_key=True)
    title: str = Field(index=True, description="Item title")
    link: str = Field(description="Item URL")
    description: str = Field(default="", description="Item description")
    user: Optional[str] = Field(default=None, description="Submitter username")
    user_link: Optional[str] = Field(default=None, description="Submitter URL")
    images: List[str] = Field(default=[], sa_column=Column(JSON), description="Image URLs")

    section_name: str = Field(description="Section name within article")
    article_id: int = Field(foreign_key="articles.id", index=True, description="Article ID")

    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    article: "Article" = Relationship(back_populates="items")

    # Unique constraint on link + title
    __table_args__ = (
        {"sqlite_autoincrement": True},
    )
