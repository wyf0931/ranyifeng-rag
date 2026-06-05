from flask import Flask
from app.config import settings
from app.services.database import db_service


def create_app() -> Flask:
    """Create and configure Flask application."""
    app = Flask(__name__)
    app.config["SECRET_KEY"] = "dev-secret-key-change-in-production"
    app.config["DEBUG"] = settings.flask_debug

    # Initialize database
    db_service.init_db()

    # Register routes
    from app.routes import chat_bp, api_bp

    app.register_blueprint(chat_bp)
    app.register_blueprint(api_bp, url_prefix="/api")

    return app
