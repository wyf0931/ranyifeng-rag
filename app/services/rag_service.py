from typing import Dict, Any, List, TypedDict, Annotated
from loguru import logger
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
            logger.info(f"[rewrite_query] START - query: {query}")

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
            logger.info(f"[rewrite_query] END - rewritten_query: {state['rewritten_query']}, loop_count: {state['loop_count']}")
            return state

        def search(state: RAGState) -> RAGState:
            """Search for relevant content."""
            query = state.get("rewritten_query") or state["query"]
            logger.info(f"[search] START - query: {query}")
            results = db_service.search(query, limit=settings.max_search_results)
            state["search_results"] = results
            logger.info(f"[search] END - found {len(results)} results")
            return state

        def think(state: RAGState) -> RAGState:
            """Think about search results and decide if more info needed."""
            query = state.get("rewritten_query") or state["query"]
            results = state.get("search_results", [])
            loop_count = state.get("loop_count", 0)
            logger.info(f"[think] START - query: {query}, results_count: {len(results)}, loop_count: {loop_count}")

            try:
                # Format search results
                context = "\n".join([
                    f"- {r['title']} ({r['article_title']}): {r['description']}"
                    for r in results
                ])

                logger.info(f"[think] Calling LLM with context length: {len(context)} chars")

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

                logger.info(f"[think] Invoking LLM...")

                # Use messages format for LangChain ChatOpenAI
                messages = [
                    {"role": "system", "content": "You are a helpful assistant that analyzes search results and decides if more information is needed."},
                    {"role": "user", "content": prompt}
                ]
                response = self.llm.invoke(messages)

                content = response.content.strip()
                logger.info(f"[think] LLM response received, length: {len(content)} chars")

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

                logger.info(f"[think] END - decision: {decision}, improved_query: {improved_query}")
                return state
            except Exception as e:
                logger.error(f"[think] ERROR at line {e.__traceback__.tb_lineno if hasattr(e, '__traceback__') else 'unknown'}: {e}", exc_info=True)
                logger.error(f"[think] ERROR type: {type(e).__name__}, args: {e.args}")
                state["thinking"] = f"思考过程出错: {str(e)}"
                state["rewritten_query"] = query
                # On error, default to answering with current results
                return state

        def generate_answer(state: RAGState) -> RAGState:
            """Generate final answer based on all search results."""
            query = state["query"]
            results = state.get("search_results", [])
            logger.info(f"[generate_answer] START - query: {query}, results_count: {len(results)}")

            try:
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

                user_message = f"""基于以下搜索结果回答用户查询。

用户查询: {query}

搜索结果:
{context}

请提供准确、有帮助的答案。如果搜索结果不足以回答问题，请诚实地说明。"""

                # Use messages format
                messages = [
                    {"role": "system", "content": "You are a helpful assistant that answers questions based on search results from technology weekly articles."},
                    {"role": "user", "content": user_message}
                ]
                response = self.llm.invoke(messages)
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

                logger.info(f"[generate_answer] END - answer generated successfully")
                return state
            except Exception as e:
                logger.error(f"[generate_answer] ERROR: {e}", exc_info=True)
                state["answer"] = f"生成回答时出错: {str(e)}\n\n搜索结果:\n" + "\n".join([
                    f"- {r['title']}: {r['description']}"
                    for r in results[:5]
                ])
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

        # workflow.add_node("rewrite", rewrite_query)
        workflow.add_node("search", search)
        workflow.add_node("think", think)
        workflow.add_node("generate", generate_answer)

        # workflow.set_entry_point("rewrite")
        workflow.set_entry_point("search")
        # workflow.add_edge("rewrite", "search")
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
        try:
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

            # Safely extract sources from history
            sources = []
            history = result.get("history", [])
            if history and len(history) > 0:
                last_entry = history[-1]
                if isinstance(last_entry, dict):
                    sources = last_entry.get("sources", [])

            return {
                "query": result["query"],
                "rewritten_query": result.get("rewritten_query", ""),
                "thinking": result.get("thinking", ""),
                "answer": result.get("answer", ""),
                "sources": sources,
                "loop_count": result.get("loop_count", 0)
            }
        except Exception as e:
            logger.error(f"[query] ERROR: {e}", exc_info=True)
            return {
                "query": query,
                "rewritten_query": "",
                "thinking": f"查询出错: {str(e)}",
                "answer": "抱歉，查询过程中出现错误。请稍后重试。",
                "sources": [],
                "loop_count": 0
            }


rag_service = RAGService()
