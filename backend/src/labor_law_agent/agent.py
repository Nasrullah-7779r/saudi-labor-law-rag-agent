"""Labor-law agent: LangChain v1 ``create_agent`` with a ``search_labor_law`` tool.

Docs relied on (langchain 1.5 / langgraph 1.2):
- ``create_agent(model, tools, system_prompt=...)``: https://docs.langchain.com/oss/python/langchain/agents
- ``@tool(response_format="content_and_artifact")``: the tool returns ``(content, artifact)``; the
  artifact rides on the ``ToolMessage`` and is not sent to the model.
"""

from __future__ import annotations

from typing import Any

from langchain.agents import create_agent
from langchain_core.language_models import BaseChatModel
from langchain_core.tools import BaseTool, tool
from langgraph.graph.state import CompiledStateGraph

from labor_law_agent.retrieval import LawRetriever, RetrievedArticle

SEARCH_TOOL_NAME = "search_labor_law"
SEARCH_RESULTS_K = 5

SYSTEM_PROMPT = """\
You are an assistant for the Saudi Labor Law (Royal Decree M/51, 1426H, as amended). \
You answer only from the official Arabic text retrieved with the search_labor_law tool.

Rules:
- Always call search_labor_law before answering a labor-law question. You may search more than \
once with different wording; the law text is Arabic, so Arabic search terms work best.
- Reply in the language of the user's latest message (Arabic or English). When replying in \
English, translate or paraphrase the Arabic text; do not invent wording.
- Cite every article you rely on as "Article <number>" (English) or "المادة <number>" (Arabic), \
with the number in digits.
- If the retrieved articles do not answer the question, say plainly that the law text you \
found does not cover it. Never answer from general knowledge or other countries' laws.
- Politely refuse questions unrelated to Saudi labor law.
- You are not a lawyer and this is not legal advice; the Arabic text governs (Article 9).
"""


def _format_articles(articles: list[RetrievedArticle]) -> str:
    if not articles:
        return "No matching articles found."
    return "\n\n".join(f"المادة {a.article_no}:\n{a.text_ar}" for a in articles)


def make_search_tool(retriever: LawRetriever) -> BaseTool:
    """The ``search_labor_law`` tool over ``retriever``; its artifact is the hit list."""

    @tool(SEARCH_TOOL_NAME, response_format="content_and_artifact")
    def search_labor_law(query: str) -> tuple[str, list[RetrievedArticle]]:
        """Search the Saudi Labor Law (Arabic official text) for articles relevant to a query.

        Args:
            query: What to look for, preferably in Arabic.
        """
        articles = retriever.search(query, k=SEARCH_RESULTS_K)
        return _format_articles(articles), articles

    return search_labor_law


def build_agent(model: BaseChatModel, retriever: LawRetriever) -> CompiledStateGraph[Any]:
    return create_agent(model, tools=[make_search_tool(retriever)], system_prompt=SYSTEM_PROMPT)
