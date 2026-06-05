#!/usr/bin/env python3
"""
Migration script to add status column to articles table.

Run this script to add the status column for tracking article parsing state.
"""

import sqlite3
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from app.config import settings


def migrate():
    """Add status column to articles table."""
    db_path = settings.database_path
    print(f"Migrating database: {db_path}")

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    try:
        # Check if status column already exists
        cursor.execute("PRAGMA table_info(articles)")
        columns = [row[1] for row in cursor.fetchall()]

        if 'status' in columns:
            print("Column 'status' already exists. Skipping migration.")
            return

        # Add status column with default value
        cursor.execute("""
            ALTER TABLE articles
            ADD COLUMN status TEXT DEFAULT 'imported'
            CHECK (status IN ('imported', 'analyzing', 'success', 'fail'))
        """)

        # Update existing records to have default status
        cursor.execute("UPDATE articles SET status = 'imported' WHERE status IS NULL")

        conn.commit()
        print("✓ Successfully added 'status' column to articles table")

    except Exception as e:
        conn.rollback()
        print(f"✗ Migration failed: {e}")
        return 1
    finally:
        conn.close()

    return 0


if __name__ == "__main__":
    exit(migrate())
