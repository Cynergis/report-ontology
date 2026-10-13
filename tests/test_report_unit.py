"""The report ontology OTO projects use (oto/report): maintained here by hand since release 2, when it
moved on from the Turtle's port (ttl-port/report). It composes, its sample answers every question it
must, and it composes with flow, as a report product with a pipeline or a template build does.
Needs the OTO engine importable: OTO_HOME or ../oto beside this repository, or the installed package."""
import json
import os
import pathlib
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent
UNIT = ROOT / "oto" / "report"
OTO = pathlib.Path(os.environ.get("OTO_HOME") or ROOT.parent / "oto")
if (OTO / "oto" / "__init__.py").exists() and str(OTO) not in sys.path:
    sys.path.insert(0, str(OTO))
try:
    import oto  # noqa: F401
    HAVE_OTO = True
except ImportError:
    HAVE_OTO = False
pytestmark = pytest.mark.skipif(not HAVE_OTO, reason="OTO engine not importable: set OTO_HOME or pip install oto-kg")


def test_the_report_ontology_composes_and_its_sample_answers_every_question():
    from oto.model import ontologies
    assert ontologies.self_check("report", roots=[str(UNIT.parent)]) == []


def test_it_is_the_release_projects_use_with_its_whole_history():
    manifest = json.load(open(UNIT / "manifest.json", encoding="utf-8"))
    assert manifest["name"] == "report" and manifest["release"] >= 5
    assert [c["release"] for c in manifest["changelog"]] == list(range(manifest["release"], 0, -1)), "every release recorded, newest first"
    config = json.load(open(UNIT / "ontology.config.json", encoding="utf-8"))
    assert {"QualityCheck", "Finding", "Transformation", "Macro"} <= set(config["classes"]), "the lineage and quality fold of release 5"


def test_it_composes_with_flow():
    from oto.model import ontologies
    _config, _sample, _readme, _rationale, report = ontologies.merge(["flow", "report"], roots=[str(UNIT.parent)])
    assert not report["class_clashes"], report["class_clashes"]
