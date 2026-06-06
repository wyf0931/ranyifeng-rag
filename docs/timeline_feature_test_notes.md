# Timeline Feature Test Notes

## Test Environment
- Date: 2026-06-06
- Browser: Chrome with DevTools
- Server: Flask local development (port 5001)
- Implementation: SSE-based real-time timeline

## Test Cases Passed
- [x] Basic query submission - "如何提升学习效率？"
- [x] SSE connection established - `/api/query/stream` returned 200
- [x] Timeline events received in correct order:
  1. search_start
  2. search_complete (×3 iterations)
  3. think_complete (×3 with CONTINUE decisions)
  4. rewrite_complete (×2 with new queries)
  5. answer_complete
- [x] Timeline UI expands/collapses correctly
- [x] Multi-round queries show multiple iterations (3 rounds)
- [x] Timestamps display correctly (18:00:10, 18:00:47, 18:01:21, 18:22:22)
- [x] Color-coded event types working:
  - Blue dots for search events
  - Yellow dots for think events  
  - Purple dots for rewrite events
- [x] Event content displays correctly:
  - Search shows results count
  - Think shows reasoning and decision (CONTINUE/ANSWER)
  - Rewrite shows new query keywords
- [x] Timeline step counter shows correct count (6 步)
- [x] Answer displays properly with markdown formatting
- [x] Sources list shows correctly (24 sources)

## Network Verification
- SSE Response Headers verified:
  - `content-type: text/event-stream; charset=utf-8`
  - `cache-control: no-cache`
  - `x-accel-buffering: no`
- Events properly formatted with `event:` and `data:` prefixes
- UTF-8 encoding works correctly for Chinese characters

## Screenshot Captures
- Initial state: Empty search page
- Loading state: "可信AI，有依据，才可信！ Thinking..."
- Complete state: Answer + sources + timeline button
- Expanded timeline: All 6 events visible with details

## Success Metrics Met
✅ Real-time timeline display showing multi-round process
✅ Collapsible UI inside existing "信息溯源" card
✅ Color-coded events with timestamps
✅ Backend events flow matches design spec
✅ Frontend EventSource integration working
✅ No console errors (only production warnings about CDN)
✅ Page renders correctly on desktop

## Notes
- Timeline shows the actual thinking process with detailed reasoning in Chinese
- Query rewrites are visible, showing how keywords evolved
- Decision badges (CONTINUE/ANSWER) properly styled
- Each event has accurate timestamp
- Original `/api/query` endpoint preserved for backward compatibility
