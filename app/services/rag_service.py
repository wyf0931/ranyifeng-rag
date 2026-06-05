from typing import Dict, Any, List, TypedDict, Annotated
from langchain_openai import ChatOpenAI
from langgraph.graph import StateGraph, END
from langgraph.checkpoint.memory import MemorySaver
from app.config import settings
from app.services.database import db_service


class RAGState(TypedDict):
    query: str
    rewritten_query: str
    search_results: List[Dict[str, Any]]
    thinking: str
    answer: str
    loop_count: int
    history: List[Dict[str, str]]


class RAGService:
    def __init__(self):
        self.llm = ChatOpenAI(
            base_url=settings.openai_api_base,
            api_key=settings.openai_api_key,
            model=settings.llm_model,
            temperature=0.7
        )
        self.graph = self._build_graph()

    def _build_graph(self) -> StateGraph:
        """Build RAG workflow graph using LangGraph."""

        def rewrite_query(state: RAGState) -> RAGState:
            """Rewrite user query for better search."""
            query = state["query"]

            prompt = f"""请改写以下用户查询信息，作为搜索 keywords。

output should be concise keywords that capture the essence of the query, suitable for searching a database of article titles. Use space to separate keywords.

example:
user query: "如何提升学习效率？"
rewritten keywords: "提升 学习效率 方法 技巧"

user query: "为什么我的代码报错之前没有输出？"
rewritten keywords: "代码 报错 没有 输出 原因"

user query: {query}
"""

            response = self.llm.invoke(prompt)
            state["rewritten_query"] = response.content.strip()
            state["loop_count"] = state.get("loop_count", 0) + 1
            return state

        def search(state: RAGState) -> RAGState:
            """Search for relevant content."""
            query = state.get("rewritten_query", state["query"])
            results = db_service.search(query, limit=settings.max_search_results)
            state["search_results"] = results
            return state

        def think(state: RAGState) -> RAGState:
            """Think about search results and decide if more info needed."""
            query = state.get("rewritten_query", state["query"])
            results = state.get("search_results", [])
            loop_count = state.get("loop_count", 0)

            # Format search results
            context = "\n".join([
                f"- {r['title']} ({r['article_title']}): {r['description']}"
                for r in results
            ])

            prompt = f"""用户查询: {query}

搜索结果:
{context}

请分析:
1. 这些结果是否足够回答用户查询?
2. 如果不够，需要如何改进搜索keywords?

返回格式:
DECISION: [CONTINUE/ANSWER]
REASONING: [你的分析过程]
IMPROVED_QUERY: [如果需要继续，提供改进的查询keywords]"""

            response = self.llm.invoke(prompt)
            content = response.content.strip()

            # Parse response
            decision = "ANSWER"
            improved_query = query
            reasoning = ""

            for line in content.split("\n"):
                if line.startswith("DECISION:"):
                    decision = line.split(":", 1)[1].strip().upper()
                elif line.startswith("REASONING:"):
                    reasoning = line.split(":", 1)[1].strip()
                elif line.startswith("IMPROVED_QUERY:"):
                    improved_query = line.split(":", 1)[1].strip()

            state["thinking"] = reasoning
            state["rewritten_query"] = improved_query

            # Check loop limit
            if loop_count >= settings.max_thinking_loops:
                decision = "ANSWER"

            return state

        def generate_answer(state: RAGState) -> RAGState:
            """Generate final answer based on all search results."""
            query = state["query"]
            results = state.get("search_results", [])

            # Build comprehensive context
            context_parts = []
            for r in results:
                context_parts.append(f"""
标题: {r['title']}
来源: {r['article_title']} - {r['article_link']}
描述: {r['description']}
链接: {r['link']}
""")

            context = "\n".join(context_parts)

            prompt = f"""基于以下搜索结果回答用户查询。

用户查询: {query}

搜索结果:
{context}

请提供准确、有帮助的答案。如果搜索结果不足以回答问题，请诚实地说明。"""

            response = self.llm.invoke(prompt)
            state["answer"] = response.content.strip()

            # Update history
            if "history" not in state:
                state["history"] = []
            state["history"].append({
                "query": query,
                "rewritten_query": state.get("rewritten_query", ""),
                "thinking": state.get("thinking", ""),
                "answer": state["answer"],
                "sources": [r["link"] for r in results]
            })

            return state

        def should_continue(state: RAGState) -> str:
            """Decide whether to continue searching or generate answer."""
            thinking = state.get("thinking", "")
            loop_count = state.get("loop_count", 0)

            if loop_count >= settings.max_thinking_loops:
                return "generate"

            if "CONTINUE" in thinking or "continue" in thinking.lower():
                return "search"
            return "generate"

        # Build graph
        workflow = StateGraph(RAGState)

        workflow.add_node("rewrite", rewrite_query)
        workflow.add_node("search", search)
        workflow.add_node("think", think)
        workflow.add_node("generate", generate_answer)

        workflow.set_entry_point("rewrite")
        workflow.add_edge("rewrite", "search")
        workflow.add_edge("search", "think")

        workflow.add_conditional_edges(
            "think",
            should_continue,
            {
                "search": "search",
                "generate": "generate"
            }
        )

        workflow.add_edge("generate", END)

        return workflow.compile()

    def query(self, query: str) -> Dict[str, Any]:
        """Execute RAG query."""
        initial_state: RAGState = {
            "query": query,
            "rewritten_query": "",
            "search_results": [],
            "thinking": "",
            "answer": "",
            "loop_count": 0,
            "history": []
        }

        result = self.graph.invoke(initial_state)

        return {
            "query": result["query"],
            "rewritten_query": result.get("rewritten_query", ""),
            "thinking": result.get("thinking", ""),
            "answer": result.get("answer", ""),
            "sources": result.get("history", [{}])[-1].get("sources", []),
            "loop_count": result.get("loop_count", 0)
        }


rag_service = RAGService()
