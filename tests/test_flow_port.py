"""The OTO port of the flow ontology (oto/flow, written by tools/flow_port.py) gives the verdicts
tools/kgctl.py gave: a project on `flow` and `report` holding the pdf-to-template flow as facts
(fixtures/pdf-to-template/graph.json) answers the five briefs as kgctl's `brief` and `readiness`
did, step by step, blocking question by blocking question; every brief question answers with as
many facts as the original SPARQL; and the committed unit is what the port writes.

Needs the OTO engine importable (`OTO_HOME`, or ../oto beside this repository). The comparison
with kgctl itself also needs the flow instance (`FLOW_ROOT`, the pdf-to-template plugin); without
it, the verdicts are checked against the table kgctl printed on 2026-10-07."""
import json
import os
import pathlib
import shutil
import subprocess
import sys
import tempfile

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent
UNIT = ROOT / "oto" / "flow"
GRAPH = ROOT / "fixtures" / "pdf-to-template" / "graph.json"
OTO = pathlib.Path(os.environ.get("OTO_HOME") or ROOT.parent / "oto")
if (OTO / "oto" / "__init__.py").exists() and str(OTO) not in sys.path:
    sys.path.insert(0, str(OTO))
try:
    import oto  # noqa: F401
    HAVE_OTO = True
except ImportError:
    HAVE_OTO = False
pytestmark = pytest.mark.skipif(not HAVE_OTO, reason="OTO engine not importable: set OTO_HOME or pip install oto-kg")
FLOW_ROOT = os.environ.get("FLOW_ROOT") or (str(ROOT.parent / "pdf-to-template") if (ROOT.parent / "pdf-to-template" / "flow" / "flow.json").exists() else None)

#: kgctl readiness on flow.json 1.3.0, 2026-10-07: the verdict the port must give for every implementable step.
KGCTL_READINESS = {
    "B00_intake": ("READY", "READY"), "B01_inspect": ("BLOCKED CQ03", "READY"), "B02_ocr": ("BLOCKED CQ03", "READY"),
    "B04_layout": ("BLOCKED CQ03", "READY"), "B05_decompose": ("READY", "READY"), "B07_sample_data": ("BLOCKED CQ03", "READY"),
    "B08_generate": ("READY", "READY"), "B09_render": ("READY", "READY"), "B10_verify": ("READY", "READY"),
    "B11_repair": ("BLOCKED CQ03", "READY"), "B13_stress_data": ("BLOCKED CQ03", "READY"), "B14_stress_verify": ("BLOCKED CQ03", "READY"),
    "B16_freeze": ("READY", "READY"), "R00_load_batch": ("BLOCKED CQ03", "READY"), "R01_validate_data": ("READY", "READY"),
    "R02_render": ("READY", "READY"), "R03_verify": ("BLOCKED CQ03", "READY"), "R06_publish": ("BLOCKED CQ03", "READY"),
}
#: The original's question ids, by the port's.
CQ = {"FL%d" % i: "CQ%02d" % i for i in range(1, 18)}
#: Questions whose rows the two sides count alike (the port's FL10 lists the concepts of an artifact in one row).
COUNTED = ["FL1", "FL2", "FL3", "FL4", "FL5", "FL6", "FL7", "FL8", "FL9", "FL11"]


@pytest.fixture(scope="module")
def project():
    """A project on flow and report, the fixture graph as its facts, built."""
    from oto.builder import build
    from oto.project import Project
    from oto.scaffold import init
    root = tempfile.mkdtemp()
    os.environ["OTO_ONTOLOGIES"] = str(ROOT / "oto")
    init(root, slug="ptt", name="pdf-to-template", ontology="flow,report", empty=True)
    shutil.copy(GRAPH, os.path.join(root, "graph.json"))
    project = Project.standard(root)
    build(project)
    yield project
    shutil.rmtree(root, ignore_errors=True)


@pytest.fixture(scope="module")
def ported(project):
    from oto.model.vocabulary import covers
    from oto.reason import briefs as B, questions as Q
    config = json.load(open(project.ontology_config_path, encoding="utf-8"))
    graph = json.load(open(os.path.join(project.layout.graph, "knowledge-graph.json"), encoding="utf-8"))
    derived = json.load(open(os.path.join(project.layout.graph, "derived.json"), encoding="utf-8"))
    edges = graph["edges"] + [{"from": e["from"], "rel": e["rel"], "to": e["to"]} for e in derived["derived_edges"]]
    return {"questions": Q.load(project), "briefs": B.load(project), "nodes": graph["nodes"], "edges": edges,
            "covers": covers(config["classes"]), "declared": Q.declared_names(config)}


def _steps(ported):
    return {n["attributes"]["stepId"]: n["id"] for n in ported["nodes"] if "stepId" in (n.get("attributes") or {})}


def _verdict(result):
    return result["status"] if result["status"] == "READY" else "BLOCKED " + ",".join(CQ.get(b["id"], b["id"]) for b in result["blocking"])


def _run_brief(ported, task, params):
    from oto.reason import briefs as B
    return B.run(task, ported["briefs"][task], params, ported["questions"], ported["nodes"], ported["edges"], ported["covers"], declared=ported["declared"])


def test_the_readiness_table_is_kgctls(ported):
    steps = _steps(ported)
    table = {}
    for step_id, nid in steps.items():
        if ported["nodes"][[n["id"] for n in ported["nodes"]].index(nid)]["type"] in ("HumanStep", "TerminalStep"):
            continue
        table[step_id] = tuple(_verdict(_run_brief(ported, task, {"STEP": nid})) for task in ("implement-step", "write-tests"))
    assert table == KGCTL_READINESS


def test_every_brief_question_answers_with_as_many_facts_as_the_original(ported):
    """kgctl's brief for B10_verify, 2026-10-07: the fact counts per question."""
    kgctl = {"CQ01": 1, "CQ02": 7, "CQ03": 16, "CQ04": 6, "CQ05": 6, "CQ06": 3, "CQ08": 1, "CQ11": 3, "CQ07": 3, "CQ09": 3}
    result = _run_brief(ported, "implement-step", {"STEP": _steps(ported)["B10_verify"]})
    assert result["status"] == "READY"
    counted = {CQ[r["id"]]: len(r["rows"]) for r in result["questions"] if r["id"] in COUNTED}
    assert counted == kgctl
    engine = _run_brief(ported, "build-engine", {})
    assert engine["status"] == "READY" and [r["id"] for r in engine["questions"]] == ["FL13", "FL14", "FL15"]
    assert all(r["rows"] for r in engine["questions"])
    tests = _run_brief(ported, "write-tests", {"STEP": _steps(ported)["B10_verify"]})
    exercised = sorted({row["x.type"] for r in tests["questions"] if r["id"] == "FL12" for row in r["rows"]})
    assert exercised == ["Check", "Invariant", "Transition"], "a test of every check, transition and enforced invariant"
    kinds = sorted({row["t.obligationKind"] for r in tests["questions"] if r["id"] == "FL21" for row in r["rows"]})
    assert kinds == ["fail_case", "pass_case", "property", "route"], "the materialised obligations, with ids to cite"


@pytest.mark.skipif(not FLOW_ROOT, reason="the flow instance (FLOW_ROOT) is needed to run kgctl itself")
def test_kgctl_itself_agrees_on_every_step_task_parameter_and_artifact(ported):
    sys.path.insert(0, str(ROOT / "tools"))
    import kgctl
    kgctl.FLOW_ROOT = pathlib.Path(FLOW_ROOT)
    g = kgctl.build()
    steps = _steps(ported)
    for step_id, nid in steps.items():
        kind = next(n["type"] for n in ported["nodes"] if n["id"] == nid)
        if kind in ("HumanStep", "TerminalStep"):
            continue
        for task in ("implement-step", "write-tests"):
            theirs = kgctl.brief(g, task, {"STEP": kgctl.PT + "step/" + step_id})
            mine = _run_brief(ported, task, {"STEP": nid})
            assert _verdict(mine) == (theirs["status"] if theirs["status"] == "READY" else "BLOCKED " + ",".join(x["cq"] for x in theirs["blocking"])), (step_id, task)
            for q in theirs["questions"]:
                fl = next(k for k, v in CQ.items() if v == q["id"])
                if fl in COUNTED:
                    # CQ02 lists an artifact once per direction; the port once (B11_repair reads and writes template_project)
                    expected = len({row["artifact"] for row in q["answer"]}) if q["id"] == "CQ02" else len(q["answer"])
                    assert len(next(r for r in mine["questions"] if r["id"] == fl)["rows"]) == expected, (step_id, task, q["id"])
                if q["id"] == "CQ12":
                    # FL12 lists what a test must exercise (a check once); FL21 the materialised obligations (a check twice)
                    assert len(next(r for r in mine["questions"] if r["id"] == "FL21")["rows"]) == len(q["answer"]), (step_id, task, q["id"])
    # a parameter change reaches the same elements; an artifact change the same steps
    for n in ported["nodes"]:
        if n["type"] == "ConfigParameter":
            theirs = kgctl.ask(g, "CQ16", {"PARAM": kgctl.PT + "param/" + n["attributes"]["paramName"]}, True)
            mine = next(r for r in _run_brief(ported, "impact-parameter", {"PARAM": n["id"]})["questions"])
            # kgctl's CQ16 matches `?element a flow:Step` without subclass inference, so it misses a step whose
            # action uses the parameter (B01_inspect --dpi {config.inspect_dpi}); the port's classes cover their kinds
            steps_using = [e for e in ported["edges"] if e["rel"] == "usesParameter" and e["to"] == n["id"] and e["from"].startswith("step.")]
            assert len(mine["rows"]) == len(theirs["answer"]) + len(steps_using), n["id"]
        if n["type"] == "Artifact":
            theirs = kgctl.ask(g, "CQ17", {"ARTIFACT": kgctl.PT + "artifact/" + n["label"]}, True)
            mine = next(r for r in _run_brief(ported, "impact-artifact", {"ARTIFACT": n["id"]})["questions"])
            # CQ17 lists a step once per role; the port once (a step that reads and writes the blueprint)
            assert len(mine["rows"]) == len({row["step"] for row in theirs["answer"]}), n["id"]


@pytest.mark.skipif(not FLOW_ROOT, reason="the port rebuilds the fixture graph from the flow instance (FLOW_ROOT)")
def test_the_committed_unit_and_graph_are_what_the_port_writes():
    import flow_port
    with tempfile.TemporaryDirectory() as work:
        flow_port.OUT_FLOW = os.path.join(work, "flow")
        flow_port.OUT_GRAPH = os.path.join(work, "graph.json")
        assert flow_port.main(["--flow-root", FLOW_ROOT, "--oto", str(OTO)]) == 0
        for name in sorted(os.listdir(UNIT)):
            if name.endswith(".json"):
                committed = json.load(open(UNIT / name, encoding="utf-8"))
                written = json.load(open(os.path.join(work, "flow", name), encoding="utf-8"))
                if name == "manifest.json":
                    committed["changelog"][0]["at"] = written["changelog"][0]["at"] = "today"
                assert committed == written, name
        assert json.load(open(GRAPH, encoding="utf-8")) == json.load(open(os.path.join(work, "graph.json"), encoding="utf-8"))
