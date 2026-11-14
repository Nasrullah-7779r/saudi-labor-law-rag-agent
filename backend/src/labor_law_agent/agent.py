"""Labor-law agent: LangChain v1 ``create_agent`` with retrieval and end-of-service tools.

Docs relied on (langchain 1.5 / langchain-core 1.8 / langgraph 1.2):
- ``create_agent(model, tools, system_prompt=...)``: https://docs.langchain.com/oss/python/langchain/agents
- ``@tool(args_schema=...)``: https://docs.langchain.com/oss/python/langchain/tools#advanced-schema-definition
- ``@tool(response_format="content_and_artifact")``: the tool returns ``(content, artifact)``; the
  artifact rides on the ``ToolMessage`` and is not sent to the model.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any

from langchain.agents import create_agent
from langchain_core.language_models import BaseChatModel
from langchain_core.tools import BaseTool, tool
from langgraph.graph.state import CompiledStateGraph

from labor_law_agent.calculator import (
    EndOfServiceRequest,
    ServiceCalendar,
    TerminationReason,
    calculate_end_of_service,
)
from labor_law_agent.retrieval import LawRetriever, RetrievedArticle

SEARCH_TOOL_NAME = "search_labor_law"
CALCULATOR_TOOL_NAME = "calc_end_of_service"
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
- For an end-of-service award, use calc_end_of_service rather than doing arithmetic yourself. \
Before calling it, ask for any missing last monthly wage in SAR, employment start date, \
end date, or reason the employment ended. Never invent or infer these inputs. Ask for \
Gregorian ISO dates (YYYY-MM-DD), converting other dates only after clarification.
- Explain that service periods default to Hijri under Article 10; use Gregorian only if the \
user says their contract or work regulations specify it. Clarify ambiguous termination reasons. \
Apply Article 80, 81 or 87 only when the user confirms the relevant circumstances and the \
retrieved text supports that classification; otherwise ask. Search for the applicable articles.
- Report the calculator's amount in SAR, calendar, service years, each wage-band amount, \
full award, resignation fraction and applied articles. Its breakdown is the full Article 84 \
award before the entitlement fraction; explain that adjustment separately. If a tool reports \
invalid or missing inputs, ask the user to correct them; do not produce a guessed award.
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


@tool(CALCULATOR_TOOL_NAME, args_schema=EndOfServiceRequest)
def calc_end_of_service(
    last_monthly_wage: Decimal,
    start_date: date,
    end_date: date,
    reason: TerminationReason,
    calendar: ServiceCalendar = ServiceCalendar.HIJRI,
) -> str:
    """Calculate a Saudi end-of-service award from confirmed user inputs.

    Wage is the last monthly wage in SAR. Dates are Gregorian ISO dates (YYYY-MM-DD).
    Service uses Hijri by default (Article 10); choose Gregorian only when the contract
    or work regulations specify it. Ask for missing wage, dates or termination reason
    before calling. Do not assume an Article 80/81/87 legal exception applies.
    Returns amount, full-award wage bands, entitlement fraction and applied articles.
    """
    request = EndOfServiceRequest(
        last_monthly_wage=last_monthly_wage,
        start_date=start_date,
        end_date=end_date,
        reason=reason,
        calendar=calendar,
    )
    return calculate_end_of_service(request).model_dump_json()


def build_agent(model: BaseChatModel, retriever: LawRetriever) -> CompiledStateGraph[Any]:
    return create_agent(
        model,
        tools=[make_search_tool(retriever), calc_end_of_service],
        system_prompt=SYSTEM_PROMPT,
    )
