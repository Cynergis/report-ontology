"""MCP server for the report ontology: the operations of kg.py as tools, over stdio.

  REPORTS_ROOT=/path/to/reports [FLOW_ROOT=/path/to/flow] python tools/mcp_server.py

REPORTS_ROOT is the catalogue: a folder of report folders (<report>/semantic/report.yaml). When it is not set,
the reports/ folder of the project is used: $CLAUDE_PROJECT_DIR/reports when a Claude client started the server,
otherwise ./reports. FLOW_ROOT is only
needed for flow questions. Every tool is read-only: it never writes to a report folder or to the ontology.
"""
import functools, os, pathlib
from typing import Any

from mcp.server.mcpserver import MCPServer

import kg

if not os.environ.get("REPORTS_ROOT") and os.environ.get("CLAUDE_PROJECT_DIR"):
    os.environ["REPORTS_ROOT"] = str(pathlib.Path(os.environ["CLAUDE_PROJECT_DIR"]) / "reports")

server = MCPServer("report-ontology", instructions=(
    "Read-only access to the report ontology and the report catalogue. Start with list_questions to see what can be "
    "asked, then ask. explain gives the meaning of any class or edge. To define a new report, requirements lists what "
    "it must provide and who provides each part, and gaps says what a draft still lacks and where each answer is written. "
    "An answer with status 'gap' is real but incomplete: report the gaps, do not fill them by guessing. "
    "For a question no competency question covers, walk the graph: overview for the map, resolve to turn the reader's words "
    "into entities, entity and neighbors to read them, search for text inside meanings, purposes and rules. history says "
    "what a definition said before and who changed it; stale lists what is out of date. A definition is current only as "
    "far as it is accepted: say so when history or entity reports pending changes."))


def tool(fn):
    """Register a kg operation. A request it cannot serve comes back as {"error": …}, so the caller reads what to change."""
    @functools.wraps(fn)
    def wrapped(*args, **kwargs):
        try:
            return fn(*args, **kwargs)
        except kg.KgError as e:
            return {"error": str(e)}
    return server.tool()(wrapped)


@tool
def list_questions(vocabulary: str | None = None) -> dict[str, Any]:
    """The competency questions the graph can answer, with who asks each one and the parameters it needs.
    vocabulary: 'report' (report types, fields, data mapping, schedule, policies), 'flow' (the steps that build and
    run reports), or omit for both."""
    return kg.questions(vocabulary)


@tool
def ask(question: str, report: str | None = None, field: str | None = None, column: str | None = None,
        component: str | None = None, step: str | None = None, param: str | None = None, artifact: str | None = None) -> dict[str, Any]:
    """Run one competency question by id (CQ14, or flow:CQ04 for a flow question) and return its rows and gaps.
    Pass only the parameters list_questions names for that question. status is answered, gap or empty."""
    return kg.ask(question, {"report": report, "field": field, "column": column, "component": component,
                             "step": step, "param": param, "artifact": artifact})


@tool
def explain(term: str | None = None) -> dict[str, Any]:
    """The meaning of a class or an edge of the ontology: label, definition, domain and range, the questions that read
    it and the file it is written in. term is a name or label ('sourcedFrom', 'rpt:Field', 'reads table').
    Omit term for the index of every class."""
    return kg.explain(term)


@tool
def requirements(provided_by: str | None = None) -> dict[str, Any]:
    """Everything a new report's files must hold: where each item is written, whether it is required, what it means,
    and who provides it. provided_by filters to 'analyst' (ask the analyst), 'agent' (draft it from the sample PDF or
    the table, then confirm with the analyst) or 'flow' (recorded by a flow step; never asked)."""
    return kg.requirements(provided_by)


@tool
def gaps(report: str) -> dict[str, Any]:
    """What a draft report still lacks. report is a folder name in the catalogue or a path to a report folder.
    blocking items stop the report from compiling or answering a question; warnings are gaps a production release
    cannot keep. Each item says where the missing answer is written."""
    return kg.gaps(report)


@tool
def resolve(term: str, report: str | None = None) -> dict[str, Any]:
    """Turn a name in the reader's words (an id, a label in any locale, an alias such as 'management expense ratio',
    a column or table name) into the entities of the catalogue it designates, best first, and the ontology terms of
    that name. Use it first when a question names something colloquially. report narrows to one report type."""
    return kg.resolve(term, report)


@tool
def entity(term: str, report: str | None = None) -> dict[str, Any]:
    """One entity of the catalogue (a report, field, section, column, table, component…): its values, its edges in
    both directions with what is at the other end, and for a report or a field its accepted history and pending
    changes. Other entities of the same name are listed under other_matches; pass report to pick one."""
    return kg.entity(term, report)


@tool
def neighbors(term: str, property: str | None = None, direction: str = "both", depth: int = 1, report: str | None = None) -> dict[str, Any]:
    """The entities around one, up to depth edges away (1 to 3), in direction out, in or both, optionally along one
    property only (e.g. sourcedFrom, renderedBy, hasField). Returns the nodes and the edges between them."""
    return kg.neighbors(term, property, direction, depth, report)


@tool
def search(text: str, type: str | None = None, report: str | None = None, limit: int = 10) -> dict[str, Any]:
    """Full-text search of the catalogue: entities whose labels, meanings (every locale), purposes, rules, notes or
    revision reasons hold every word of text, ranked, with a snippet; plus the ontology terms whose definition matches.
    type narrows to one class (Field, Section, Rule…)."""
    return kg.search(text, type, report, limit)


@tool
def overview(limit: int = 10) -> dict[str, Any]:
    """The map of the whole catalogue, for a question that starts from no entity: reports by lifecycle status, nodes
    by class, edges by property, how far the field mapping has got, the most shared fields and components, recent
    accepted revisions, definitions not accepted yet, and how much of the ontology records why and was confirmed."""
    return kg.overview(limit)


@tool
def stale(days: int = 30) -> dict[str, Any]:
    """What is out of date: definitions changed but not accepted, reports with no accepted history, mappings proposed
    and not verified for more than days, reports idle in a status other than production for more than days, and
    reports left out of the catalogue because they no longer validate."""
    return kg.stale(days)


@tool
def history(report: str, as_of: str | None = None, known_on: str | None = None, fact: str | None = None) -> dict[str, Any]:
    """The accepted history of a report's definition: each revision with who accepted it, when, from which date it
    applies, why, and the facts it added, changed or removed (value before and after), plus what is pending. With
    as_of (YYYY-MM-DD, the date revisions apply from) or known_on (the date they were recorded by): the definition as
    it stood then. fact keeps the facts whose name contains it, e.g. 'fields.mer.'."""
    return kg.history(report, as_of, known_on, fact)


if __name__ == "__main__":
    server.run("stdio")
