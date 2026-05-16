from duckduckgo_search import DDGS


class SearchTools:
    def web_search(self, query: str, max_results: int = 8) -> str:
        """Search the web via DuckDuckGo and return formatted results."""
        try:
            results = []
            with DDGS() as ddgs:
                for r in ddgs.text(query, max_results=max_results):
                    results.append(f"**{r['title']}**\n{r['href']}\n{r['body']}\n")
            return "\n---\n".join(results) if results else "No results found."
        except Exception as e:
            return f"Search error: {e}"

    def news_search(self, query: str, max_results: int = 6) -> str:
        """Search recent news via DuckDuckGo."""
        try:
            results = []
            with DDGS() as ddgs:
                for r in ddgs.news(query, max_results=max_results):
                    results.append(f"**{r['title']}** ({r.get('date','')})\n{r['url']}\n{r['body']}\n")
            return "\n---\n".join(results) if results else "No news found."
        except Exception as e:
            return f"News search error: {e}"
