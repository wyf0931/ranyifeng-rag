"""
Service for parsing article markdown content to JSON using LLM.

This service handles:
- Reading markdown content from articles
- Calling LLM API to parse markdown to structured JSON
- Validating and saving JSON output
- Updating article parsing status
"""

import asyncio
import json
import os
import re
from pathlib import Path
from typing import Optional, Dict, Any, List
from datetime import datetime
from loguru import logger
from openai import AsyncOpenAI
from sqlmodel import Session, select

from app.models import Article
from app.config import settings


# System prompt for LLM
SYSTEM_PROMPT = """you are a helpful assistant of convert markdown article to json.

## convert workflow:
1. the user will give you a markdown article, that has mutil sections about 开篇小故事，活动（一般都是推广），文章（一些推荐的文章），工具，资源，特定领域（例如 Ai等），图片，文摘，言论，References，往期回顾等；

2. we need extract sections and items then write and format with json, the json schema example:

```json
{
    "title": "article title",
    "link": "article link",
    "number": 123,
    "sections": [
        {
            "name": "section name (e.g. 开篇小故事，活动，文章，工具，资源，特定领域（例如 Ai等），图片，文摘，言论，References，往期回顾等)",
            "items": [
                {
                    "title": "该条目的标题",
                    "link": "从对应编号的 reference 中提取",
                    "description": "该条信息的解释或说明，如果是开篇小故事，则是整段故事内容的 Markdown，包含图片、链接等（optional）； ",
                    "user": "投稿人，一般都会提到，optional",
                    "user_link": "投稿连接，根据编号在 reference 中找对应的链接地址，optional",
                    "images": [
                        "https://cdn.beekka.com/blogimg/asset/202405/bg2024052912.webp"
                    ]
                }
            ]
        }
    ]
}
```

## Filter rules:
- 不需要的 section：往期回顾；

## 输出要求：
- 直接输出干净的 json 数据，不需要任何解释和说明；
- number 字段必须是数字类型，不要字符串；
"""

class MarkdownToJSONService:
    """Service for converting article markdown to JSON."""

    def __init__(self):
        self.api_base = os.getenv("OPENAI_API_BASE", "http://127.0.0.1:9092/v1")
        self.api_key = os.getenv("OPENAI_API_KEY", "hebo0931")
        self.model = os.getenv("LLM_MODEL", "Qwen3.6-35B-A3B-nvfp4")
        self.client = AsyncOpenAI(
            api_key=self.api_key,
            base_url=self.api_base
        )
        self.output_dir = Path("data/articles")
        self.output_dir.mkdir(parents=True, exist_ok=True)

        logger.info(f"Markdown to JSON service initialized:")
        logger.info(f"  API Base: {self.api_base}")
        logger.info(f"  Model: {self.model}")
        logger.info(f"  Output Dir: {self.output_dir}")

    async def parse_article(self, article_id: int) -> Dict[str, Any]:
        """
        Parse a single article's markdown content to JSON.

        Args:
            article_id: The article ID to parse

        Returns:
            Dict with parsing result status and details
        """
        import time
        from sqlalchemy import create_engine

        engine = create_engine(f"sqlite:///{settings.database_path}")

        with Session(engine) as session:
            article = session.get(Article, article_id)
            if not article:
                return {"success": False, "error": "Article not found"}

            if not article.md_content:
                return {"success": False, "error": "No markdown content to parse"}

            # Update status to analyzing
            article.status = "analyzing"
            session.commit()

            try:
                # Start timing
                start_time = time.time()

                # Call LLM to parse markdown
                result = await self._call_llm(article.md_content)

                # End timing
                duration = time.time() - start_time

                if result is None:
                    article.status = "fail"
                    session.commit()
                    return {"success": False, "error": "Failed to get valid JSON from LLM"}

                result_json = result.get("json")
                usage = result.get("usage", {})

                # Save JSON file
                json_path = self._save_json_file(article.number, result_json)

                # Store usage metrics
                article.parse_duration = round(duration, 2)
                article.parse_input_tokens = usage.get("prompt_tokens")
                article.parse_output_tokens = usage.get("completion_tokens")
                article.parse_cached_tokens = usage.get("cached_tokens")
                article.parse_output_length = len(result_json.get("title", "")) + sum(
                    len(item.get("title", "") + (item.get("description", "" or "")))
                    for section in result_json.get("sections", [])
                    for item in section.get("items", [])
                )

                # Update status to success
                article.status = "success"
                session.commit()

                logger.info(
                    f"Successfully parsed article {article_id} (#{article.number}) "
                    f"in {duration:.2f}s - "
                    f"tokens: {usage.get('prompt_tokens', 0)}→{usage.get('completion_tokens', 0)}"
                )
                return {
                    "success": True,
                    "article_id": article_id,
                    "number": article.number,
                    "json_path": str(json_path),
                    "usage": {
                        "duration": round(duration, 2),
                        "input_tokens": usage.get("prompt_tokens"),
                        "output_tokens": usage.get("completion_tokens"),
                        "cached_tokens": usage.get("cached_tokens"),
                    }
                }

            except Exception as e:
                article.status = "fail"
                session.commit()
                logger.error(f"Error parsing article {article_id}: {e}")
                return {"success": False, "error": str(e)}

    async def _call_llm(self, markdown_content: str) -> Optional[Dict[str, Any]]:
        """
        Call LLM API to parse markdown to JSON.

        Args:
            markdown_content: The markdown content to parse

        Returns:
            Dict with 'json' (parsed JSON) and 'usage' (token usage), or None if parsing failed
        """
        try:
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": markdown_content}
                ],
                temperature=0.1,
                max_tokens=16000,
            )

            # Extract content from response
            content = response.choices[0].message.content
            logger.debug(f"LLM response length: {len(content)} chars")

            # Extract usage information
            usage = {
                "prompt_tokens": response.usage.prompt_tokens if response.usage else 0,
                "completion_tokens": response.usage.completion_tokens if response.usage else 0,
                "total_tokens": response.usage.total_tokens if response.usage else 0,
                "cached_tokens": getattr(response.usage, "cached_tokens", 0) if response.usage else 0,
            }

            # Try to parse JSON
            parsed_json = self._parse_and_validate_json(content)

            if parsed_json is None:
                return None

            return {
                "json": parsed_json,
                "usage": usage
            }

        except Exception as e:
            logger.error(f"Error calling LLM: {e}")
            return None

    def _parse_and_validate_json(self, content: str | None) -> Optional[Dict[str, Any]]:
        """
        Parse and validate JSON content, attempting to fix common errors.

        Args:
            content: Raw string content from LLM

        Returns:
            Parsed JSON dict, or None if parsing fails
        """
        if not content:
            return None

        # Try direct JSON parsing first
        try:
            return json.loads(content)
        except json.JSONDecodeError:
            pass

        # Try to extract JSON from markdown code blocks
        json_match = re.search(r'```(?:json)?\s*(\{.*?\})\s*```', content, re.DOTALL)
        if json_match:
            try:
                return json.loads(json_match.group(1))
            except json.JSONDecodeError:
                pass

        # Try to find JSON object in content
        json_match = re.search(r'\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}', content, re.DOTALL)
        if json_match:
            try:
                return json.loads(json_match.group(0))
            except json.JSONDecodeError:
                pass

        # Try to fix common JSON errors
        fixed_content = self._fix_common_json_errors(content)
        if fixed_content:
            try:
                return json.loads(fixed_content)
            except json.JSONDecodeError:
                pass

        logger.warning("Failed to parse JSON from LLM response")
        return None

    def _fix_common_json_errors(self, content: str) -> Optional[str]:
        """
        Attempt to fix common JSON formatting errors.

        Args:
            content: Raw content string

        Returns:
            Fixed JSON string, or None if can't be fixed
        """
        try:
            # Remove markdown code blocks
            content = re.sub(r'```(?:json)?\s*', '', content)
            content = re.sub(r'```\s*$', '', content)

            # Remove extra text before/after JSON
            json_start = content.find('{')
            json_end = content.rfind('}')
            if json_start >= 0 and json_end > json_start:
                content = content[json_start:json_end + 1]

            # Fix common quote issues
            # Replace smart quotes with regular quotes
            content = content.replace('"', '"').replace('"', '"')
            content = content.replace(''', "'").replace(''', "'")

            # Remove trailing commas before closing brackets/braces
            content = re.sub(r',\s*([}\]])', r'\1', content)

            return content
        except Exception:
            return None

    def _save_json_file(self, number: str, json_data: Dict[str, Any]) -> Path:
        """
        Save parsed JSON to file.

        Args:
            number: Article issue number
            json_data: Parsed JSON data

        Returns:
            Path to saved JSON file
        """
        # Use number as filename
        json_path = self.output_dir / f"{number}.json"

        with open(json_path, 'w', encoding='utf-8') as f:
            json.dump(json_data, f, ensure_ascii=False, indent=2)

        logger.info(f"Saved JSON to {json_path}")
        return json_path

    async def batch_parse_imported_articles(self) -> Dict[str, Any]:
        """
        Parse all articles with status='imported' that have markdown content.

        Uses concurrent processing with up to 4 parallel LLM requests.
        Articles are sorted by issue number in descending order.

        Returns:
            Dict with batch parsing results
        """
        import asyncio
        from sqlalchemy import create_engine, desc, cast, Integer

        engine = create_engine(f"sqlite:///{settings.database_path}")

        with Session(engine) as session:
            query = select(Article).where(
                (Article.status == "imported") &
                (Article.md_content != None) &
                (Article.md_content != "")
            ).order_by(desc(cast(Article.number, Integer)))

            articles = session.exec(query).all()

        if not articles:
            logger.info("No articles to parse")
            return {
                "total": 0,
                "success": 0,
                "failed": 0,
                "articles": []
            }

        logger.info(f"Found {len(articles)} articles to parse (max 4 concurrent)")

        # Semaphore to limit concurrent requests to 4
        semaphore = asyncio.Semaphore(4)

        async def parse_with_semaphore(article):
            """Parse article with semaphore to limit concurrency."""
            async with semaphore:
                logger.info(f"Parsing article {article.id} (#{article.number})...")
                result = await self.parse_article(article.id)

                return {
                    "article": article,
                    "result": result
                }

        # Process all articles concurrently with semaphore
        tasks = [parse_with_semaphore(article) for article in articles]
        outcomes = await asyncio.gather(*tasks, return_exceptions=True)

        results = {
            "total": len(articles),
            "success": 0,
            "failed": 0,
            "articles": []
        }

        for outcome in outcomes:
            if isinstance(outcome, Exception):
                logger.error(f"Parse task failed with exception: {outcome}")
                results["failed"] += 1
                continue

            article = outcome["article"]
            result = outcome["result"]

            if result.get("success"):
                results["success"] += 1
                results["articles"].append({
                    "id": article.id,
                    "number": article.number,
                    "status": "success"
                })
            else:
                results["failed"] += 1
                results["articles"].append({
                    "id": article.id,
                    "number": article.number,
                    "status": "failed",
                    "error": result.get("error", "Unknown error")
                })

        logger.info(f"Batch parsing completed: {results['success']} success, {results['failed']} failed")
        return results


# Global service instance
md_to_json_service = MarkdownToJSONService()
