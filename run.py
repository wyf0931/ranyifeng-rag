#!/usr/bin/env python3
"""
Entry point for the RAG application.
Usage: uv run python run.py
"""

from app import create_app
from app.config import settings

app = create_app()

if __name__ == "__main__":
    app.run(
        host=settings.flask_host,
        port=settings.flask_port,
        debug=settings.flask_debug
    )
