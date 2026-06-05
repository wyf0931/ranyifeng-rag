#!/usr/bin/env python3
"""
Fix article numbers by extracting from title.

This script scans articles where number is 'imported', empty, None, or 'none',
extracts the issue number from the title using regex, and updates the database.

Usage:
    uv run python bin/fix_article_numbers.py

Title format examples:
    - 科技爱好者周刊（第 302 期）：创业虽然好，不敢推荐了
    - 每周分享第 17 期
    - 科技爱好者周刊：第 99 期

Extracted number: 302, 17, 99
"""

import re
import sys
from pathlib import Path
from sqlalchemy import create_engine, or_
from sqlmodel import Session, select

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from app.models import Article
from app.config import settings


def extract_issue_number(title: str) -> str | None:
    """
    Extract issue number from article title.

    Pattern: 科技爱好者周刊（第 X 期）：标题内容
    Returns: The extracted issue number as string, or None if not found.
    """
    if not title:
        return None

    # Match pattern: 第 [digits] 期
    # Examples:
    # - 科技爱好者周刊（第 302 期）：创业虽然好，不敢推荐了
    # - 科技爱好者周刊（第399期）：中国 AI 大厂访问记
    pattern = r'第\s*(\d+)\s*期'
    match = re.search(pattern, title)

    if match:
        return match.group(1)

    return None


def fix_article_numbers():
    """
    Scan articles and fix their issue numbers by extracting from title.
    """
    print(f"Database: {settings.database_path}")

    engine = create_engine(f"sqlite:///{settings.database_path}")

    with Session(engine) as session:
        # Find articles that need fixing
        # number is 'imported', empty string, None, or 'none'
        from sqlalchemy.sql import expression

        query = select(Article).where(
            or_(
                Article.number == 'imported',
                Article.number == '',
                Article.number == 'none',
                Article.number.is_(None)
            )
        )

        articles = session.exec(query).all()

        if not articles:
            print("No articles need fixing.")
            return

        print(f"Found {len(articles)} articles that need fixing.")

        updated_count = 0
        skipped_count = 0

        for article in articles:
            old_number = article.number
            extracted_number = extract_issue_number(article.title)

            if extracted_number:
                article.number = extracted_number
                print(f"✓ Article {article.id}: '{old_number}' → '{extracted_number}' (from title: {article.title[:50]}...)")
                updated_count += 1
            else:
                print(f"✗ Article {article.id}: Could not extract number from title: {article.title}")
                skipped_count += 1

        # Commit changes
        try:
            session.commit()
            print(f"\nSuccessfully updated {updated_count} articles.")
            print(f"Skipped {skipped_count} articles (could not extract number).")
        except Exception as e:
            session.rollback()
            print(f"\nError updating database: {e}")
            return 1

    return 0


if __name__ == "__main__":
    exit(fix_article_numbers())
