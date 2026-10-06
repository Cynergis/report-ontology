"""The package's own checks, run the way a consumer runs them: through the two command-line tools.

Report ontology checks run against the two reports in fixtures/ (fund-profile-equity is synthetic: it exists so
questions across report types return more than one row). Flow checks need a flow instance and are skipped unless
FLOW_ROOT points at one (the folder holding flow/flow.json).
"""
import os, pathlib, subprocess, sys
import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent
CATALOGUE = ROOT / "fixtures"
EXAMPLE = CATALOGUE / "fund-profile-balanced" / "semantic"
needs_flow = pytest.mark.skipif(not os.environ.get("FLOW_ROOT"), reason="FLOW_ROOT not set: no flow instance to check")


def run(tool, *args):
    r = subprocess.run([sys.executable, str(ROOT / "tools" / tool), *map(str, args)], capture_output=True, text=True, cwd=ROOT)
    return r.returncode, r.stdout + r.stderr


@pytest.fixture(scope="session", autouse=True)
def compiled_example():
    """conform, ask and the orphan check of `kgctl terms` all read the compiled graph, which is never committed."""
    code, out = run("semantic.py", "compile", CATALOGUE)
    assert code == 0, out


def test_ontologies_and_shapes_parse():
    from rdflib import Graph
    for ttl in sorted((ROOT / "ontology").glob("*.ttl")):
        Graph().parse(ttl)


def test_examples_validate_against_schemas():
    code, out = run("semantic.py", "validate", CATALOGUE)
    assert code == 0, out


def test_examples_conform_to_report_shapes():
    code, out = run("semantic.py", "conform", CATALOGUE)
    assert "Violations: 0" in out and code == 0, out


def test_schemas_ontology_and_questions_agree():
    code, out = run("kgctl.py", "terms")
    assert code == 0, out


def test_the_ontology_lock_is_current_and_every_version_says_what_changed():
    code, out = run("kgctl.py", "ontology", "check", "--strict")
    assert code == 0 and "the lock is current" in out, out


def test_example_definitions_are_accepted():
    code, out = run("semantic.py", "diff", CATALOGUE)
    assert code == 0 and out.count("0 pending since revision") == 2, out


# CQ5 reports a gap on purpose: most fields of the example are not mapped to a column yet, and the question must say so.
# CQ15 is empty on purpose: a report on its own shares fields with no other report.
EXPECTED = {"CQ5": "gap", "CQ15": "empty"}


@pytest.mark.parametrize("cq,status", [(f"CQ{n}", EXPECTED.get(f"CQ{n}", "answered")) for n in range(1, 22)])
def test_report_question_on_one_report(cq, status):
    _, out = run("semantic.py", "ask", EXAMPLE, cq, "--field", "mer", "--column", "mer", "--component", "bar_chart")
    assert f"→ {status}," in out.splitlines()[0], out


@pytest.mark.parametrize("cq,args,rows", [
    ("CQ14", [], 2),                                            # the catalogue lists both report types
    ("CQ15", ["--report", "fund-profile-balanced"], 1),         # the equity report shares fields with it
    ("CQ16", ["--component", "two_column_allocation"], 3),      # two sections in balanced, one in equity
    ("CQ6", ["--column", "mer"], 2),                            # a column name used by both reports
    ("CQ9", ["--field", "mer"], 2),
    ("CQ18", [], 35),                                           # 33 fields in both reports, 2 only in balanced
])
def test_report_question_across_the_catalogue(cq, args, rows):
    _, out = run("semantic.py", "ask", CATALOGUE, cq, *args)
    assert f"→ answered, {rows} rows" in out.splitlines()[0], out


def test_question_names_the_parameter_it_lacks():
    code, out = run("semantic.py", "ask", CATALOGUE, "CQ2")
    assert code != 0 and "CQ2 needs --report" in out, out


def test_proposed_field_without_column_is_refused(tmp_path):
    import shutil
    shutil.copytree(EXAMPLE.parent, tmp_path / "r")
    lin = tmp_path / "r" / "semantic" / "lineage.yaml"
    lin.write_text(lin.read_text().replace("{status: proposed, column: mer}", "{status: proposed}"))
    code, out = run("semantic.py", "validate", tmp_path / "r" / "semantic")
    assert code == 1 and "field mer is proposed but names no column" in out, out


@needs_flow
def test_flow_graph_builds_and_has_no_violations():
    code, out = run("kgctl.py", "build")
    assert code == 0, out
    code, out = run("kgctl.py", "validate")
    assert code == 0 and "Violations: 0" in out, out
