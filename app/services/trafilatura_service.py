from threading import Thread
from typing import List, Dict, Any
from loguru import logger
from trafilatura import fetch_url, extract
from app.services.database import db_service
from app.models.article import Article
from sqlmodel import Session


class TrafilaturaService:
    """Service for converting URLs to markdown using trafilatura."""

    def __init__(self):
        self._active_tasks: Dict[str, Thread] = {}

    def process_urls_async(self, urls: List[str]) -> Dict[str, Any]:
        """Process URLs asynchronously in background thread."""
        task_id = f"task_{id(self)}"

        def _process():
            results = []
            for url in urls:
                try:
                    result = self._process_single_url(url)
                    results.append(result)
                except Exception as e:
                    logger.error(f"Failed to process URL {url}: {e}")
                    results.append({"url": url, "status": "error", "message": str(e)})

            logger.info(f"Task {task_id} completed: {len(results)} URLs processed")

        thread = Thread(target=_process, daemon=True)
        thread.start()
        self._active_tasks[task_id] = thread

        return {
            "task_id": task_id,
            "status": "started",
            "urls_count": len(urls)
        }

    def _process_single_url(self, url: str) -> Dict[str, Any]:
        """Process a single URL and save to database."""
        logger.info(f"Fetching URL: {url}")

        # Step 1: Download HTML
        downloaded = fetch_url(url)
        if not downloaded:
            raise Exception(f"Failed to fetch URL: {url}")

        # Step 2: Extract as markdown with metadata
        result = extract(
            downloaded,
            url=url,
            output_format="markdown",
            with_metadata=True,
            include_links=True,
            include_images=True
        )

        if not result:
            raise Exception(f"Failed to extract content from: {url}")

        # Step 3: Parse metadata from the result
        # Trafilatura returns markdown with metadata as YAML frontmatter
        # We need to extract it properly
        metadata = self._extract_metadata(downloaded, url)

        # Step 4: Save to database
        self._save_article(url, metadata.get("title", ""), result, metadata.get("keywords", []))

        return {
            "url": url,
            "status": "success",
            "title": metadata.get("title", ""),
            "keywords": metadata.get("keywords", [])
        }

    def _extract_metadata(self, html_content: str, url: str) -> Dict[str, Any]:
        """Extract metadata from HTML content."""
        from trafilatura import bare_extraction

        metadata = bare_extraction(
            html_content,
            url=url,
            with_metadata=True
        )

        return {
            "title": metadata.title if metadata else "",
            "author": metadata.author if metadata else None,
            "date": metadata.date if metadata else None,
            "keywords": metadata.tags if metadata else [],
            "description": metadata.description if metadata else None
        }

    def _save_article(self, url: str, title: str, md_content: str, keywords: List[str]):
        """Save or update article in database."""
        session: Session = db_service.get_session()

        # Check if article exists by URL
        existing = session.query(Article).filter(Article.link == url).first()

        if existing:
            # Update existing article
            existing.title = title
            existing.md_content = md_content
            existing.keywords = keywords
            existing.updated_at = existing.updated_at
            logger.info(f"Updated article: {title} ({url})")
        else:
            # Create new article
            # Extract issue number from URL or use a default
            number = self._extract_number_from_url(url)

            new_article = Article(
                title=title,
                link=url,
                number=number,
                md_content=md_content,
                keywords=keywords
            )
            session.add(new_article)
            logger.info(f"Created new article: {title} ({url})")

        session.commit()
        session.close()

    def _extract_number_from_url(self, url: str) -> str:
        """Extract issue number from URL or generate default."""
        import re
        # Try to extract number from URL patterns like /issue/123 or ?issue=123
        match = re.search(r'issue[/=]?(\d+)', url, re.IGNORECASE)
        if match:
            return match.group(1)
        return "imported"


# Global service instance
trafilatura_service = TrafilaturaService()
