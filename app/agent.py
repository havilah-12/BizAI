"""LangChain tools and agent runner for BizAI."""

from __future__ import annotations

import os
import smtplib
from email.message import EmailMessage
from typing import Any

from duckduckgo_search import DDGS
from langchain.agents import create_agent
from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.tools import tool
from langchain_openai import ChatOpenAI

from app.knowledge import knowledge_stats, search_knowledge
from app.prompts import BUSINESS_SYSTEM_PROMPT
from app.tools import run_tool

DEFAULT_MODEL = "gpt-4o-mini"
KNOWLEDGE_HINT_TERMS = {
    "doc",
    "docs",
    "document",
    "documents",
    "file",
    "files",
    "upload",
    "uploaded",
    "policy",
    "policies",
    "kb",
    "knowledge",
    "pdf",
    "txt",
    "md",
    "summarize",
    "summary",
}


def _ensure_openai_key() -> None:
    if not os.environ.get("OPENAI_API_KEY"):
        raise RuntimeError("OPENAI_API_KEY is not set. Add it to .env")


def _extract_text(messages: list[Any]) -> str:
    for msg in reversed(messages):
        if isinstance(msg, AIMessage):
            content = msg.content
            if isinstance(content, str):
                return content
            if isinstance(content, list):
                out: list[str] = []
                for part in content:
                    if isinstance(part, str):
                        out.append(part)
                    elif isinstance(part, dict) and part.get("type") == "text":
                        out.append(str(part.get("text", "")))
                text = "".join(out).strip()
                if text:
                    return text
    return ""


def _should_use_knowledge(query: str) -> bool:
    lowered = query.strip().lower()
    if not lowered:
        return False
    words = set(lowered.replace("?", " ").replace(".", " ").split())
    if len(words) <= 2 and words.issubset({"hi", "hello", "hey", "yo", "hola"}):
        return False
    return bool(words.intersection(KNOWLEDGE_HINT_TERMS))


def _is_simple_greeting(query: str) -> bool:
    lowered = query.strip().lower()
    return lowered in {"hi", "hello", "hey", "yo", "hola", "hello!", "hi!"}


def _send_email(
    to: str,
    subject: str,
    body: str,
    attachments: list[dict[str, bytes | str]] | None = None,
) -> str:
    host = os.environ.get("SMTP_HOST")
    port = int(os.environ.get("SMTP_PORT", "587"))
    user = os.environ.get("SMTP_USER")
    password = os.environ.get("SMTP_PASS")
    sender = os.environ.get("SMTP_FROM", user or "")

    if not host or not sender:
        return "SMTP is not configured. Set SMTP_HOST/SMTP_PORT/SMTP_USER/SMTP_PASS/SMTP_FROM."

    msg = EmailMessage()
    msg["From"] = sender
    msg["To"] = to
    msg["Subject"] = subject
    msg.set_content(body)

    for attachment in attachments or []:
      filename = str(attachment.get("filename", "attachment"))
      content = attachment.get("content", b"")
      content_type = str(attachment.get("content_type", "application/octet-stream"))
      if isinstance(content, str):
          content = content.encode("utf-8")
      maintype, _, subtype = content_type.partition("/")
      msg.add_attachment(
          content,
          maintype=maintype or "application",
          subtype=subtype or "octet-stream",
          filename=filename,
      )

    with smtplib.SMTP(host, port, timeout=20) as smtp:
        smtp.starttls()
        if user and password:
            smtp.login(user, password)
        smtp.send_message(msg)

    return f"Email sent to {to}."


def _web_search(query: str) -> str:
    with DDGS() as ddgs:
        results = list(ddgs.text(query, max_results=5))
    if not results:
        return "No web results found."
    lines: list[str] = []
    for i, item in enumerate(results, 1):
        lines.append(
            f"[{i}] {item.get('title', 'Untitled')}\nURL: {item.get('href', '')}\nSnippet: {item.get('body', '')}"
        )
    return "\n\n".join(lines)


def _tools_for_user(user_email: str, enable_web_search: bool):
    @tool
    def calculate(expression: str) -> str:
        """Evaluate a numeric expression for business math."""
        return run_tool("calculate", {"expression": expression})

    @tool
    def business_framework(framework: str) -> str:
        """Get a short outline for SWOT/OKR/RACI/lean canvas/meeting agenda."""
        return run_tool("business_framework", {"framework": framework})

    @tool
    def company_knowledge_search(query: str) -> str:
        """Search uploaded company documents and policies for internal answers."""
        return search_knowledge(user_email, query=query, k=4)

    @tool
    def send_email(to: str, subject: str, body: str) -> str:
        """Send an email using configured SMTP credentials."""
        try:
            return _send_email(to, subject, body)
        except Exception as e:
            return f"Email send failed: {e!s}"

    tools = [calculate, business_framework, company_knowledge_search, send_email]

    if enable_web_search:
        @tool
        def web_search(query: str) -> str:
            """Search the web for current information. Return sources with URLs."""
            try:
                return _web_search(query)
            except Exception as e:
                return f"Web search failed: {e!s}"

        tools.append(web_search)

    return tools


def run_business_agent(
    user_message: str,
    history: list[dict[str, str]],
    user_email: str,
    enable_web_search: bool,
) -> str:
    if _is_simple_greeting(user_message):
        return (
            "Hi - ready to help. Pick one or type your request:\n"
            "1. Strategy: roadmap, pricing, GTM\n"
            "2. Finance: runway, burn, unit economics\n"
            "3. Hiring: JD, scorecard, interview plan\n"
            "4. Ops: SOP, RACI, process improvement\n"
            "5. Marketing & Sales: positioning, channels, KPIs\n"
            "6. Comms: draft email, board update, investor note\n"
            "7. Policy lookup: search company docs\n"
            "Or tell me the outcome you want and the deadline."
        )

    _ensure_openai_key()
    model = os.environ.get("OPENAI_MODEL", DEFAULT_MODEL).strip() or DEFAULT_MODEL
    llm = ChatOpenAI(model=model, temperature=0.1)

    tools = _tools_for_user(user_email=user_email, enable_web_search=enable_web_search)
    agent = create_agent(
        llm,
        tools=tools,
        system_prompt=BUSINESS_SYSTEM_PROMPT
        + "\nUse company_knowledge_search for internal policy questions before answering.",
    )

    messages: list[Any] = []
    for turn in history:
        role = turn.get("role")
        text = turn.get("content", "")
        if role == "user":
            messages.append(HumanMessage(content=text))
        elif role == "assistant":
            messages.append(AIMessage(content=text))

    enriched_message = user_message
    try:
        stats = knowledge_stats(user_email)
        if stats.get("documents", 0) > 0 and _should_use_knowledge(user_message):
            context = search_knowledge(user_email, query=user_message, k=4)
            if not context.startswith("No company documents found") and not context.startswith("No relevant internal policy found"):
                enriched_message = (
                    "User question:\n"
                    f"{user_message}\n\n"
                    "Relevant uploaded company knowledge:\n"
                    f"{context}\n\n"
                    "Answer using the uploaded knowledge first when it is relevant. "
                    "Mention the source filename when helpful."
                )
    except Exception:
        enriched_message = user_message

    messages.append(HumanMessage(content=enriched_message))
    result = agent.invoke({"messages": messages})
    return _extract_text(result.get("messages", []))
