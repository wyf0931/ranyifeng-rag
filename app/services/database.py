import sqlite3
import jieba
from pathlib import Path
from typing import List, Dict, Any
from sqlmodel import SQLModel, create_engine, Session
from app.config import settings


class DatabaseService:
    def __init__(self):
        self.db_path = settings.database_path
        self.engine = None
        self.stopwords: set = set()
        self._init_jieba()
        self._load_stopwords()

    def _init_jieba(self):
        """Initialize jieba with custom dictionary if exists."""
        if Path(settings.jieba_dict_path).exists():
            jieba.load_userdict(settings.jieba_dict_path)

    def _load_stopwords(self):
        """Load stopwords from file if exists."""
        stopwords_path = Path(settings.jieba_stopwords_path)
        if stopwords_path.exists():
            with open(stopwords_path, 'r', encoding='utf-8') as f:
                self.stopwords = set(line.strip() for line in f if line.strip() and not line.startswith('#'))
        else:
            self.stopwords = set()

    def init_db(self):
        """Initialize database and create tables."""
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)

        self.engine = create_engine(f"sqlite:///{self.db_path}")

        # Create base tables
        from app.models import Article, Item
        SQLModel.metadata.create_all(self.engine)

        # Create FTS5 virtual table
        self._create_fts_table()

        return self.engine

    def _create_fts_table(self):
        """Create FTS5 virtual table for full-text search."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        # Drop existing FTS table if exists
        cursor.execute("DROP TABLE IF EXISTS items_fts")

        # Create FTS5 virtual table with simple tokenizer (we'll pre-tokenize with jieba)
        cursor.execute("""
            CREATE VIRTUAL TABLE items_fts USING fts5(
                title,
                description,
                content='items',
                content_rowid='id'
            )
        """)

        # Get all items and tokenize with jieba before inserting
        cursor.execute("SELECT id, title, description FROM items")
        items = cursor.fetchall()

        # Populate FTS table with tokenized content
        for item_id, title, description in items:
            # Tokenize with jieba
            title_tokens = " ".join(jieba.lcut(title))
            desc_tokens = " ".join(jieba.lcut(description))

            cursor.execute("""
                INSERT INTO items_fts(rowid, title, description)
                VALUES (?, ?, ?)
            """, (item_id, title_tokens, desc_tokens))

        conn.commit()
        conn.close()

    def reindex_fts(self):
        """Rebuild FTS index - use after updating jieba dictionary."""
        # Rebuild will use the same logic as _create_fts_table
        self._create_fts_table()

    def search(self, query: str, limit: int = 100) -> List[Dict[str, Any]]:
        """Search using FTS5 with jieba tokenization."""
        if not query or not query.strip():
            return []

        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        # Tokenize query with jieba
        tokens = jieba.cut_for_search(query)

        # Filter out single characters, whitespace, and stopwords
        search_tokens = [t for t in tokens if len(t) > 1 and t.strip() and t not in self.stopwords]
        if not search_tokens:
            search_tokens = [t for t in tokens if t.strip() and t not in self.stopwords]

        if not search_tokens:
            return []

        # Use OR query to match any token
        search_query = " OR ".join(search_tokens)

        # Search with FTS5
        cursor.execute("""
            SELECT i.id, i.title, i.link, i.description, i.section_name,
                   i.user, i.user_link, i.images, i.created_at,
                   i.article_id, a.title as article_title, a.number as article_number, a.link as article_link,
                   bm25(items_fts) as rank
            FROM items_fts
            JOIN items i ON items_fts.rowid = i.id
            JOIN articles a ON i.article_id = a.id
            WHERE items_fts MATCH ?
            ORDER BY rank
            LIMIT ?
        """, (search_query, limit))

        results = [dict(row) for row in cursor.fetchall()]
        conn.close()

        return results

    def get_session(self) -> Session:
        """Get database session."""
        if self.engine is None:
            self.init_db()
        return Session(self.engine)

    def reload_stopwords(self):
        """Reload stopwords from file."""
        self._load_stopwords()

    def cleanup_stale_parsing_status(self):
        """Reset articles with 'analyzing' status to 'fail' on startup."""
        with self.get_session() as session:
            from app.models import Article
            from sqlmodel import select

            # Find articles with analyzing status
            query = select(Article).where(Article.status == "analyzing")
            articles = session.exec(query).all()

            if articles:
                for article in articles:
                    article.status = "fail"
                session.commit()
                return len(articles)
            return 0


# Global database service instance
db_service = DatabaseService()
