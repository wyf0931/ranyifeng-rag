from typing import Dict, Any, List, TypedDict
from loguru import logger
from langchain_openai import ChatOpenAI
from langgraph.graph import StateGraph, END
from app.config import settings
from app.services.database import db_service


class RAGState(TypedDict):
    query: str
    rewritten_query: str
    search_results: List[Dict[str, Any]]
    thinking: str
    decision: str
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

    def think_and_rewrite(self, state: RAGState) -> RAGState:
        """Think about search results and rewrite query for better search.

        This merged node:
        1. Analyzes if current search results are sufficient
        2. If not sufficient, extracts relevant terms from search results
        3. Outputs both reasoning and improved keywords in one step

        Example: User searches "油猴 脚本", results contain "tampermonkey"
        The LLM should extract "tampermonkey" as a new keyword.
        """
        query = state.get("rewritten_query") or state["query"]
        results = state.get("search_results", [])
        loop_count = state.get("loop_count", 0) + 1
        logger.info(f"[think_and_rewrite] START - query: {query}, results_count: {len(results)}, loop_count: {loop_count}")

        try:
            # Format search results with rich context
            context = "\n".join([
                f"- 标题: {r['title']}\n  来源: {r['article_title']}\n  描述: {r['description']}"
                for r in results
            ])

            logger.info(f"[think_and_rewrite] Calling LLM with context length: {len(context)} chars")

            prompt = f"""用户查询: {query}

搜索结果:
{context}

请分析:
1. 这些结果是否足够回答用户查询?
2. 如果不够，请从搜索结果的标题和描述中提取相关关键词，结合用户查询生成改进的搜索keywords

重要提示:
- 优先使用搜索结果中出现的专业术语、英文名、同义词
- 例如: 用户搜"油猴 脚本"，结果中包含"Tampermonkey"，则应提取"Tampermonkey"作为关键词
- 例如: 用户搜"前端框架"，结果中包含"React Vue Angular"，则应提取这些框架名

返回格式:
DECISION: [CONTINUE/ANSWER]
REASONING: [你的分析过程]
IMPROVED_QUERY: [如果需要继续，提供改进的查询keywords，应包含从搜索结果提取的相关术语]"""

            logger.info(f"[think_and_rewrite] Invoking LLM...")

            messages = [
                {"role": "system", "content": "You are a helpful assistant that analyzes search results and improves search queries by extracting relevant terms from results."},
                {"role": "user", "content": prompt}
            ]
            response = self.llm.invoke(messages)

            content = response.content.strip()
            logger.info(f"[think_and_rewrite] LLM response received, length: {len(content)} chars")

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
            state["decision"] = decision
            state["rewritten_query"] = improved_query
            state["loop_count"] = loop_count

            # Check loop limit
            if loop_count >= settings.max_thinking_loops:
                decision = "ANSWER"
                state["decision"] = decision

            logger.info(f"[think_and_rewrite] END - decision: {decision}, improved_query: {improved_query}")
            return state
        except Exception as e:
            logger.error(f"[think_and_rewrite] ERROR: {e}", exc_info=True)
            state["thinking"] = f"思考过程出错: {str(e)}"
            state["decision"] = "ANSWER"
            state["loop_count"] = loop_count
            return state

    def search_node(self, state: RAGState) -> RAGState:
        """Search for relevant content."""
        query = state.get("rewritten_query") or state["query"]
        logger.info(f"[search] START - query: {query}")
        results = db_service.search(query, limit=settings.max_search_results)
        state["search_results"] = results
        logger.info(f"[search] END - found {len(results)} results")
        return state

    def generate_node(self, state: RAGState) -> RAGState:
        """Generate final answer based on all search results."""
        query = state["query"]
        results = state.get("search_results", [])
        logger.info(f"[generate] START - query: {query}, results_count: {len(results)}")

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

            logger.info(f"[generate] END - answer generated successfully")
            return state
        except Exception as e:
            logger.error(f"[generate] ERROR: {e}", exc_info=True)
            state["answer"] = f"生成回答时出错: {str(e)}\n\n搜索结果:\n" + "\n".join([
                f"- {r['title']}: {r['description']}"
                for r in results[:5]
            ])
            return state

    def should_continue(self, state: RAGState) -> str:
        """Decide whether to continue searching or generate answer."""
        decision = state.get("decision", "ANSWER")
        loop_count = state.get("loop_count", 0)

        if loop_count >= settings.max_thinking_loops:
            return "generate"

        if decision == "CONTINUE":
            return "search"  # Go to search with improved query
        return "generate"

    def _build_graph(self) -> StateGraph:
        """Build RAG workflow graph using LangGraph."""
        # Build graph
        workflow = StateGraph(RAGState)

        workflow.add_node("search", self.search_node)
        workflow.add_node("think_and_rewrite", self.think_and_rewrite)
        workflow.add_node("generate", self.generate_node)

        workflow.set_entry_point("search")
        workflow.add_conditional_edges(
            "search",
            lambda state: "think_and_rewrite" if state.get("search_results") else "generate",
            {
                "think_and_rewrite": "think_and_rewrite",
                "generate": "generate"
            }
        )

        workflow.add_conditional_edges(
            "think_and_rewrite",
            self.should_continue,
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
                "decision": "",
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

    def query_stream(self, query: str):
        """Execute RAG query with streaming timeline events.

        Yields events as they happen during the RAG workflow:
        - search_start, search_complete
        - think_complete (merged think and rewrite)
        - answer_complete
        - error (if something goes wrong)
        """
        try:
            initial_state: RAGState = {
                "query": query,
                "rewritten_query": "",
                "search_results": [],
                "thinking": "",
                "decision": "",
                "answer": "",
                "loop_count": 0,
                "history": []
            }

            yield {"type": "search_start", "data": {"query": query}}

            original_query = query  # Store original query for first iteration display
            current_query = query
            all_search_results = []
            loop_count = 0

            while loop_count <= settings.max_thinking_loops:
                loop_count += 1

                results = db_service.search(current_query, limit=settings.max_search_results)
                all_search_results.extend(results)

                # For first iteration, show original query tokenized keywords
                # For subsequent iterations, show the actual query used
                display_query = original_query if loop_count == 1 else current_query
                tokenized_query = db_service.tokenize_query(display_query)

                yield {
                    "type": "search_complete",
                    "data": {
                        "iteration": loop_count,
                        "results_count": len(results),
                        "query": display_query,
                        "tokenized_query": tokenized_query,
                        "is_original_search": loop_count == 1
                    }
                }

                # Use merged think_and_rewrite prompt
                context = "\n".join([
                    f"- 标题: {r['title']}\n  来源: {r['article_title']}\n  描述: {r['description']}"
                    for r in results
                ])

                think_prompt = f"""用户查询: {current_query}

搜索结果:
{context}

请分析:
1. 这些结果是否足够回答用户查询?
2. 如果不够，请从搜索结果的标题和描述中提取相关关键词，结合用户查询生成改进的搜索keywords

重要提示:
- 优先使用搜索结果中出现的专业术语、英文名、同义词
- 例如: 用户搜"油猴 脚本"，结果中包含"Tampermonkey"，则应提取"Tampermonkey"作为关键词
- 例如: 用户搜"前端框架"，结果中包含"React Vue Angular"，则应提取这些框架名

返回格式:
DECISION: [CONTINUE/ANSWER]
REASONING: [你的分析过程]
IMPROVED_QUERY: [如果需要继续，提供改进的查询keywords，应包含从搜索结果提取的相关术语]"""

                messages = [
                    {"role": "system", "content": "You are a helpful assistant that analyzes search results and improves search queries by extracting relevant terms from results."},
                    {"role": "user", "content": think_prompt}
                ]
                response = self.llm.invoke(messages)
                content = response.content.strip()

                decision = "ANSWER"
                reasoning = ""
                improved_query = current_query

                for line in content.split("\n"):
                    if line.startswith("DECISION:"):
                        decision = line.split(":", 1)[1].strip().upper()
                    elif line.startswith("REASONING:"):
                        reasoning = line.split(":", 1)[1].strip()
                    elif line.startswith("IMPROVED_QUERY:"):
                        improved_query = line.split(":", 1)[1].strip()

                yield {
                    "type": "think_complete",
                    "data": {
                        "iteration": loop_count,
                        "reasoning": reasoning,
                        "decision": decision,
                        "improved_query": improved_query if decision == "CONTINUE" else ""
                    }
                }

                if decision == "ANSWER" or loop_count >= settings.max_thinking_loops:
                    break

                current_query = improved_query

            context_parts = []
            for r in all_search_results:
                context_parts.append(f"""
标题: {r['title']}
来源: {r['article_title']} - {r['article_link']}
描述: {r['description']}
链接: {r['link']}
""")

            context = "\n".join(context_parts)
            answer_prompt = f"""基于以下搜索结果回答用户查询。

用户查询: {query}

搜索结果:
{context}

请提供准确、有帮助的答案。如果搜索结果不足以回答问题，请诚实地说明。"""

            messages = [
                {"role": "system", "content": "You are a helpful assistant that answers questions based on search results from technology weekly articles."},
                {"role": "user", "content": answer_prompt}
            ]
            response = self.llm.invoke(messages)
            answer = response.content.strip()

            sources = list({r["link"] for r in all_search_results})

            yield {
                "type": "answer_complete",
                "data": {
                    "answer": answer,
                    "sources": sources,
                    "total_iterations": loop_count
                }
            }

        except Exception as e:
            logger.error(f"[query_stream] ERROR: {e}", exc_info=True)
            yield {
                "type": "error",
                "data": {"error": str(e)}
            }


rag_service = RAGService()
