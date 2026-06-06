# Timeline Feature Design

## Overview

Add a real-time timeline view to the chat interface that shows the multi-round search, thinking, and query rewrite process as it happens, rather than only showing the final result.

## Problem

Currently, the `/api/query` endpoint returns only the final state after multiple rounds of search → think → rewrite loops. The response includes:
- `loop_count`: Number of iterations (but no detail per iteration)
- `rewritten_query`: Final rewritten query (not intermediate ones)
- `thinking`: Last thinking content (not each round's reasoning)
- `answer`: Final answer
- `sources`: Source links

Users cannot see the progression of the AI's reasoning process.

## Solution

Use Server-Sent Events (SSE) to stream timeline events in real-time, allowing the frontend to display the thinking process as it unfolds.

## Architecture

```
┌─────────────────┐
│  chat.html      │  EventSource
│  (Frontend)     │◄──────────────────┐
└─────────────────┘                   │
                                      │
┌─────────────────┐                   │
│  /api/query/    │ SSE Stream        │
│  stream         │◄──────────────────┤
└─────────────────┘                   │
         │                            │
         │ rag_service.query_stream() │
         └────────────────────────────┘
              │ Emits events:
              │ • search_start
              │ • search_complete
              │ • think_complete
              │ • rewrite_complete
              │ • answer_complete
              └─→ Frontend appends to timeline array
```

## Backend Changes

### New Endpoint: `/api/query/stream`

**File:** `app/routes/api.py`

```python
@api_bp.route("/query/stream", methods=["POST"])
def query_stream():
    """SSE endpoint for streaming RAG query timeline."""
    from flask import Response, stream_with_context
    
    data = request.get_json()
    query = data.get("query", "")
    
    def generate():
        try:
            for event in rag_service.query_stream(query):
                yield f"event: {event['type']}\n"
                yield f"data: {json.dumps(event['data'])}\n\n"
        except Exception as e:
            yield f"event: error\n"
            yield f"data: {json.dumps({'error': str(e)})}\n\n"
    
    return Response(
        stream_with_context(generate()),
        mimetype="text/event-stream",
        headers={"Cache-Control": "no-cache"}
    )
```

### Modified RAGService

**File:** `app/services/rag_service.py`

Add new method `query_stream()` that yields events at each step:

```python
def query_stream(self, query: str):
    """Execute RAG query with streaming timeline events."""
    initial_state = {
        "query": query,
        "rewritten_query": "",
        "search_results": [],
        "thinking": "",
        "decision": "",
        "answer": "",
        "loop_count": 0,
        "history": []
    }
    
    # Custom invoke with event emission
    for event_type, event_data in self._streaming_invoke(initial_state):
        yield {"type": event_type, "data": event_data}
```

**Event Types:**

| Event Type | Data Fields | Description |
|------------|-------------|-------------|
| `search_start` | `query` | Search is starting |
| `search_complete` | `iteration`, `results_count`, `query` | Search finished |
| `think_complete` | `iteration`, `reasoning`, `decision` | Thinking finished |
| `rewrite_complete` | `iteration`, `new_query` | Query rewritten |
| `answer_complete` | `answer`, `sources`, `total_iterations` | Final answer ready |
| `error` | `error` | Error occurred |

## Frontend Changes

### Alpine.js Component Updates

**File:** `app/templates/chat.html`

Add new state and EventSource handling:

```javascript
function chatApp() {
    return {
        query: '',
        loading: false,
        result: null,
        timeline: [],
        showTimeline: false,
        
        async submitQuery() {
            this.loading = true;
            this.result = null;
            this.timeline = [];
            
            const eventSource = new EventSource(
                `/api/query/stream?query=${encodeURIComponent(this.query)}`
            );
            
            eventSource.addEventListener('search_start', (e) => {
                const data = JSON.parse(e.data);
                this.timeline.push({
                    type: 'search',
                    status: 'start',
                    timestamp: new Date(),
                    query: data.query
                });
            });
            
            // ... other event handlers
            
            eventSource.addEventListener('answer_complete', (e) => {
                const data = JSON.parse(e.data);
                this.result = {
                    answer: data.answer,
                    sources: data.sources,
                    loop_count: data.total_iterations
                };
                eventSource.close();
                this.loading = false;
            });
            
            eventSource.onerror = () => {
                eventSource.close();
                this.loading = false;
            };
        }
    };
}
```

### Timeline UI Component

Inside the "信息溯源" card, add collapsible timeline:

```html
<!-- Timeline Section -->
<div class="mb-4">
    <button 
        @click="showTimeline = !showTimeline" 
        class="flex items-center space-x-2 text-sm text-gray-600 mb-2 w-full text-left"
    >
        <i data-lucide="clock" class="w-4 h-4"></i>
        <span>处理时间线 (<span x-text="timeline.length"></span> 步)</span>
        <i data-lucide="chevron-down" class="w-4 h-4 ml-auto" :class="{'rotate-180': showTimeline}"></i>
    </button>
    
    <div x-show="showTimeline" class="space-y-2 ml-6">
        <template x-for="(event, index) in timeline" :key="index">
            <div class="relative pl-6 pb-4 border-l-2 border-gray-200">
                <div class="absolute -left-2 top-0 w-4 h-4 rounded-full bg-blue-500"></div>
                
                <!-- Search Event -->
                <div x-show="event.type === 'search'" class="bg-gray-50 rounded p-2">
                    <div class="font-medium text-gray-700">搜索</div>
                    <div x-show="event.status === 'complete'" class="text-gray-500 text-xs mt-1">
                        找到 <span x-text="event.resultsCount"></span> 条结果
                    </div>
                </div>
                
                <!-- Think Event -->
                <div x-show="event.type === 'think'" class="bg-yellow-50 rounded p-2">
                    <div class="font-medium text-gray-700">思考 <span class="text-gray-400 text-xs">Round <span x-text="event.iteration"></span></span></div>
                    <div class="text-gray-600 text-xs mt-1" x-text="event.reasoning"></div>
                    <div class="mt-1">
                        <span class="px-1 rounded text-xs" 
                              :class="event.decision === 'CONTINUE' ? 'bg-blue-100 text-blue-700' : 'bg-green-100 text-green-700'"
                              x-text="event.decision">
                        </span>
                    </div>
                </div>
                
                <!-- Rewrite Event -->
                <div x-show="event.type === 'rewrite'" class="bg-blue-50 rounded p-2">
                    <div class="font-medium text-gray-700">查询重写</div>
                    <div class="text-gray-600 text-xs mt-1" x-text="event.newQuery"></div>
                </div>
            </div>
        </template>
    </div>
</div>
```

## Data Structure

### Timeline Event (Frontend)

```typescript
interface TimelineEvent {
    type: 'search' | 'think' | 'rewrite';
    timestamp: Date;
    
    // Search-specific
    status?: 'start' | 'complete';
    resultsCount?: number;
    
    // Think-specific
    iteration?: number;
    reasoning?: string;
    decision?: 'CONTINUE' | 'ANSWER';
    
    // Rewrite-specific
    newQuery?: string;
}
```

## Error Handling

1. **SSE Connection Error:** Fallback to standard `/api/query` endpoint
2. **Event Parse Error:** Log and continue (don't break UI)
3. **Backend Error Stream:** Send `error` event, close connection

## Testing Plan

1. **Unit Tests:**
   - Test `query_stream()` event emission
   - Test event parsing in frontend

2. **Integration Tests:**
   - End-to-end SSE flow
   - Connection failure handling

3. **Manual Testing with Chrome DevTools:**
   - Open Network tab, filter for EventStream
   - Verify events are received in correct order
   - Verify UI updates correctly
   - Test with queries that require multiple iterations
   - Test with queries that answer in one iteration

## Implementation Steps

1. Add `/api/query/stream` endpoint to `app/routes/api.py`
2. Add `query_stream()` method to `rag_service.py`
3. Modify LangGraph workflow to emit events
4. Update `chat.html` with EventSource handling
5. Add timeline UI component
6. Test with Chrome DevTools MCP
7. Verify page and API work correctly

## Notes

- Keep original `/api/query` endpoint for backward compatibility
- Timeline is collapsed by default (minimal UI)
- Each event shows timestamp for progression visibility
- Color-coded events: gray (search), yellow (think), blue (rewrite)
