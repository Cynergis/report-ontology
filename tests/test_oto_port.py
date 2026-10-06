"""The OTO port of the report ontology (oto/report, written by tools/oto_port.py) answers what the
original does: every competency question, run by the original SPARQL over the fixture's compiled
graph and by the OTO engine over the same facts as its sample, gives the same number of answers
for every binding; two questions are compared value by value; OTO's own SPARQL rendering of each
question agrees with its engine on this graph; and the committed unit is what the port writes.

Needs the OTO engine importable: `OTO_HOME` or ../oto beside this repository, with rdflib."""
import json
import os
import pathlib
import subprocess
import sys
import tempfile

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent
UNIT = ROOT / "oto" / "report"
OTO = pathlib.Path(os.environ.get("OTO_HOME") or ROOT.parent / "oto")
if (OTO / "oto" / "__init__.py").exists() and str(OTO) not in sys.path:
    sys.path.insert(0, str(OTO))
try:
    import oto  # noqa: F401  (a checkout on OTO_HOME or beside this repository, or the installed package)
    HAVE_OTO = True
except ImportError:
    HAVE_OTO = False
pytestmark = pytest.mark.skipif(not HAVE_OTO, reason="OTO engine not importable: set OTO_HOME or pip install oto-kg")
sys.path.insert(0, str(ROOT / "tools"))

#: Questions whose original SPARQL groups its rows (GROUP_CONCAT) or multiplies them (a multi-valued
#: property in a plain triple pattern): the two sides are compared on the distinct values of one
#: column, (the port's, the original's).
GROUPED = {"CQ2": ("s", "section"), "CQ18": ("f.fieldId", "fid"), "CQ13": ("rel.version", "version")}
#: What a parameter of the original question is bound to: the fixture node's attribute that names it.
BINDINGS = {"REPORT": ("ReportType", "reportId"), "FIELD": ("Field", "fieldId"), "COLUMN": ("Column", "columnName"),
            "COMPONENT": ("Component", "label")}


@pytest.fixture(scope="module")
def ported():
    from oto.model import ontologies
    from oto.model.vocabulary import covers
    from oto.reason import questions as Q
    config = json.load(open(UNIT / "ontology.config.json", encoding="utf-8"))
    composed = ontologies.composed("report", roots=[str(UNIT.parent)])
    sample = composed["sample"]
    return {"config": composed["config"], "own": config, "nodes": sample["nodes"], "edges": sample["edges"],
            "questions": Q.load(type("U", (), {"data": str(UNIT)})()), "covers": covers(composed["config"]["classes"])}


@pytest.fixture(scope="module")
def original():
    import semantic
    fixture = ROOT / "fixtures" / "fund-profile-balanced" / "semantic" / "report.graph.json"
    if not fixture.exists():                       # the compiled graph is never committed
        r = subprocess.run([sys.executable, str(ROOT / "tools" / "semantic.py"), "compile", str(ROOT / "fixtures")],
                           capture_output=True, text=True, cwd=ROOT)
        assert r.returncode == 0, r.stdout + r.stderr
    return semantic.rdf_graph([str(fixture)]), semantic


def _original_rows(original, cq, params):
    graph, semantic = original
    return semantic.run_question(graph, cq, params)["rows"]


def _bindings(ported, name):
    kind, attribute = BINDINGS[name]
    out = []
    for node in ported["nodes"]:
        if node["type"] == kind:
            value = node["label"] if attribute == "label" else node["attributes"].get(attribute)
            if value:
                out.append((node["id"], value))
    return out


def test_the_unit_is_what_the_port_writes_and_checks_clean():
    from oto.model import ontologies
    assert ontologies.self_check("report", roots=[str(UNIT.parent)]) == []
    before = {name: (UNIT / name).read_text(encoding="utf-8") for name in os.listdir(UNIT)}
    r = subprocess.run([sys.executable, str(ROOT / "tools" / "oto_port.py")] + (["--oto", str(OTO)] if (OTO / "oto").exists() else []),
                       capture_output=True, text=True, cwd=ROOT)
    assert r.returncode == 0, r.stdout + r.stderr
    after = {name: (UNIT / name).read_text(encoding="utf-8") for name in os.listdir(UNIT)}
    changed = [name for name in after if name != "manifest.json" and before.get(name) != after[name]]
    assert changed == [], "the committed unit differs from what the port writes: %s" % changed
    (UNIT / "manifest.json").write_text(before["manifest.json"], encoding="utf-8")       # its changelog date is today's
    manifest = json.load(open(UNIT / "manifest.json", encoding="utf-8"))
    assert manifest["namespace"] == "https://cynergis.ai/ont/report#" and "questions" in manifest["carries"]


def test_every_question_gives_the_same_number_of_answers_as_the_original(ported, original):
    from oto.reason import questions as Q
    declared_names = Q.declared_names(ported["config"])
    compared = 0
    for cq, q in ported["questions"].items():
        if not cq.startswith("CQ"):
            continue
        declared = q.get("params") or {}
        def count(rows, side=0):
            column = GROUPED.get(cq)
            return len({json.dumps(r.get(column[side]), default=str) for r in rows}) if column else len(rows)

        if not declared:
            theirs = _original_rows(original, cq, {})
            mine = Q.run(cq, q, {}, ported["nodes"], ported["edges"], ported["covers"], declared=declared_names)["rows"]
            assert count(mine) == count(theirs, 1), "%s: original %d row(s), port %d\n%s" % (cq, count(theirs, 1), count(mine), mine[:3])
            compared += 1
            continue
        name = next(iter(declared))
        for nid, value in _bindings(ported, name):
            theirs = _original_rows(original, cq, {name: value})
            mine = Q.run(cq, q, {name: nid}, ported["nodes"], ported["edges"], ported["covers"], declared=declared_names)["rows"]
            assert count(mine) == count(theirs, 1), "%s on %s: original %d row(s), port %d\noriginal: %s\nport: %s" % (
                cq, value, count(theirs, 1), count(mine), theirs[:3], mine[:3])
            compared += 1
    assert compared >= 21 + 35 * 3


def test_two_questions_agree_value_by_value(ported, original):
    from oto.reason import questions as Q
    theirs = _original_rows(original, "CQ1", {"FIELD": "mer"})
    declared_names = Q.declared_names(ported["config"])
    mine = Q.run("CQ1", ported["questions"]["CQ1"], {"FIELD": "report.fund-profile-balanced.field.mer"},
                 ported["nodes"], ported["edges"], ported["covers"], declared=declared_names)["rows"]
    assert [(r["locale"], r["label"], r["definition"]) for r in theirs] == [(r["m.locale"], r["m.label"], r["m.definition"]) for r in mine]
    theirs = _original_rows(original, "CQ7", {"REPORT": "fund-profile-balanced"})
    mine = Q.run("CQ7", ported["questions"]["CQ7"], {"REPORT": "report.fund-profile-balanced"},
                 ported["nodes"], ported["edges"], ported["covers"], declared=declared_names)["rows"]
    assert sorted((r["source"], r["kind"], r["dataset"], r["table"], r["param"], r["column"]) for r in theirs) == \
        sorted((r["s.label"], r["s.sourceKind"], r["t.dataset"], r["t.tableName"], r["p.label"], r["c.columnName"]) for r in mine)


def test_the_sparql_rendering_agrees_with_the_engine_on_this_graph(ported):
    """OTO renders each question as SPARQL over the graph.ttl a build writes; on the report
    graph it must return the engine's rows (list-valued attributes, RDF collections in the export,
    are compared by presence)."""
    import datetime
    import decimal
    from rdflib import Graph, URIRef, Literal
    from oto.builder import build
    from oto.compile import sparql as _sparql
    from oto.model.namespaces import Terms
    from oto.project import Project
    from oto.reason import questions as Q
    from oto.scaffold import init
    with tempfile.TemporaryDirectory() as root:
        init(root, slug="cat", name="Catalogue", ontology=str(UNIT))
        project = Project.standard(root)
        build(project)
        config = json.load(open(project.ontology_config_path, encoding="utf-8"))
        graph = json.load(open(os.path.join(project.layout.graph, "knowledge-graph.json"), encoding="utf-8"))
        terms = Terms(config, project.identity())
        data = Graph().parse(os.path.join(project.layout.graph, "graph.ttl"), format="turtle")
        lists = {"%s.%s" % (k, a) for k, attrs in (config.get("attributes") or {}).items() for a, s in attrs.items() if s.get("type") == "list"}

        def value(term):
            if term is None:
                return None
            if isinstance(term, URIRef):
                text = str(term)
                return text[len(terms.instances):] if text.startswith(terms.instances) else text.rsplit("#", 1)[-1].rsplit("/", 1)[-1]
            if isinstance(term, Literal):
                v = term.toPython()
                if isinstance(v, decimal.Decimal):
                    v = float(v)
                if isinstance(v, datetime.date):
                    v = v.isoformat()
                return v
            return "<list>"

        def normalise(row, types):
            out = {}
            for key, v in row.items():
                var, _dot, field = key.lstrip("$").partition(".")
                kinds = types.get(var, [])
                if field and any("%s.%s" % (k, field) in lists for k in kinds):
                    v = bool(v)
                if isinstance(v, float):
                    v = round(v, 6)
                out[key] = v
            return out

        compared = 0
        for cq, q in ported["questions"].items():
            if not cq.startswith("CQ"):
                continue
            renderer = _sparql.Renderer(config, terms)
            query = renderer.render(q)
            types = {}
            renderer._collect_types(q["ask"]["when"], types)
            for name, spec in (q.get("params") or {}).items():
                types[name] = [spec["type"]]
            select = q["ask"]["select"]
            runs = [({}, query)]
            if q.get("params"):
                name = next(iter(q["params"]))
                runs = [({name: nid}, query.replace("$" + name, "<%s>" % terms.instance(nid))) for nid, _v in _bindings(ported, name)]
            for params, bound in runs:
                engine = [normalise(r, types) for r in Q.run(cq, q, params, graph["nodes"], graph["edges"], ported["covers"],
                                                               declared=Q.declared_names(config))["rows"]]
                sparql_rows = [normalise({k: value(v) for k, v in zip(select, row)}, types) for row in data.query(bound)]
                key = lambda r: json.dumps(r, sort_keys=True, default=str)  # noqa: E731
                assert sorted(map(key, engine)) == sorted(map(key, sparql_rows)), "%s %s\nengine: %s\nsparql: %s\n%s" % (
                    cq, params, engine[:3], sparql_rows[:3], bound)
                compared += 1
        assert compared > 100
