"""
Tavily Search Tool — primary web search for LectureCrewLLM.
Replaces Google Programmable Search as the default search backend.
"""

import os
from typing import Type

from crewai.tools import BaseTool
from pydantic import BaseModel, Field
from tavily import TavilyClient


class TavilySearchSchema(BaseModel):
    query: str = Field(..., description="Search query to send to Tavily API")


class TavilySearchTool(BaseTool):
    name: str = "Tavily Web Search"
    description: str = (
        "Searches the web using the Tavily API and returns top results with title, content, and URL. "
        "Preferred over Google Programmable Search — more reliable and faster."
    )
    args_schema: Type[BaseModel] = TavilySearchSchema

    def _run(self, query: str) -> str:
        api_key = os.getenv("TAVILY_API_KEY")
        if not api_key:
            return "错误：未设置 TAVILY_API_KEY 环境变量"

        try:
            client = TavilyClient(api_key=api_key)
            response = client.search(
                query=query,
                search_depth="advanced",
                max_results=5,
                include_answer=True,
            )
        except Exception as e:
            return f"Tavily 搜索出错：{e}"

        results = response.get("results", [])
        if not results:
            return f"未找到与「{query}」相关的搜索结果"

        lines = [f"「{query}」的搜索结果（Tavily）", ""]

        # Include the AI-generated answer if available
        answer = response.get("answer")
        if answer:
            lines.append(f"📝 摘要：{answer}")
            lines.append("")

        for index, item in enumerate(results, start=1):
            title = item.get("title", "无标题")
            url = item.get("url", "")
            content = item.get("content", "")
            lines.append(f"{index}. {title}")
            if content:
                # Truncate very long content snippets
                snippet = content[:300] + "..." if len(content) > 300 else content
                lines.append(f"   内容：{snippet}")
            if url:
                lines.append(f"   URL: {url}")
            lines.append("")

        return "\n".join(lines).strip()
