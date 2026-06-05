from flask import Blueprint, request, jsonify
from loguru import logger
from app.services.rag_service import rag_service
from app.services.import_service import import_service
from app.services.database import db_service
from app.services.trafilatura_service import trafilatura_service

api_bp = Blueprint("api", __name__)


@api_bp.route("/query", methods=["POST"])
def query():
    """RAG query endpoint."""
    data = request.get_json()
    query = data.get("query", "")

    if not query:
        return jsonify({"error": "Query is required"}), 400

    try:
        result = rag_service.query(query)
        return jsonify(result)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@api_bp.route("/import", methods=["POST"])
def import_data():
    """Import data from JSON file or directory."""
    data = request.get_json()
    path = data.get("path")

    if not path:
        return jsonify({"error": "Path is required"}), 400

    try:
        # Detect if it's a file or directory
        from pathlib import Path
        target_path = Path(path)

        if target_path.is_file():
            stats = import_service.import_from_json(path)
        elif target_path.is_dir():
            stats = import_service.import_from_directory(path)
        else:
            return jsonify({"error": "Path not found"}), 404

        # Update FTS index
        import_service.update_fts_index()

        return jsonify({"success": True, "stats": stats})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@api_bp.route("/reindex", methods=["POST"])
def reindex():
    """Rebuild FTS index."""
    try:
        db_service.reindex_fts()
        return jsonify({"success": True, "message": "FTS index rebuilt"})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@api_bp.route("/stats", methods=["GET"])
def stats():
    """Get database statistics."""
    try:
        from sqlmodel import Session, select, func
        from app.models import Article, Item

        with db_service.get_session() as session:
            article_count = session.exec(select(func.count(Article.id))).one()
            item_count = session.exec(select(func.count(Item.id))).one()

        return jsonify({
            "articles": article_count,
            "items": item_count
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@api_bp.route("/items", methods=["GET"])
def get_items():
    """Get all items with optional section filter."""
    try:
        from sqlmodel import Session, select
        from app.models import Item, Article

        section_filter = request.args.get("section")

        with db_service.get_session() as session:
            query = select(Item, Article).join(Article, Item.article_id == Article.id)

            if section_filter:
                query = query.where(Item.section_name == section_filter)

            results = session.exec(query).all()

            items = []
            for item, article in results:
                items.append({
                    "id": item.id,
                    "title": item.title,
                    "link": item.link,
                    "description": item.description,
                    "user": item.user,
                    "user_link": item.user_link,
                    "images": item.images,
                    "section_name": item.section_name,
                    "article_id": item.article_id,
                    "article_title": article.title,
                    "article_number": article.number,
                    "article_link": article.link,
                    "created_at": item.created_at.isoformat() if item.created_at else None
                })

            return jsonify(items)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@api_bp.route("/articles", methods=["GET"])
def get_articles():
    """Get all articles with optional filter."""
    try:
        from sqlmodel import Session, select
        from app.models import Article

        search = request.args.get("search", "")

        with db_service.get_session() as session:
            query = select(Article)

            if search:
                query = query.where(
                    (Article.title.contains(search)) |
                    (Article.number.contains(search))
                )

            results = session.exec(query).all()

            articles = []
            for article in results:
                articles.append({
                    "id": article.id,
                    "title": article.title,
                    "link": article.link,
                    "number": article.number,
                    "keywords": article.keywords or [],
                    "md_content": article.md_content,
                    "status": article.status or "imported",
                    "created_at": article.created_at.isoformat() if article.created_at else None,
                    "updated_at": article.updated_at.isoformat() if article.updated_at else None
                })

            # Sort by number as integer (descending)
            def sort_key(article):
                try:
                    return -int(article['number'])  # Negative for descending
                except (ValueError, TypeError):
                    return 0  # Non-numeric numbers go to end

            articles.sort(key=sort_key)

            return jsonify(articles)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@api_bp.route("/articles/<int:article_id>", methods=["DELETE"])
def delete_article(article_id):
    """Delete an article by ID."""
    try:
        from sqlmodel import Session, select, delete
        from app.models import Article, Item

        with db_service.get_session() as session:
            # Check if article exists
            article = session.get(Article, article_id)
            if not article:
                return jsonify({"error": "Article not found"}), 404

            # Delete associated items first
            session.exec(delete(Item).where(Item.article_id == article_id))

            # Delete the article
            session.delete(article)
            session.commit()

        return jsonify({"success": True, "message": "Article deleted successfully"})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@api_bp.route("/dictionary", methods=["GET"])
def get_dictionary():
    """Get all words from jieba custom dictionary."""
    try:
        from pathlib import Path
        from app.config import settings

        dict_path = Path(settings.jieba_dict_path)
        words = []

        if dict_path.exists():
            with open(dict_path, 'r', encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith('#'):
                        parts = line.split()
                        if parts:
                            words.append(parts[0])

        return jsonify(words)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@api_bp.route("/dictionary", methods=["POST"])
def add_dictionary_word():
    """Add a word to jieba custom dictionary."""
    try:
        from pathlib import Path
        from app.config import settings

        data = request.get_json()
        word = data.get("word", "").strip()

        if not word:
            return jsonify({"error": "Word is required"}), 400

        dict_path = Path(settings.jieba_dict_path)
        dict_path.parent.mkdir(parents=True, exist_ok=True)

        # Read existing words
        existing_words = set()
        if dict_path.exists():
            with open(dict_path, 'r', encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith('#'):
                        parts = line.split()
                        if parts:
                            existing_words.add(parts[0])

        # Check if word already exists
        if word in existing_words:
            return jsonify({"success": True, "message": "Word already exists", "skipped": True})

        # Append new word with default frequency and noun tag
        with open(dict_path, 'a', encoding='utf-8') as f:
            f.write(f"{word} 5 n\n")

        return jsonify({"success": True, "message": "Word added successfully", "skipped": False})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@api_bp.route("/dictionary/<word>", methods=["DELETE"])
def delete_dictionary_word(word):
    """Delete a word from jieba custom dictionary."""
    try:
        from pathlib import Path
        from app.config import settings

        word = word.strip()
        if not word:
            return jsonify({"error": "Word is required"}), 400

        dict_path = Path(settings.jieba_dict_path)

        if not dict_path.exists():
            return jsonify({"error": "Dictionary file not found"}), 404

        # Read all lines and filter out the word
        lines = []
        with open(dict_path, 'r', encoding='utf-8') as f:
            for line in f:
                parts = line.strip().split()
                if parts and parts[0] == word:
                    continue  # Skip this line (delete the word)
                lines.append(line)

        # Write back without the deleted word
        with open(dict_path, 'w', encoding='utf-8') as f:
            f.writelines(lines)

        return jsonify({"success": True, "message": "Word deleted successfully"})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@api_bp.route("/stopwords", methods=["GET"])
def get_stopwords():
    """Get all stopwords from jieba stopwords file."""
    try:
        from pathlib import Path
        from app.config import settings

        stopwords_path = Path(settings.jieba_stopwords_path)
        words = []

        if stopwords_path.exists():
            with open(stopwords_path, 'r', encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith('#'):
                        words.append(line)

        return jsonify(words)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@api_bp.route("/stopwords", methods=["POST"])
def add_stopword():
    """Add a word to jieba stopwords file."""
    try:
        from pathlib import Path
        from app.config import settings

        data = request.get_json()
        word = data.get("word", "").strip()

        if not word:
            return jsonify({"error": "Word is required"}), 400

        stopwords_path = Path(settings.jieba_stopwords_path)
        stopwords_path.parent.mkdir(parents=True, exist_ok=True)

        # Read existing stopwords
        existing_words = set()
        if stopwords_path.exists():
            with open(stopwords_path, 'r', encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith('#'):
                        existing_words.add(line)

        # Check if word already exists
        if word in existing_words:
            return jsonify({"success": True, "message": "Word already exists", "skipped": True})

        # Append new word
        with open(stopwords_path, 'a', encoding='utf-8') as f:
            f.write(f"{word}\n")

        # Reload stopwords in database service
        db_service.reload_stopwords()

        return jsonify({"success": True, "message": "Stopword added successfully", "skipped": False})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@api_bp.route("/stopwords/<word>", methods=["DELETE"])
def delete_stopword(word):
    """Delete a word from jieba stopwords file."""
    try:
        from pathlib import Path
        from app.config import settings

        word = word.strip()
        if not word:
            return jsonify({"error": "Word is required"}), 400

        stopwords_path = Path(settings.jieba_stopwords_path)

        if not stopwords_path.exists():
            return jsonify({"error": "Stopwords file not found"}), 404

        # Read all lines and filter out the word
        lines = []
        with open(stopwords_path, 'r', encoding='utf-8') as f:
            for line in f:
                if line.strip() == word:
                    continue  # Skip this line (delete the word)
                lines.append(line)

        # Write back without the deleted word
        with open(stopwords_path, 'w', encoding='utf-8') as f:
            f.writelines(lines)

        # Reload stopwords in database service
        db_service.reload_stopwords()

        return jsonify({"success": True, "message": "Stopword deleted successfully"})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@api_bp.route("/dictionary/batch", methods=["POST"])
def batch_import_dictionary():
    """Batch import words to jieba custom dictionary."""
    try:
        from pathlib import Path
        from app.config import settings

        data = request.get_json()
        words = data.get("words", [])

        if not words:
            return jsonify({"error": "Words are required"}), 400

        dict_path = Path(settings.jieba_dict_path)
        dict_path.parent.mkdir(parents=True, exist_ok=True)

        # Read existing words
        existing_words = set()
        if dict_path.exists():
            with open(dict_path, 'r', encoding='utf-8') as f:
                for line in f:
                    parts = line.strip().split()
                    if parts:
                        existing_words.add(parts[0])

        # Count new and skipped words
        added_count = 0
        skipped_count = 0

        # Append new words
        with open(dict_path, 'a', encoding='utf-8') as f:
            for word in words:
                word = word.strip()
                if word and word not in existing_words:
                    f.write(f"{word} 5 n\n")
                    existing_words.add(word)
                    added_count += 1
                else:
                    skipped_count += 1

        return jsonify({
            "success": True,
            "message": f"Batch import completed: {added_count} added, {skipped_count} skipped",
            "added": added_count,
            "skipped": skipped_count
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@api_bp.route("/stopwords/batch", methods=["POST"])
def batch_import_stopwords():
    """Batch import words to jieba stopwords file."""
    try:
        from pathlib import Path
        from app.config import settings

        data = request.get_json()
        words = data.get("words", [])

        if not words:
            return jsonify({"error": "Words are required"}), 400

        stopwords_path = Path(settings.jieba_stopwords_path)
        stopwords_path.parent.mkdir(parents=True, exist_ok=True)

        # Read existing words
        existing_words = set()
        if stopwords_path.exists():
            with open(stopwords_path, 'r', encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith('#'):
                        existing_words.add(line)

        # Count new and skipped words
        added_count = 0
        skipped_count = 0

        # Append new words
        with open(stopwords_path, 'a', encoding='utf-8') as f:
            for word in words:
                word = word.strip()
                if word and word not in existing_words:
                    f.write(f"{word}\n")
                    existing_words.add(word)
                    added_count += 1
                else:
                    skipped_count += 1

        # Reload stopwords in database service
        db_service.reload_stopwords()

        return jsonify({
            "success": True,
            "message": f"Batch import completed: {added_count} added, {skipped_count} skipped",
            "added": added_count,
            "skipped": skipped_count
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@api_bp.route("/import-urls", methods=["POST"])
def import_urls():
    """Import articles from URLs using trafilatura."""
    try:
        data = request.get_json()
        urls = data.get("urls", [])

        if not urls:
            return jsonify({"error": "URLs are required"}), 400

        # Filter valid URLs
        valid_urls = []
        for url in urls:
            url = url.strip()
            if url and (url.startswith("http://") or url.startswith("https://")):
                valid_urls.append(url)

        if not valid_urls:
            return jsonify({"error": "No valid URLs provided"}), 400

        # Process URLs asynchronously
        result = trafilatura_service.process_urls_async(valid_urls)

        return jsonify({
            "success": True,
            "message": f"Processing {len(valid_urls)} URLs in background",
            "task_id": result.get("task_id"),
            "urls_count": len(valid_urls)
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@api_bp.route("/articles/<int:article_id>/parse", methods=["POST"])
def parse_article(article_id):
    """Parse a single article's markdown content to JSON."""
    try:
        from app.services.md_to_json_service import md_to_json_service
        import threading

        def _parse_task():
            import asyncio
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                result = loop.run_until_complete(md_to_json_service.parse_article(article_id))
                logger.info(f"Parse task completed for article {article_id}: {result}")
            finally:
                loop.close()

        # Run in background thread
        thread = threading.Thread(target=_parse_task, daemon=True)
        thread.start()

        return jsonify({
            "success": True,
            "message": "解析任务提交成功，正在解析中"
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@api_bp.route("/articles/batch-parse", methods=["POST"])
def batch_parse_articles():
    """Parse all articles with markdown content to JSON."""
    try:
        from app.services.md_to_json_service import md_to_json_service
        import threading

        def _batch_parse_task():
            import asyncio
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                result = loop.run_until_complete(md_to_json_service.batch_parse_imported_articles())
                logger.info(f"Batch parse completed: {result}")
            finally:
                loop.close()

        # Run in background thread
        thread = threading.Thread(target=_batch_parse_task, daemon=True)
        thread.start()

        return jsonify({
            "success": True,
            "message": "批量解析任务已启动，正在后台处理中..."
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500
