#!/usr/bin/env python3
"""
Migration script to add LLM parsing usage fields to articles table.

Run this script to add the following columns:
- parse_duration: Parsing duration in seconds (FLOAT, nullable)
- parse_input_tokens: Input tokens used (INTEGER, nullable)
- parse_output_tokens: Output tokens generated (INTEGER, nullable)
- parse_cached_tokens: Cached tokens (INTEGER, nullable)
- parse_output_length: Output length in characters (INTEGER, nullable)
"""

import sqlite3
import sys
from pathlib import Path

# Add parent directory to path to import app modules
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.config import settings


def migrate():
    """Add parsing usage columns to articles table."""
    db_path = Path(settings.database_path)

    if not db_path.exists():
        print(f"Database not found at {db_path}")
        return

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    try:
        # Check if columns already exist
        cursor.execute("PRAGMA table_info(articles)")
        columns = {row[1] for row in cursor.fetchall()}

        columns_to_add = {
            'parse_duration': 'REAL',
            'parse_input_tokens': 'INTEGER',
            'parse_output_tokens': 'INTEGER',
            'parse_cached_tokens': 'INTEGER',
            'parse_output_length': 'INTEGER'
        }

        for column_name, column_type in columns_to_add.items():
            if column_name not in columns:
                print(f"Adding column: {column_name} ({column_type})")
                cursor.execute(
                    f"ALTER TABLE articles ADD COLUMN {column_name} {column_type}"
                )
            else:
                print(f"Column already exists: {column_name}")

        conn.commit()
        print("Migration completed successfully!")

    except Exception as e:
        conn.rollback()
        print(f"Migration failed: {e}")
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    migrate()
