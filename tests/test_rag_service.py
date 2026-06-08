"""Tests for RAG service with optimized query rewrite."""
import pytest
from unittest.mock import Mock, patch, MagicMock
from app.services.rag_service import RAGService, RAGState


# Helper to create mock LLM response
def create_mock_response(content: str):
    """Create a mock ChatMessage response."""
    mock_response = Mock()
    mock_response.content = content
    return mock_response


@pytest.fixture
def rag_service():
    """Create RAG service instance."""
    return RAGService()


@pytest.fixture
def sample_search_results():
    """Sample search results for testing."""
    return [
        {
            'id': 1,
            'title': '油猴脚本使用指南',
            'link': 'https://example.com/tampermonkey-guide',
            'description': '介绍如何使用Tampermonkey编写和安装用户脚本',
            'section_name': '教程',
            'article_title': '科技爱好者周刊（第 100 期）',
            'article_link': 'https://www.ruanyifeng.com/blog/2020/01/weekly-issue-100.html',
            'article_id': 1,
            'rank': 1.0
        },
        {
            'id': 2,
            'title': 'Tampermonkey脚本开发教程',
            'link': 'https://example.com/tampermonkey-dev',
            'description': '详解Tampermonkey API和脚本开发实战',
            'section_name': '开发工具',
            'article_title': '科技爱好者周刊（第 105 期）',
            'article_link': 'https://www.ruanyifeng.com/blog/2020/02/weekly-issue-105.html',
            'article_id': 2,
            'rank': 0.9
        },
        {
            'id': 3,
            'title': 'JavaScript油猴脚本推荐',
            'link': 'https://example.com/js-scripts',
            'description': '推荐实用的油猴脚本，包括视频去广告、页面优化等',
            'section_name': '资源',
            'article_title': '科技爱好者周刊（第 110 期）',
            'article_link': 'https://www.ruanyifeng.com/blog/2020/03/weekly-issue-110.html',
            'article_id': 3,
            'rank': 0.8
        }
    ]


@pytest.fixture
def mock_llm_response_continue():
    """Mock LLM response for CONTINUE decision."""
    return create_mock_response("""DECISION: CONTINUE
REASONING: 搜索结果包含相关内容，但关键词"油猴 脚本"可以扩展为"Tampermonkey"以获得更精确的结果
IMPROVED_QUERY: 油猴 脚本 Tampermonkey""")


@pytest.fixture
def mock_llm_response_answer():
    """Mock LLM response for ANSWER decision."""
    return create_mock_response("""DECISION: ANSWER
REASONING: 搜索结果已经包含足够的信息来回答用户关于油猴脚本的查询
IMPROVED_QUERY: 油猴 脚本""")


class TestThinkAndRewrite:
    """Tests for think_and_rewrite functionality."""

    @pytest.fixture
    def state_with_results(self, sample_search_results):
        """State with search results."""
        return {
            'query': '油猴 脚本',
            'rewritten_query': '',
            'search_results': sample_search_results,
            'thinking': '',
            'decision': '',
            'answer': '',
            'loop_count': 0,
            'history': []
        }

    @patch('langchain_openai.ChatOpenAI.invoke')
    def test_think_and_rewrite_extracts_relevant_terms(
        self, mock_invoke, rag_service, state_with_results, mock_llm_response_continue
    ):
        """Test that think_and_rewrite extracts relevant terms from search results."""
        mock_invoke.return_value = mock_llm_response_continue

        new_state = rag_service.think_and_rewrite(state_with_results)

        # Should extract "Tampermonkey" from search results
        assert 'Tampermonkey' in new_state['rewritten_query']
        assert new_state['decision'] == 'CONTINUE'
        assert new_state['loop_count'] == 1
        assert len(new_state['thinking']) > 0

        # Verify LLM was called
        assert mock_invoke.called

    @patch('langchain_openai.ChatOpenAI.invoke')
    def test_think_and_rewrite_decides_to_answer(
        self, mock_invoke, rag_service, state_with_results, mock_llm_response_answer
    ):
        """Test that think_and_rewrite can decide to answer directly."""
        mock_invoke.return_value = mock_llm_response_answer

        new_state = rag_service.think_and_rewrite(state_with_results)

        assert new_state['decision'] == 'ANSWER'
        assert new_state['loop_count'] == 1

    @patch('langchain_openai.ChatOpenAI.invoke')
    def test_think_and_rewrite_respects_loop_limit(self, mock_invoke, rag_service, state_with_results):
        """Test that think_and_rewrite respects max loop limit."""
        from app.config import settings

        # Set loop count to max limit
        state_with_results['loop_count'] = settings.max_thinking_loops

        mock_response = create_mock_response("""DECISION: CONTINUE
REASONING: Should continue
IMPROVED_QUERY: test query""")

        mock_invoke.return_value = mock_response

        new_state = rag_service.think_and_rewrite(state_with_results)

        # Should force ANSWER decision when loop limit reached
        assert new_state['decision'] == 'ANSWER'

    @patch('langchain_openai.ChatOpenAI.invoke')
    def test_think_and_rewrite_handles_llm_error(self, mock_invoke, rag_service, state_with_results):
        """Test error handling in think_and_rewrite."""
        mock_invoke.side_effect = Exception("LLM error")

        new_state = rag_service.think_and_rewrite(state_with_results)

        assert new_state['decision'] == 'ANSWER'  # Should default to ANSWER on error
        assert '思考过程出错' in new_state['thinking']


class TestRAGWorkflow:
    """Tests for RAG workflow integration."""

    def test_workflow_has_correct_nodes(self, rag_service):
        """Test that workflow has the correct nodes after merge."""
        workflow = rag_service.graph

        # Should have search, think_and_rewrite, and generate nodes
        # Should NOT have separate think or rewrite nodes
        nodes = workflow.nodes
        assert 'search' in nodes
        assert 'think_and_rewrite' in nodes
        assert 'generate' in nodes

    @patch('app.services.rag_service.db_service')
    @patch('langchain_openai.ChatOpenAI.invoke')
    def test_query_with_think_and_rewrite(
        self, mock_invoke, mock_db_service, rag_service, sample_search_results
    ):
        """Test query execution with merged think_and_rewrite."""
        # Mock database search
        mock_db_service.search.return_value = sample_search_results

        # Mock LLM responses
        mock_invoke.side_effect = [
            create_mock_response("DECISION: ANSWER\nREASONING: Results are sufficient\nIMPROVED_QUERY: 油猴 脚本"),
            create_mock_response("基于搜索结果的回答内容...")
        ]

        result = rag_service.query('油猴 脚本')

        assert result['query'] == '油猴 脚本'
        assert result['answer'] == '基于搜索结果的回答内容...'
        assert len(result['sources']) > 0


class TestQueryStream:
    """Tests for query_stream functionality."""

    @patch('app.services.rag_service.db_service')
    @patch('langchain_openai.ChatOpenAI.invoke')
    def test_query_stream_emits_correct_events(
        self, mock_invoke, mock_db_service, rag_service, sample_search_results
    ):
        """Test that query_stream emits correct event sequence."""
        mock_db_service.search.return_value = sample_search_results

        mock_invoke.side_effect = [
            create_mock_response("""DECISION: CONTINUE
REASONING: Extracting relevant terms
IMPROVED_QUERY: 油猴 脚本 Tampermonkey"""),
            create_mock_response("""DECISION: ANSWER
REASONING: Sufficient results
IMPROVED_QUERY: 油猴 脚本 Tampermonkey"""),
            create_mock_response("Final answer based on search results...")
        ]

        events = list(rag_service.query_stream('油猴 脚本'))

        # Check event sequence
        assert events[0]['type'] == 'search_start'
        assert events[1]['type'] == 'search_complete'
        assert events[2]['type'] == 'think_complete'
        assert events[3]['type'] == 'search_complete'  # Second search
        assert events[4]['type'] == 'think_complete'
        assert events[-1]['type'] == 'answer_complete'

    @patch('app.services.rag_service.db_service')
    @patch('langchain_openai.ChatOpenAI.invoke')
    def test_query_stream_think_complete_includes_improved_query(
        self, mock_invoke, mock_db_service, rag_service, sample_search_results
    ):
        """Test that think_complete event includes improved_query when continuing."""
        mock_db_service.search.return_value = sample_search_results

        mock_response = create_mock_response("""DECISION: CONTINUE
REASONING: Need more specific terms
IMPROVED_QUERY: 油猴 脚本 Tampermonkey userscript""")

        mock_invoke.return_value = mock_response

        events = list(rag_service.query_stream('油猴 脚本'))

        # Find think_complete event
        think_event = next(e for e in events if e['type'] == 'think_complete')

        assert think_event['data']['decision'] == 'CONTINUE'
        assert 'Tampermonkey' in think_event['data']['improved_query']


class TestPromptQuality:
    """Tests for prompt quality and context usage."""

    @patch('langchain_openai.ChatOpenAI.invoke')
    def test_think_and_rewrite_prompt_includes_search_results(
        self, mock_invoke, rag_service, sample_search_results
    ):
        """Test that think_and_rewrite prompt includes search results context."""
        state = {
            'query': 'test',
            'search_results': sample_search_results,
            'loop_count': 0
        }

        mock_invoke.return_value = create_mock_response(
            "DECISION: ANSWER\nREASONING: test\nIMPROVED_QUERY: test"
        )

        rag_service.think_and_rewrite(state)

        # Check that LLM was invoked
        assert mock_invoke.called

        # Get the prompt that was sent
        call_args = mock_invoke.call_args
        messages = call_args[0][0]  # First positional argument (messages list)
        user_message = messages[1]['content']

        # Verify prompt includes search results context
        assert '搜索结果:' in user_message
        assert '油猴脚本使用指南' in user_message
        assert 'Tampermonkey' in user_message

    @patch('langchain_openai.ChatOpenAI.invoke')
    def test_think_and_rewrite_prompt_includes_extraction_instructions(self, mock_invoke, rag_service):
        """Test that prompt includes instructions for extracting terms from results."""
        state = {
            'query': '油猴 脚本',
            'search_results': [],
            'loop_count': 0
        }

        mock_invoke.return_value = create_mock_response(
            "DECISION: ANSWER\nREASONING: test\nIMPROVED_QUERY: test"
        )

        rag_service.think_and_rewrite(state)

        # Get the prompt
        call_args = mock_invoke.call_args
        messages = call_args[0][0]
        user_message = messages[1]['content']

        # Verify extraction instructions
        assert '请从搜索结果的标题和描述中提取相关关键词' in user_message
        assert '优先使用搜索结果中出现的专业术语、英文名、同义词' in user_message


class TestErrorHandling:
    """Tests for error handling."""

    @patch('app.services.rag_service.db_service')
    def test_query_stream_handles_search_error(self, mock_db_service, rag_service):
        """Test that query_stream handles database errors."""
        mock_db_service.search.side_effect = Exception("Database error")

        events = list(rag_service.query_stream('test query'))

        # Should emit error event
        assert any(e['type'] == 'error' for e in events)

    @patch('app.services.rag_service.db_service')
    @patch('langchain_openai.ChatOpenAI.invoke')
    def test_query_stream_handles_llm_error(self, mock_invoke, mock_db_service, rag_service, sample_search_results):
        """Test that query_stream handles LLM errors."""
        mock_db_service.search.return_value = sample_search_results

        mock_invoke.side_effect = Exception("LLM error")

        events = list(rag_service.query_stream('test query'))

        # Should emit error event
        assert any(e['type'] == 'error' for e in events)
