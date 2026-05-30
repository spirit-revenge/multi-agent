import json
import os
from typing import Type
from urllib.parse import urlencode
from urllib.request import urlopen, Request
from urllib.error import HTTPError, URLError

from crewai.tools import BaseTool
from pydantic import BaseModel, Field


class GoogleSearchSchema(BaseModel):
    query: str = Field(..., description="Search query to send to Google Programmable Search Engine")


class GoogleProgrammableSearchTool(BaseTool):
    name: str = "Google Programmable Search"
    description: str = (
        "Searches the web using Google Programmable Search Engine and returns top results with title, snippet, and URL."
    )
    args_schema: Type[BaseModel] = GoogleSearchSchema

    def _run(self, query: str) -> str:
        api_key = os.getenv("GOOGLE_API_KEY")
        cse_id = os.getenv("GOOGLE_CSE_ID")

        if not api_key:
            return "错误：未设置 GOOGLE_API_KEY 环境变量"
        if not cse_id:
            return "错误：未设置 GOOGLE_CSE_ID 环境变量"

        params = {
            "q": query,
            "key": api_key,
            "cx": cse_id,
            "num": 5,
        }
        url = f"https://www.googleapis.com/customsearch/v1?{urlencode(params)}"

        try:
            request = Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urlopen(request, timeout=20) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except HTTPError as error:
            return f"Google 搜索 HTTP 错误：{error.code} {error.reason}"
        except URLError as error:
            return f"Google 搜索网络错误：{error.reason}"
        except Exception as error:
            return f"Google 搜索错误：{error}"

        items = payload.get("items", [])
        if not items:
            return f"未找到与「{query}」相关的搜索结果"

        results = [f"「{query}」的搜索结果", ""]
        for index, item in enumerate(items, start=1):
            title = item.get("title", "No title")
            link = item.get("link", "")
            snippet = item.get("snippet", "")
            results.append(f"{index}. {title}")
            if snippet:
                results.append(f"   Snippet: {snippet}")
            if link:
                results.append(f"   URL: {link}")
            results.append("")

        return "\n".join(results).strip()