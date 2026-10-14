"""The report product type OTO projects use (oto/product-report): on `product` (the engine's) and
`report` (oto/report). It composes, its sample answers every question it must, it declares its
product type, and it composes with `report` and `flow` as a report product does.
Needs the OTO engine importable: OTO_HOME or ../oto beside this repository, or the installed package."""
import json
import os
import pathlib
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent
UNIT = ROOT / "oto" / "product-report"
OTO = pathlib.Path(os.environ.get("OTO_HOME") or ROOT.parent / "oto")
if (OTO / "oto" / "__init__.py").exists() and str(OTO) not in sys.path:
    sys.path.insert(0, str(OTO))
try:
    import oto  # noqa: F401
    HAVE_OTO = True
except ImportError:
    HAVE_OTO = False
pytestmark = pytest.mark.skipif(not HAVE_OTO, reason="OTO engine not importable: set OTO_HOME or pip install oto-kg")


def test_it_composes_and_its_sample_answers_every_question():
    from oto.model import ontologies
    assert ontologies.self_check("product-report", roots=[str(UNIT.parent)]) == []


def test_it_is_a_product_type_on_product_and_report_with_its_whole_history():
    manifest = json.load(open(UNIT / "manifest.json", encoding="utf-8"))
    assert manifest["name"] == "product-report" and manifest["product_type"] == "report"
    assert manifest["extends"] == ["product", "report"]
    assert [c["release"] for c in manifest["changelog"]] == list(range(manifest["release"], 0, -1)), "every release recorded, newest first"
    questions = json.load(open(UNIT / "questions.json", encoding="utf-8"))
    assert {"RP%d" % i for i in range(1, 11)} <= set(questions.get("questions", questions))


def test_it_composes_with_report_and_flow():
    from oto.model import ontologies
    _config, _sample, _readme, _rationale, report = ontologies.merge(["product-report", "flow"], roots=[str(UNIT.parent)])
    assert not report["class_clashes"], report["class_clashes"]
    # `product` refines oto-core's Document, which flow keeps as is: the merge keeps the refined one
    # and records it as a refinement (engine 0.11.15), not a clash
    assert ("Document", "product-report", "flow") in report["class_refinements"]
