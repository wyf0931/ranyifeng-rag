from flask import Blueprint, request, jsonify
from app.services.rag_service import rag_service
from app.services.import_service import import_service
from app.services.database import db_service

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
                    "article_link": article.link
                })

            return jsonify(items)
    except Exception as e:
        return jsonify({"error": str(e)}), 500
