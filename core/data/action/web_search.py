from core.action.action_framework.registry import action

@action(
    name="web_search",
    description="Performs web search using Google Custom Search API (if credentials exist) or DuckDuckGo fallback. Supports single query (string) or batch queries (array of strings).",
    default=True,
    mode="CLI",
    action_sets=["web_research"],
    input_schema={
        "query": {
            "type": ["string", "array"],
            "example": "latest AI developments 2025",
            "description": "Search query. Can be a single string or an array of strings for batch search."
        },
        "num_results": {
            "type": "integer",
            "example": 5,
            "description": "Number of results per query (1-20). Defaults to 5."
        },
        "combine_output": {
            "type": "boolean",
            "example": False,
            "description": "For batch queries: if true, combines all results into a single formatted string. Defaults to false."
        }
    },
    output_schema={
        "status": {
            "type": "string",
            "example": "success",
            "description": "'success' or 'error'."
        },
        "search_results": {
            "type": "array",
            "description": "For single query: list of {title, url, content, type}. For batch: list of {query, search_results}."
        },
        "combined_text": {
            "type": "string",
            "description": "Present when combine_output=true. All results as formatted text."
        },
        "message": {
            "type": "string",
            "description": "Error message if status is 'error'."
        }
    },
    requirement=["aiohttp", "duckduckgo-search", "google-api-python-client"],
    test_payload={
        "query": "latest AI developments 2025",
        "num_results": 5,
        "simulated_mode": True
    }
)
def web_search(input_data: dict) -> dict:
    import os, json, asyncio, random, re

    simulated_mode = input_data.get('simulated_mode', False)
    query = input_data.get('query', '')
    num_results = int(input_data.get('num_results', 5))
    combine_output = bool(input_data.get('combine_output', False))

    # Determine if batch mode
    is_batch = isinstance(query, list)
    queries = query if is_batch else [query] if query else []

    if not queries or (len(queries) == 1 and not queries[0]):
        return {'status': 'error', 'message': 'query is required.', 'search_results': []}

    if simulated_mode:
        # Return mock result for testing
        if is_batch:
            results = [
                {
                    'query': q,
                    'search_results': [
                        {'title': f'Test result {i} for {q}', 'url': 'https://example.com', 'content': 'Test content', 'type': 'text'}
                        for i in range(num_results)
                    ]
                }
                for q in queries
            ]
            if combine_output:
                combined = '\n\n'.join(f"{r['query']}:\n" + ' '.join(sr['content'] for sr in r['search_results']) for r in results)
                return {'status': 'success', 'search_results': results, 'combined_text': combined}
            return {'status': 'success', 'search_results': results}
        else:
            return {
                'status': 'success',
                'search_results': [
                    {'title': f'Test result {i} for {queries[0]}', 'url': 'https://example.com', 'content': 'Test content', 'type': 'text'}
                    for i in range(num_results)
                ]
            }

    from ddgs import DDGS

    UA_LIST = [
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64)',
        'Mozilla/5.0 (Macintosh; Intel Mac OS X 13_6)',
        'Mozilla/5.0 (X11; Ubuntu; Linux x86_64)'
    ]

    def _normalise_ws(t):
        return re.sub(r'\s+', ' ', (t or '')).strip()

    def _strip_links_images(t):
        return re.sub(r'!\[.*?\]\([^)]*\)', '', t or '')

    async def duckduckgo_search(q, n=5):
        results = []
        dd = DDGS()
        with dd:
            hits = list(dd.text(q, max_results=n))
            for hit in hits:
                url = hit.get('url') or hit.get('href')
                entry = {
                    'title': _normalise_ws(hit.get('title') or 'Untitled'),
                    'url': url,
                    'content': _strip_links_images(_normalise_ws(hit.get('description') or '')),
                    'type': 'text'
                }
                results.append(entry)
        return results

    async def google_cse_search(q, n=5):
        try:
            from googleapiclient.discovery import build
            api_key = os.getenv('GOOGLE_API_KEY')
            cse_id = os.getenv('GOOGLE_CSE_ID')
            if not api_key or not cse_id:
                raise Exception('No API credentials')
            service = build('customsearch', 'v1', developerKey=api_key)
            res = service.cse().list(q=q, cx=cse_id, num=n).execute()
            items = res.get('items', [])
            return [{
                'title': _normalise_ws(i.get('title', 'Untitled')),
                'url': i.get('link'),
                'content': _normalise_ws(i.get('snippet', '')),
                'type': 'text'
            } for i in items]
        except:
            return await duckduckgo_search(q, n)

    async def do_search(q, n):
        return await google_cse_search(q, n)

    async def run_searches():
        all_results = []
        for q in queries:
            results = await do_search(q, num_results)
            if is_batch:
                all_results.append({'query': q, 'search_results': results})
            else:
                all_results = results
                break
        return all_results

    try:
        results = asyncio.run(run_searches())

        if is_batch and combine_output:
            combined_parts = []
            for r in results:
                content = ' '.join(
                    _normalise_ws(sr.get('content', ''))
                    for sr in r['search_results']
                    if sr.get('content')
                )
                if content:
                    combined_parts.append(f"{r['query']}:\n{content}")
            return {
                'status': 'success',
                'search_results': results,
                'combined_text': '\n\n'.join(combined_parts)
            }

        return {'status': 'success', 'search_results': results}

    except Exception as e:
        return {'status': 'error', 'message': str(e), 'search_results': []}
