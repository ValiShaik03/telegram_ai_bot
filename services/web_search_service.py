import requests
from bs4 import BeautifulSoup
from services.gemini_service import GeminiService

class WebSearchService:
    def __init__(self):
        self.gemini = GeminiService()

    async def search(self, query):
        # Using DuckDuckGo for search
        url = f"https://duckduckgo.com/html/?q={query}"
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }
        
        response = requests.get(url, headers=headers)
        soup = BeautifulSoup(response.text, 'html.parser')
        
        results = []
        for result in soup.find_all('div', class_='result')[:5]:
            title = result.find('a', class_='result__a')
            if title:
                link = title['href']
                text = title.text
                results.append(f"{text}\n{link}\n")

        # Generate AI summary
        summary_prompt = f"Summarize these search results for '{query}':\n" + "\n".join(results)
        summary = await self.gemini.get_response(summary_prompt)
        
        return {
            'summary': summary,
            'links': results
        } 