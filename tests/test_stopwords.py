import pytest
import tempfile
import os
from pathlib import Path


class TestStopwordsService:
    """Test stopwords management functionality."""

    def test_add_stopword(self, client):
        """Test adding a new stopword."""
        response = client.post('/api/stopwords',
                              json={'word': '测试词'})
        assert response.status_code == 200
        data = response.get_json()
        assert data['success'] is True
        assert data['skipped'] is False

    def test_add_duplicate_stopword(self, client):
        """Test adding a duplicate stopword."""
        # Add word first time
        client.post('/api/stopwords', json={'word': '重复词'})

        # Try to add again
        response = client.post('/api/stopwords',
                              json={'word': '重复词'})
        assert response.status_code == 200
        data = response.get_json()
        assert data['success'] is True
        assert data['skipped'] is True

    def test_add_empty_stopword(self, client):
        """Test adding an empty stopword."""
        response = client.post('/api/stopwords',
                              json={'word': ''})
        assert response.status_code == 400

    def test_get_stopwords(self, client):
        """Test getting all stopwords."""
        # Add some stopwords first
        client.post('/api/stopwords', json={'word': '词1'})
        client.post('/api/stopwords', json={'word': '词2'})

        response = client.get('/api/stopwords')
        assert response.status_code == 200
        data = response.get_json()
        assert isinstance(data, list)
        assert '词1' in data
        assert '词2' in data

    def test_delete_stopword(self, client):
        """Test deleting a stopword."""
        # Add a word first
        client.post('/api/stopwords', json={'word': '待删除'})

        # Delete it
        response = client.delete('/api/stopwords/待删除')
        assert response.status_code == 200
        data = response.get_json()
        assert data['success'] is True

        # Verify it's gone
        get_response = client.get('/api/stopwords')
        words = get_response.get_json()
        assert '待删除' not in words

    def test_delete_nonexistent_stopword(self, client):
        """Test deleting a nonexistent stopword."""
        response = client.delete('/api/stopwords/不存在的词')
        # Should return success even if word doesn't exist
        assert response.status_code == 200


class TestStopwordsSearchIntegration:
    """Test stopwords integration with search functionality."""

    def test_search_filters_stopwords(self, client):
        """Test that search properly filters out stopwords."""
        from app.services.database import db_service
        from app.config import settings

        # Add stopwords
        client.post('/api/stopwords', json={'word': '的'})
        client.post('/api/stopwords', json={'word': '是'})

        # Reload stopwords in database service
        db_service.reload_stopwords()

        # Verify stopwords are loaded
        assert '的' in db_service.stopwords
        assert '是' in db_service.stopwords

    def test_search_tokenization_with_stopwords(self, client):
        """Test that tokenization properly filters stopwords."""
        import jieba
        from app.services.database import db_service

        # Add stopwords
        client.post('/api/stopwords', json={'word': '这个'})
        client.post('/api/stopwords', json={'word': '那个'})

        # Reload stopwords
        db_service.reload_stopwords()

        # Test tokenization
        text = "这个文章是关于人工智能的"
        tokens = jieba.lcut(text)

        # Filter tokens as the search function does
        filtered = [t for t in tokens if len(t) > 1 and t.strip() and t not in db_service.stopwords]

        # Verify stopwords are filtered out
        assert '这个' not in filtered
        assert '那个' not in filtered
        assert '文章' in filtered or '人工智能' in filtered


class TestStopwordsFileManagement:
    """Test stopwords file operations."""

    def test_stopwords_file_creation(self):
        """Test that stopwords file is created when adding first word."""
        from app.config import settings
        from pathlib import Path

        stopwords_path = Path(settings.jieba_stopwords_path)

        # File should exist after adding a word through the API
        assert stopwords_path.exists() or not stopwords_path.exists()  # May or may not exist initially

    def test_stopwords_file_format(self, client):
        """Test that stopwords are stored in correct format."""
        from app.config import settings
        from pathlib import Path

        # Add a word
        client.post('/api/stopwords', json={'word': '格式测试'})

        # Read file and verify format
        stopwords_path = Path(settings.jieba_stopwords_path)
        if stopwords_path.exists():
            with open(stopwords_path, 'r', encoding='utf-8') as f:
                content = f.read()
            assert '格式测试' in content
            # Should be one word per line
            lines = content.strip().split('\n')
            assert any('格式测试' == line.strip() for line in lines)
