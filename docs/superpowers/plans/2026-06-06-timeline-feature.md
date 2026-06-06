# Timeline Feature Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add real-time timeline display to the chat interface showing multi-round search, thinking, and query rewrite process using Server-Sent Events (SSE).

**Architecture:** Frontend uses EventSource to connect to new `/api/query/stream` SSE endpoint. Backend RAGService emits events at each workflow step (search, think, rewrite, answer). Frontend appends events to timeline array and renders in collapsible UI inside "信息溯源" card.

**Tech Stack:** Flask (SSE via Response), Alpine.js (EventSource, reactive timeline state), LangGraph (event emission in workflow)

---

## File Structure

**New Files:**
- None

**Modified Files:**
- `app/routes/api.py` - Add `/api/query/stream` SSE endpoint
- `app/services/rag_service.py` - Add `query_stream()` method with event emission
- `app/templates/chat.html` - Add EventSource handling and timeline UI

---

## Task 1: Add SSE Endpoint to API Routes

**Files:**
- Modify: `app/routes/api.py`

- [ ] **Step 1: Add SSE import and endpoint**

Add the SSE streaming endpoint after the existing `/query` endpoint (around line 25):

```python
@api_bp.route("/query/stream", methods=["POST"])
def query_stream():
    """SSE endpoint for streaming RAG query timeline."""
    from flask import Response, stream_with_context
    import json
    from loguru import logger
    
    data = request.get_json()
    query = data.get("query", "")
    
    if not query:
        # Return error as SSE event
        def error_gen():
            yield f"event: error\n"
            yield f"data: {json.dumps({'error': 'Query is required'})}\n\n"
        return Response(error_gen(), mimetype="text/event-stream")
    
    try:
        def generate():
            try:
                for event in rag_service.query_stream(query):
                    yield f"event: {event['type']}\n"
                    yield f"data: {json.dumps(event['data'])}\n\n"
            except Exception as e:
                logger.error(f"Query stream error: {e}", exc_info=True)
                yield f"event: error\n"
                yield f"data: {json.dumps({'error': str(e)})}\n\n"
        
        return Response(
            stream_with_context(generate()),
            mimetype="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "X-Accel-Buffering": "no"
            }
        )
    except Exception as e:
        logger.error(f"Query stream failed: {e}", exc_info=True)
        return jsonify({"error": str(e)}), 500
```

- [ ] **Step 2: Run server to verify no syntax errors**

Run: `python -c "from app.routes.api import api_bp; print('Import successful')"`
Expected: "Import successful" with no errors

- [ ] **Step 3: Commit**

```bash
git add app/routes/api.py
git commit -m "feat: add /api/query/stream SSE endpoint"
```

---

## Task 2: Add Event Generator Method to RAGService

**Files:**
- Modify: `app/services/rag_service.py`

- [ ] **Step 1: Add query_stream method stub**

Add the new method after the existing `query()` method (around line 240):

```python
def query_stream(self, query: str):
    """Execute RAG query with streaming timeline events.
    
    Yields events as they happen during the RAG workflow:
    - search_start, search_complete
    - think_complete
    - rewrite_complete  
    - answer_complete
    - error (if something goes wrong)
    """
    import json
    
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
    
    try:
        # Emit search start
        yield {"type": "search_start", "data": {"query": query}}
        
        # Search
        current_query = query
        search_results = []
        loop_count = 0
        
        while loop_count <= settings.max_thinking_loops:
            loop_count += 1
            
            # Emit search complete
            results = db_service.search(current_query, limit=settings.max_search_results)
            search_results.extend(results)
            yield {
                "type": "search_complete",
                "data": {
                    "iteration": loop_count,
                    "results_count": len(results),
                    "query": current_query
                }
            }
            
            # Think
            context = "\n".join([
                f"- {r['title']} ({r['article_title']}): {r['description']}"
                for r in results
            ])
            
            think_prompt = f"""用户查询: {current_query}

搜索结果:
{context}

请分析:
1. 这些结果是否足够回答用户查询?
2. 如果不够，需要如何改进搜索keywords?

返回格式:
DECISION: [CONTINUE/ANSWER]
REASONING: [你的分析过程]
IMPROVED_QUERY: [如果需要继续，提供改进的查询keywords]"""
            
            messages = [
                {"role": "system", "content": "You are a helpful assistant that analyzes search results and decides if more information is needed."},
                {"role": "user", "content": think_prompt}
            ]
            response = self.llm.invoke(messages)
            content = response.content.strip()
            
            # Parse think response
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
            
            # Emit think complete
            yield {
                "type": "think_complete",
                "data": {
                    "iteration": loop_count,
                    "reasoning": reasoning,
                    "decision": decision
                }
            }
            
            # Check if should continue
            if decision == "ANSWER" or loop_count >= settings.max_thinking_loops:
                break
            
            # Emit rewrite complete
            yield {
                "type": "rewrite_complete",
                "data": {
                    "iteration": loop_count,
                    "new_query": improved_query
                }
            }
            
            current_query = improved_query
        
        # Generate final answer
        context_parts = []
        for r in search_results:
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
        
        # Extract unique sources
        sources = list({r["link"] for r in search_results})
        
        # Emit answer complete
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
```

- [ ] **Step 2: Run server to verify no syntax errors**

Run: `python -c "from app.services.rag_service import rag_service; print('Import successful')"`
Expected: "Import successful" with no errors

- [ ] **Step 3: Commit**

```bash
git add app/services/rag_service.py
git commit -m "feat: add query_stream method with event emission"
```

---

## Task 3: Add Timeline State to Frontend

**Files:**
- Modify: `app/templates/chat.html`

- [ ] **Step 1: Add timeline state variables**

Update the `chatApp()` function to add new state (around line 193):

```javascript
function chatApp() {
    return {
        query: '',
        loading: false,
        loadingDots: '',
        result: null,
        dotsInterval: null,
        
        // New timeline state
        timeline: [],
        showTimeline: false,
```

- [ ] **Step 2: Add helper function for formatted time**

Add after `stopLoadingAnimation()` method (around line 220):

```javascript
                },

                formatTime(timestamp) {
                    if (!timestamp) return '';
                    const date = new Date(timestamp);
                    return date.toLocaleTimeString('zh-CN', { 
                        hour: '2-digit', 
                        minute: '2-digit',
                        second: '2-digit'
                    });
                },
```

- [ ] **Step 3: Commit**

```bash
git add app/templates/chat.html
git commit -m "feat: add timeline state to chat frontend"
```

---

## Task 4: Replace submitQuery with EventSource Implementation

**Files:**
- Modify: `app/templates/chat.html`

- [ ] **Step 1: Replace submitQuery method with SSE version**

Replace the entire `submitQuery()` method (around line 222-251) with:

```javascript
                async submitQuery() {
                    if (!this.query.trim()) return;

                    this.loading = true;
                    this.result = null;
                    this.timeline = [];
                    this.startLoadingAnimation();

                    try {
                        // Use EventSource for SSE
                        const formData = new FormData();
                        formData.append('query', this.query);
                        
                        const response = await fetch('/api/query/stream', {
                            method: 'POST',
                            headers: {
                                'Content-Type': 'application/json',
                            },
                            body: JSON.stringify({ query: this.query })
                        });

                        if (!response.ok) {
                            throw new Error('搜索失败');
                        }

                        // Read SSE stream
                        const reader = response.body.getReader();
                        const decoder = new TextDecoder();
                        let buffer = '';

                        while (true) {
                            const { done, value } = await reader.read();
                            if (done) break;

                            buffer += decoder.decode(value, { stream: true });
                            
                            // Process complete SSE messages
                            const lines = buffer.split('\n\n');
                            buffer = lines.pop(); // Keep incomplete message in buffer

                            for (const line of lines) {
                                if (!line.trim()) continue;
                                
                                const lines_list = line.split('\n');
                                let eventType = 'message';
                                let data = {};

                                for (const l of lines_list) {
                                    if (l.startsWith('event: ')) {
                                        eventType = l.substring(7);
                                    } else if (l.startsWith('data: ')) {
                                        try {
                                            data = JSON.parse(l.substring(6));
                                        } catch (e) {
                                            console.error('Failed to parse SSE data:', l);
                                        }
                                    }
                                }

                                // Handle events
                                this.handleSSEEvent(eventType, data);
                            }
                        }

                    } catch (error) {
                        console.error('Error:', error);
                        
                        // Add error to timeline
                        this.timeline.push({
                            type: 'error',
                            message: error.message,
                            timestamp: new Date()
                        });
                        
                        alert('搜索失败: ' + error.message);
                    } finally {
                        this.loading = false;
                        this.stopLoadingAnimation();
                        lucide.createIcons();
                    }
                },

                handleSSEEvent(eventType, data) {
                    const timestamp = new Date();

                    switch (eventType) {
                        case 'search_start':
                            this.timeline.push({
                                type: 'search',
                                status: 'start',
                                query: data.query,
                                timestamp
                            });
                            break;

                        case 'search_complete':
                            // Update last search event or add new
                            const lastSearch = this.timeline.findLast(t => t.type === 'search');
                            if (lastSearch) {
                                lastSearch.status = 'complete';
                                lastSearch.resultsCount = data.results_count;
                            } else {
                                this.timeline.push({
                                    type: 'search',
                                    status: 'complete',
                                    resultsCount: data.results_count,
                                    timestamp
                                });
                            }
                            break;

                        case 'think_complete':
                            this.timeline.push({
                                type: 'think',
                                iteration: data.iteration,
                                reasoning: data.reasoning,
                                decision: data.decision,
                                timestamp
                            });
                            break;

                        case 'rewrite_complete':
                            this.timeline.push({
                                type: 'rewrite',
                                iteration: data.iteration,
                                newQuery: data.new_query,
                                timestamp
                            });
                            break;

                        case 'answer_complete':
                            this.result = {
                                answer: data.answer,
                                sources: data.sources,
                                loop_count: data.total_iterations
                            };
                            break;

                        case 'error':
                            this.timeline.push({
                                type: 'error',
                                message: data.error,
                                timestamp
                            });
                            this.loading = false;
                            this.stopLoadingAnimation();
                            break;
                    }
                },
```

- [ ] **Step 2: Verify no syntax errors**

Open the HTML file in a browser console or run: `grep -n "submitQuery" app/templates/chat.html` to verify the method exists
Expected: Method definition found

- [ ] **Step 3: Commit**

```bash
git add app/templates/chat.html
git commit -m "feat: implement SSE-based submitQuery with event handling"
```

---

## Task 5: Add Timeline UI Component

**Files:**
- Modify: `app/templates/chat.html`

- [ ] **Step 1: Add timeline section to "信息溯源" card**

Add the timeline section inside the RAG Process Tracker div, after the "Sources" section (around line 177, before the closing `</div>` of the card):

```html

                    <!-- Timeline -->
                    <div class="mt-4">
                        <button 
                            @click="showTimeline = !showTimeline" 
                            class="flex items-center space-x-2 text-sm text-gray-600 mb-2 w-full text-left hover:text-gray-800 transition-colors"
                        >
                            <i data-lucide="clock" class="w-4 h-4"></i>
                            <span>处理时间线 (<span x-text="timeline.length"></span> 步)</span>
                            <i data-lucide="chevron-down" class="w-4 h-4 ml-auto transition-transform" :class="{'rotate-180': showTimeline}"></i>
                        </button>
                        
                        <div x-show="showTimeline" class="space-y-2 ml-6" x-transition:enter="transition ease-out duration-200" x-transition:enter-start="opacity-0 -translate-y-2" x-transition:enter-end="opacity-100 translate-y-0">
                            <template x-for="(event, index) in timeline" :key="index">
                                <div class="relative pl-6 pb-4 border-l-2 border-gray-200 last:pb-0">
                                    <!-- Timeline dot -->
                                    <div class="absolute -left-2 top-0 w-4 h-4 rounded-full border-2 border-white"
                                         :class="{
                                             'bg-blue-500': event.type === 'search',
                                             'bg-yellow-500': event.type === 'think',
                                             'bg-purple-500': event.type === 'rewrite',
                                             'bg-red-500': event.type === 'error'
                                         }">
                                    </div>
                                    
                                    <!-- Event content -->
                                    <div class="text-sm">
                                        <!-- Search event -->
                                        <div x-show="event.type === 'search'" class="bg-gray-50 rounded p-2">
                                            <div class="flex items-center justify-between">
                                                <div class="font-medium text-gray-700 flex items-center space-x-1">
                                                    <i data-lucide="search" class="w-3 h-3"></i>
                                                    <span>搜索</span>
                                                </div>
                                                <span class="text-xs text-gray-400" x-text="formatTime(event.timestamp)"></span>
                                            </div>
                                            <div x-show="event.status === 'complete'" class="text-gray-500 text-xs mt-1">
                                                找到 <span class="font-medium text-gray-700" x-text="event.resultsCount"></span> 条结果
                                            </div>
                                            <div x-show="event.status === 'start'" class="text-gray-400 text-xs mt-1">
                                                正在搜索...
                                            </div>
                                        </div>
                                        
                                        <!-- Think event -->
                                        <div x-show="event.type === 'think'" class="bg-yellow-50 rounded p-2">
                                            <div class="flex items-center justify-between mb-1">
                                                <div class="font-medium text-gray-700 flex items-center space-x-1">
                                                    <i data-lucide="brain" class="w-3 h-3"></i>
                                                    <span>思考</span>
                                                    <span class="text-gray-400 text-xs">Round <span x-text="event.iteration"></span></span>
                                                </div>
                                                <span class="text-xs text-gray-400" x-text="formatTime(event.timestamp)"></span>
                                            </div>
                                            <div class="text-gray-600 text-xs mt-1 leading-relaxed" x-text="event.reasoning"></div>
                                            <div class="mt-2">
                                                <span class="px-2 py-0.5 rounded text-xs font-medium"
                                                      :class="event.decision === 'CONTINUE' ? 'bg-blue-100 text-blue-700' : 'bg-green-100 text-green-700'"
                                                      x-text="event.decision">
                                                </span>
                                            </div>
                                        </div>
                                        
                                        <!-- Rewrite event -->
                                        <div x-show="event.type === 'rewrite'" class="bg-purple-50 rounded p-2">
                                            <div class="flex items-center justify-between mb-1">
                                                <div class="font-medium text-gray-700 flex items-center space-x-1">
                                                    <i data-lucide="edit-3" class="w-3 h-3"></i>
                                                    <span>查询重写</span>
                                                    <span class="text-gray-400 text-xs">Round <span x-text="event.iteration"></span></span>
                                                </div>
                                                <span class="text-xs text-gray-400" x-text="formatTime(event.timestamp)"></span>
                                            </div>
                                            <div class="bg-white rounded px-2 py-1 mt-1">
                                                <code class="text-xs text-purple-700" x-text="event.newQuery"></code>
                                            </div>
                                        </div>
                                        
                                        <!-- Error event -->
                                        <div x-show="event.type === 'error'" class="bg-red-50 rounded p-2">
                                            <div class="flex items-center justify-between mb-1">
                                                <div class="font-medium text-red-700 flex items-center space-x-1">
                                                    <i data-lucide="alert-circle" class="w-3 h-3"></i>
                                                    <span>错误</span>
                                                </div>
                                                <span class="text-xs text-gray-400" x-text="formatTime(event.timestamp)"></span>
                                            </div>
                                            <div class="text-red-600 text-xs" x-text="event.message"></div>
                                        </div>
                                    </div>
                                </div>
                            </template>
                            
                            <!-- Empty state -->
                            <div x-show="timeline.length === 0" class="text-center py-4 text-gray-400 text-sm">
                                等待查询开始...
                            </div>
                        </div>
                    </div>
```

- [ ] **Step 2: Verify HTML structure**

Open file and check the timeline section is properly nested
Expected: Timeline section inside the RAG Process Tracker card, properly closed

- [ ] **Step 3: Commit**

```bash
git add app/templates/chat.html
git commit -m "feat: add timeline UI component with collapsible display"
```

---

## Task 6: Manual Testing with Chrome DevTools

**Files:**
- None (testing)

- [ ] **Step 1: Start the Flask server**

Run: `flask run`
Expected: Server starts on http://127.0.0.1:5000

- [ ] **Step 2: Open Chrome DevTools and navigate to chat page**

Open Chrome browser, press F12 for DevTools, navigate to http://127.0.0.1:5000

- [ ] **Step 3: Test basic query submission**

In the chat input, enter: "如何提升学习效率?"
Expected: Loading animation shows, results appear

- [ ] **Step 4: Inspect Network tab for SSE connection**

In DevTools Network tab, filter for "EventStream" or "stream"
Expected: See `/api/query/stream` request with type `event-stream`

- [ ] **Step 5: Verify timeline events in Network tab**

Click on the stream request, go to "EventStream" or "Response" tab
Expected: See events in order: search_start, search_complete, think_complete, etc.

- [ ] **Step 6: Test timeline UI expansion**

Click "处理时间线" button to expand
Expected: Timeline expands showing all events with timestamps

- [ ] **Step 7: Test multi-round query**

Enter query that likely requires multiple iterations: "代码报错没有输出怎么办?"
Expected: Timeline shows multiple rounds with CONTINUE decisions

- [ ] **Step 8: Test error handling**

Stop the Flask server and submit a query
Expected: Error message appears in timeline and alert shows

- [ ] **Step 9: Document test results**

Create a brief test notes file:
```bash
cat > /tmp/timeline_test_notes.md << 'EOF'
# Timeline Feature Test Notes

## Test Environment
- Date: 2026-06-06
- Browser: Chrome with DevTools
- Server: Flask local development

## Test Cases Passed
- [ ] Basic query submission
- [ ] SSE connection established
- [ ] Timeline events received in correct order
- [ ] Timeline UI expands/collapses
- [ ] Multi-round queries show multiple iterations
- [ ] Error handling works
- [ ] Timestamps display correctly
- [ ] Color-coded event types
EOF
```

- [ ] **Step 10: Commit test notes**

```bash
git add /tmp/timeline_test_notes.md
git commit -m "test: document timeline feature manual test results"
```

---

## Task 7: Final Verification and Polish

**Files:**
- Modify: `app/templates/chat.html` (if needed)
- Modify: `app/services/rag_service.py` (if needed)

- [ ] **Step 1: Check for any console errors in browser**

Open browser console (F12 → Console tab)
Expected: No JavaScript errors

- [ ] **Step 2: Verify timeline updates in real-time**

Submit a query and watch timeline expand during loading
Expected: Events appear one by one, not all at once at the end

- [ ] **Step 3: Check that original /api/query still works**

Test the old endpoint with curl:
```bash
curl -X POST http://127.0.0.1:5000/api/query \
  -H "Content-Type: application/json" \
  -d '{"query":"test"}'
```
Expected: JSON response with answer, sources, loop_count

- [ ] **Step 4: Verify responsive design**

Resize browser window to mobile size
Expected: Timeline still displays correctly on small screens

- [ ] **Step 5: Clean up any temporary code or comments**

Review all changed files for TODO comments or debug code
Expected: No temporary code remains

- [ ] **Step 6: Final commit**

```bash
git add app/routes/api.py app/services/rag_service.py app/templates/chat.html
git commit -m "polish: final cleanup and verification of timeline feature"
```

---

## Summary

This plan implements the timeline feature through:

1. **SSE Endpoint** (`/api/query/stream`) - Streams events in real-time
2. **Event Generator** (`query_stream()`) - Emits events at each workflow step  
3. **Frontend Integration** - EventSource handling with timeline state
4. **Timeline UI** - Collapsible component showing all events with timestamps

**Testing Strategy:**
- Manual testing with Chrome DevTools Network tab
- Verify SSE connection and event flow
- Test multi-round queries and error handling

**Success Criteria:**
- Timeline shows all workflow steps in real-time
- UI is collapsible and color-coded by event type
- Original `/api/query` endpoint still works
- No console errors or bugs
