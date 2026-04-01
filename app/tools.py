"""Tool handlers for business math and framework outlines (used by LangChain tools)."""

from __future__ import annotations

import ast
import operator
from typing import Any

_BINOPS: dict[type[ast.operator], Any] = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.Pow: operator.pow,
    ast.Mod: operator.mod,
}


def _eval_ast(node: ast.AST) -> float:
    if isinstance(node, ast.Constant):
        if isinstance(node.value, (int, float)):
            return float(node.value)
        raise ValueError("only numeric constants allowed")
    if isinstance(node, ast.BinOp):
        op = type(node.op)
        if op not in _BINOPS:
            raise ValueError("operator not allowed")
        return float(_BINOPS[op](_eval_ast(node.left), _eval_ast(node.right)))
    if isinstance(node, ast.UnaryOp):
        if isinstance(node.op, ast.USub):
            return -_eval_ast(node.operand)
        if isinstance(node.op, ast.UAdd):
            return _eval_ast(node.operand)
        raise ValueError("unary op not allowed")
    raise ValueError("expression not allowed")


def _safe_calculate(expression: str) -> str:
    expr = expression.strip().replace(",", "")
    if not expr:
        return "Error: empty expression"
    tree = ast.parse(expr, mode="eval")
    result = _eval_ast(tree.body)
    if abs(result - round(result)) < 1e-9:
        return str(int(round(result)))
    return f"{result:.6g}"


_FRAMEWORKS: dict[str, str] = {
    "SWOT": """### SWOT
- **Strengths:** (internal positives)
- **Weaknesses:** (internal gaps)
- **Opportunities:** (external upside)
- **Threats:** (external risks)
- **So what:** 2–3 implications and one priority action.""",
    "OKR": """### OKR sketch
- **Objective:** (qualitative, inspiring, time-bound)
- **Key results:** (3 metrics, measurable; baseline → target)
- **Initiatives:** (what you'll ship this quarter)
- **Risks / dependencies:** (what could block success)""",
    "RACI": """### RACI
| Task / deliverable | R (Responsible) | A (Accountable) | C (Consulted) | I (Informed) |
| --- | --- | --- | --- | --- |
| (row 1) | | | | |
- **Notes:** single Accountable per major item; avoid too many C's.""",
    "porter_five_forces": """### Porter's Five Forces
1. **Rivalry** among existing competitors
2. **Threat of new entrants**
3. **Bargaining power of suppliers**
4. **Bargaining power of buyers**
5. **Threat of substitutes**
- **Implication:** where is profit most at risk / most defensible?""",
    "lean_canvas": """### Lean Canvas (one page)
- **Problem** | **Solution** | **Unique value prop**
- **Unfair advantage** | **Customer segments** | **Channels**
- **Cost structure** | **Revenue streams** | **Key metrics**
- **Bottom line:** riskiest assumptions to test first.""",
    "elevator_pitch": """### Elevator pitch structure (~30s)
- **For** [customer segment]
- **who** [key problem],
- **our** [product] **is a** [category]
- **that** [key benefit].
- **Unlike** [alternatives], **we** [differentiator].""",
    "meeting_agenda": """### Meeting agenda template
1. **Purpose & outcomes** (what “done” looks like)
2. **Decisions needed** (list)
3. **Discussion** (timeboxed topics)
4. **Actions** (owner + due date)
5. **Next check-in**""",
}


def _business_framework(framework: str) -> str:
    key = framework.strip()
    if key in _FRAMEWORKS:
        return _FRAMEWORKS[key]
    upper = key.upper()
    if upper in _FRAMEWORKS:
        return _FRAMEWORKS[upper]
    norm = key.lower().replace(" ", "_").replace("-", "_")
    for k, v in _FRAMEWORKS.items():
        if k.lower() == norm:
            return v
    return _FRAMEWORKS["SWOT"]


def run_tool(name: str, arguments: dict[str, Any]) -> str:
    if name == "calculate":
        expr = str(arguments.get("expression", ""))
        try:
            return _safe_calculate(expr)
        except Exception as e:
            return f"Error: could not evaluate ({e!s}). Use digits and + - * / ( ) only."
    if name == "business_framework":
        fw = str(arguments.get("framework", "SWOT"))
        return _business_framework(fw)
    return f"Error: unknown tool {name}"
