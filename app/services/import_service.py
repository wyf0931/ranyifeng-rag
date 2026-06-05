from pathlib import Path
from typing import Dict, Any, List
from sqlmodel import Session, select
from app.models import Article, Item
from app.services.database import db_service
from loguru import logger


class ImportService:
    def __init__(self):
        self.session = None

    def import_from_json(self, json_path: str) -> Dict[str, int]:
        """Import article data from JSON file. Skips invalid JSON files."""
        import json

        try:
            with open(json_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
        except (json.JSONDecodeError, UnicodeDecodeError) as e:
            logger.warning(f"Skipping invalid JSON file {json_path}: {e}")
            return {"articles_created": 0, "articles_updated": 0, "items_created": 0, "items_updated": 0}

        return self._process_article(data)

    def _process_article(self, data: Dict[str, Any]) -> Dict[str, int]:
        """Process a single article data."""
        stats = {"articles_created": 0, "articles_updated": 0, "items_created": 0, "items_updated": 0}

        with db_service.get_session() as session:
            # Check if article exists by URL
            existing = session.exec(
                select(Article).where(Article.link == data["link"])
            ).first()

            if existing:
                article = existing
                stats["articles_updated"] += 1
            else:
                article = Article(
                    title=data["title"],
                    link=data["link"],
                    number=data["number"]
                )
                session.add(article)
                session.flush()  # Get ID
                stats["articles_created"] += 1

            # Process sections and items
            for section in data.get("sections", []):
                section_name = section["name"]
                for item_data in section.get("items", []):
                    item_stats = self._process_item(session, item_data, section_name, article.id)
                    stats["items_created"] += item_stats["items_created"]
                    stats["items_updated"] += item_stats["items_updated"]

            session.commit()

        return stats

    def _process_item(
        self, session: Session, item_data: Dict[str, Any], section_name: str, article_id: int
    ) -> Dict[str, int]:
        """Process a single item."""
        stats = {"items_created": 0, "items_updated": 0}

        # Check if item exists by link + title
        existing = session.exec(
            select(Item).where(
                Item.link == item_data["link"],
                Item.title == item_data["title"]
            )
        ).first()

        if existing:
            item = existing
            item.description = item_data.get("description", "")
            item.user = item_data.get("user")
            item.user_link = item_data.get("user_link")
            item.images = item_data.get("images", [])
            item.section_name = section_name
            stats["items_updated"] += 1
        else:
            item = Item(
                title=item_data["title"],
                link=item_data["link"],
                description=item_data.get("description", ""),
                user=item_data.get("user"),
                user_link=item_data.get("user_link"),
                images=item_data.get("images", []),
                section_name=section_name,
                article_id=article_id
            )
            session.add(item)
            stats["items_created"] += 1

        return stats

    def import_from_directory(self, directory: str) -> Dict[str, int]:
        """Import all JSON files from directory. Skips invalid JSON files."""
        total_stats = {"articles_created": 0, "articles_updated": 0, "items_created": 0, "items_updated": 0}

        articles_dir = Path(directory)
        if not articles_dir.exists():
            raise FileNotFoundError(f"Directory not found: {directory}")

        for json_file in articles_dir.glob("*.json"):
            logger.info(f"Processing {json_file.name}...")
            try:
                stats = self.import_from_json(str(json_file))
                for key in total_stats:
                    total_stats[key] += stats[key]
            except Exception as e:
                logger.error(f"Error processing {json_file.name}: {e}")
                continue

        return total_stats

    def update_fts_index(self):
        """Update FTS index after import."""
        db_service._create_fts_table()


import_service = ImportService()
