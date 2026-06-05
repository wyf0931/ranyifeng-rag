#!/usr/bin/env python3
"""
Migration script to make items.link column nullable.

Run this script to allow NULL values in the link column,
since some items (like 开篇小故事) may not have their own link.
"""

import sqlite3
import sys
from pathlib import Path

# Add parent directory to path to import app modules
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.config import settings


def migrate():
    """Make items.link column nullable."""
    db_path = Path(settings.database_path)

    if not db_path.exists():
        print(f"Database not found at {db_path}")
        return

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    try:
        # SQLite doesn't support ALTER COLUMN directly, so we need to:
        # 1. Create a new table with the correct schema
        # 2. Copy data from old table to new table
        # 3. Drop old table
        # 4. Rename new table to original name

        # Check current schema
        cursor.execute("PRAGMA table_info(items)")
        columns = cursor.fetchall()
        print("Current items table schema:")
        for col in columns:
            print(f"  {col[1]}: {col[2]}")

        # Check if link column is already nullable
        link_column = next((col for col in columns if col[1] == "link"), None)
        if link_column and link_column[3] == 0:  # 0 means nullable
            print("Link column is already nullable. Migration not needed.")
            return

        print("\nMaking link column nullable...")

        # Get the CREATE TABLE statement
        cursor.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='items'")
        create_sql = cursor.fetchone()[0]

        # Create new table with nullable link column
        new_create_sql = create_sql
        # Replace various forms of NOT NULL constraint
        new_create_sql = new_create_sql.replace("link VARCHAR NOT NULL", "link TEXT")
        new_create_sql = new_create_sql.replace('"link" VARCHAR NOT NULL', '"link" TEXT')
        new_create_sql = new_create_sql.replace("link TEXT NOT NULL", "link TEXT")
        new_create_sql = new_create_sql.replace('"link" TEXT NOT NULL', '"link" TEXT')

        # Replace table name
        new_create_sql = new_create_sql.replace('CREATE TABLE "items"', 'CREATE TABLE "items_new"')
        new_create_sql = new_create_sql.replace('CREATE TABLE items', 'CREATE TABLE items_new')

        # Create new table
        cursor.execute('DROP TABLE IF EXISTS items_new')
        cursor.execute(new_create_sql)

        # Copy data
        cursor.execute("INSERT INTO items_new SELECT * FROM items")

        # Drop old table and rename new one
        cursor.execute("DROP TABLE items")
        cursor.execute("ALTER TABLE items_new RENAME TO items")

        # Recreate indexes
        cursor.execute('CREATE INDEX IF NOT EXISTS "ix_items_title" ON "items" ("title")')
        cursor.execute('CREATE INDEX IF NOT EXISTS "ix_items_article_id" ON "items" ("article_id")')

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
