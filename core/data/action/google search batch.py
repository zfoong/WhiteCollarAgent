from core.action.action_framework.registry import action

@action(
    name="google search batch",
    description="Performs searches for a list of queries. Uses Google Custom Search API when credentials exist, otherwise falls back to DuckDuckGo (ddgs). Returns a single JSON object containing a single PDF-ready string when pdf=true, with all queries as headings and combined content.",
    platforms=["linux", "windows", "darwin"],
    mode="CLI",
    input_schema={
        "queries": {
            "type": "array",
            "items": {
                "type": "string"
            },
            "example": [
                "latest AI news",
                "best cloud providers 2025"
            ],
            "description": "List of search queries."
        },
        "num_results": {
            "type": "integer",
            "example": 5,
            "description": "Number of results per query."
        },
        "pdf": {
            "type": "boolean",
            "example": False,
            "description": "If true, returns a single JSON object with all queries as headings and combined content in one string."
        }
    },
    output_schema={
        "results": {
            "type": "string",
            "description": "When pdf=true, returns a single string with all queries as headings and their combined content. When pdf=false, returns a JSON list of search results per query."
        }
    },
    requirement=["build", "DDGS", "google-api-python-client", "duckduckgo-search"],
    test_payload={
        "queries": [
            "latest AI news",
            "best cloud providers 2025"
        ],
        "num_results": 5,
        "pdf": False,
        "simulated_mode": True
    }
)
def google_search_batch(input_data: dict) -> dict:
    import os, json, asyncio, re
    
    simulated_mode = input_data.get('simulated_mode', False)
    
    if simulated_mode:
        # Return mock result for testing
        queries = input_data.get('queries', [])
        return {
            'results': [
                {'query': q, 'search_results': [
                    {'title': f'Test result for {q}', 'url': 'https://example.com', 'content': 'Test content', 'type': 'text'}
                ]} for q in queries
            ]
        }
    
    from googleapiclient.discovery import build
    from ddgs import DDGS

    async def duckduckgo_search(query, num_results=5):
        dd = DDGS()
        results = []
        with dd:
            hits = list(dd.text(query, max_results=num_results))
            for hit in hits:
                url = hit.get('url') or hit.get('href')
                results.append({
                    'title': hit.get('title') or 'Untitled',
                    'url': url,
                    'content': hit.get('description') or '',
                    'type': 'text'
                })
        return results

    async def google_search(query, num_results=5):
        try:
            api_key = os.getenv('GOOGLE_API_KEY')
            cse_id = os.getenv('GOOGLE_CSE_ID')
            if not api_key or not cse_id: raise Exception('No API key')
            service = build('customsearch', 'v1', developerKey=api_key)
            res = service.cse().list(q=query, cx=cse_id, num=num_results).execute()
            items = res.get('items', [])
            return [{'title': i.get('title','Untitled'),'url': i.get('link'),'content': i.get('snippet',''),'type':'text'} for i in items]
        except:
            return await duckduckgo_search(query, num_results)

    async def batch_search(queries, num_results=5, pdf=False):
        all_texts = []
        per_query = []
        for q in queries:
            results = await google_search(q, num_results)
            combined = ' '.join(re.sub(r'\s+',' ',r.get('content','')).strip() for r in results if r.get('content'))
            if combined: all_texts.append(f'{q}:\n{combined}')
            per_query.append({'query': q, 'search_results': results})
        return json.dumps({'results':'\n\n'.join(all_texts)}) if pdf else json.dumps({'results': per_query})

    queries = input_data.get('queries', [])
    num_results = int(input_data.get('num_results', 5))
    pdf = bool(input_data.get('pdf', False))
    result_str = asyncio.run(batch_search(queries, num_results, pdf))
    return json.loads(result_str)