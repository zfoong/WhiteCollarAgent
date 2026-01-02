from core.action.action_framework.registry import action

@action(
    name="google search",
    description="Performs a Google search using Google Custom Search API if credentials exist, otherwise falls back to DuckDuckGo (ddgs). Automatically returns text, image, video, or news results based on the query.",
    default=True,
    input_schema={
        "query": {
            "type": "string",
            "example": "latest AI developments 2025",
            "description": "The query to search for."
        },
        "num_results": {
            "type": "integer",
            "example": 5,
            "description": "Number of results (1\u201320)."
        }
    },
    output_schema={
        "search_results": {
            "type": "array",
            "description": "List of search\u2010result objects containing {title, url, content, type}."
        }
    },
    requirement=["ClientSession", "DDGS", "build", "aiohttp", "duckduckgo-search", "google-api-python-client"],
    test_payload={
        "query": "latest AI developments 2025",
        "num_results": 5,
        "simulated_mode": True
    }
)
def google_search(input_data: dict) -> dict:
    import os, json, asyncio, random, re
    
    simulated_mode = input_data.get('simulated_mode', False)
    
    if simulated_mode:
        # Return mock result for testing
        query = input_data.get('query', '')
        num_results = int(input_data.get('num_results', 5))
        return {
            'status': 'success',
            'search_results': [
                {'title': f'Test result {i} for {query}', 'url': 'https://example.com', 'content': 'Test content', 'type': 'text'}
                for i in range(num_results)
            ]
        }
    
    from aiohttp import ClientSession, ClientTimeout
    from ddgs import DDGS

    UA_LIST = [
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64)',
        'Mozilla/5.0 (Macintosh; Intel Mac OS X 13_6)',
        'Mozilla/5.0 (X11; Ubuntu; Linux x86_64)'
    ]

    def _random_ua(): return random.choice(UA_LIST)

    def _normalise_ws(t): return re.sub(r'\s+', ' ', (t or '')).strip()

    def _strip_links_images(t): return re.sub(r'!\[.*?\]\([^)]*\)', '', t or '')

    async def _fetch(session, url):
        try:
            async with session.get(url, timeout=10) as r:
                if r.status == 200: return await r.text()
        except: return ''
        return ''

    async def duckduckgo_search(query, num_results=5):
        results = []
        mode = 'text'
        dd = DDGS()
        with dd:
            hits = list(dd.text(query, max_results=num_results))
            for hit in hits:
                url = hit.get('url') or hit.get('href')
                entry = {
                    'title': _normalise_ws(hit.get('title') or 'Untitled'),
                    'url': url,
                    'content': _strip_links_images(_normalise_ws(hit.get('description') or '')),
                    'type': mode
                }
                results.append(entry)
        return results

    async def google_search(query, num_results=5):
        try:
            from googleapiclient.discovery import build
            api_key = os.getenv('GOOGLE_API_KEY')
            cse_id = os.getenv('GOOGLE_CSE_ID')
            if not api_key or not cse_id: raise Exception('No API key')
            service = build('customsearch', 'v1', developerKey=api_key)
            res = service.cse().list(q=query, cx=cse_id, num=num_results).execute()
            items = res.get('items', [])
            return [{
                'title': _normalise_ws(i.get('title', 'Untitled')),
                'url': i.get('link'),
                'content': _normalise_ws(i.get('snippet', '')),
                'type': 'text'
            } for i in items]
        except:
            return await duckduckgo_search(query, num_results)

    query = input_data.get('query', '')
    if not query:
        return {'status': 'error', 'message': 'query is mandatory.', 'search_results': []}
    num_results = int(input_data.get('num_results', 5))
    results = asyncio.run(google_search(query, num_results))
    return {'status': 'success', 'search_results': results}