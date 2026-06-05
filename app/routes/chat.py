from flask import Blueprint, render_template

chat_bp = Blueprint("chat", __name__)


@chat_bp.route("/")
def index():
    """Render chat page."""
    return render_template("chat.html")


@chat_bp.route("/dictionary")
def dictionary():
    """Render dictionary management page."""
    return render_template("dictionary.html")


@chat_bp.route("/dataset")
def dataset():
    """Render dataset management page."""
    return render_template("dataset.html")


@chat_bp.route("/articles")
def articles():
    """Render articles management page."""
    return render_template("articles.html")


@chat_bp.route("/admin")
def admin():
    """Render admin page."""
    return render_template("admin.html")


@chat_bp.route("/stopwords")
def stopwords():
    """Render stopwords management page."""
    return render_template("stopwords.html")
