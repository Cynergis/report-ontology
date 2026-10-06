"""The accepted history of a report's definition (tools/ledger.py, semantic.py diff/accept, kg.py history and stale):
a changed fact is superseded, never overwritten, and the definition can be read as it stood on any date.

Runs on copies of the example report, so a test may change it.
"""
import pathlib, shutil, subprocess, sys
import pytest
import yaml

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
import kg, ledger, semantic  # noqa: E402

FIXTURES = ROOT / "fixtures"
MEANING = "Management expense ratio, per series shown, as of the last audited or interim statement."
MER = "semantic/report.yaml → fields.mer.meaning"


def tool(*args):
    r = subprocess.run([sys.executable, str(ROOT / "tools" / "semantic.py"), *map(str, args)], capture_output=True, text=True)
    return r.returncode, r.stdout + r.stderr


@pytest.fixture
def draft(tmp_path):
    shutil.copytree(FIXTURES / "fund-profile-balanced", tmp_path / "reports" / "fund-profile-balanced", ignore=shutil.ignore_patterns("*.graph.json"))
    return tmp_path / "reports" / "fund-profile-balanced"


def edit(path, old, new):
    text = path.read_text()
    assert text.count(old) == 1, old
    path.write_text(text.replace(old, new))


def new_meaning(draft):
    edit(draft / "semantic" / "report.yaml", f'meaning: "{MEANING}"', 'meaning: "Management expense ratio of the series, net of waivers, from the last audited or interim statement."')


# ───────────────────────────── what a fact is ─────────────────────────────
def test_every_value_of_the_definition_is_a_named_fact():
    f = ledger.facts(semantic.load(FIXTURES / "fund-profile-balanced" / "semantic"))
    assert f[MER] == MEANING
    assert f["semantic/lineage.yaml → fields.mer.column"] == "mer" and f["manifest.json → schedule.run_on"] == "business_day:3"
    assert f["semantic/report.yaml → sections"][:3] == ["header", "returns", "regional"]            # the order of sections is a fact
    assert f["semantic/report.yaml → sections.header.fields"] == ["fund_name", "series", "category"]
    assert f["semantic/report.yaml → report.parameters.fund_id.meaning"] == "Identifier of the fund the document describes"
    assert not any(k.startswith("semantic/provenance.yaml") for k in f)                               # provenance is a log already


# ───────────────────────────── accept: the gate ─────────────────────────────
def test_a_first_accept_records_the_whole_definition(draft):
    (draft / "semantic" / "history.yaml").unlink()
    assert tool("diff", draft / "semantic")[0] == 1
    code, out = tool("accept", draft / "semantic", "--by", "ana")
    assert code == 0 and "accepted revision 1 by ana" in out, out
    files = semantic.load(draft / "semantic")
    assert ledger.revisions(files)[0]["facts"] == ledger.facts(files) and ledger.count(ledger.pending(files)) == 0
    assert tool("accept", draft / "semantic", "--by", "ana")[1].strip().endswith("nothing to accept: the files match revision 1")


def test_a_changed_meaning_is_pending_until_someone_accepts_it_and_says_why(draft):
    new_meaning(draft)
    code, out = tool("diff", draft / "semantic")
    assert code == 1 and f"~ {MER}" in out
    assert kg.gaps(draft)["pending"]["changed"][0]["from"] == MEANING                   # pending is reported, not a gap
    code, out = tool("accept", draft / "semantic", "--by", "ana")
    assert code == 1 and "say why with --why" in out and MER in out                    # an overwrite needs a reason
    code, out = tool("accept", draft / "semantic", "--by", "ana", "--why", "the MER is shown net of waivers since the 2026 prospectus")
    assert code == 0 and "revision 3" in out, out
    last = ledger.revisions(semantic.load(draft / "semantic"))[-1]
    assert last["changes"] == [{"fact": MER, "kind": "changed", "from": MEANING, "to": last["changes"][0]["to"]}]
    assert kg.gaps(draft)["pending"]["count"] == 0 and kg.gaps(draft)["history"]["last"]["by"] == "ana"


def test_additions_need_no_reason(draft):
    edit(draft / "semantic" / "lineage.yaml", "  fund_name:          {status: unmapped}", "  fund_name:          {status: unmapped, note: owned by marketing}")
    code, out = tool("accept", draft / "semantic", "--by", "ana")
    assert code == 0 and ledger.revisions(semantic.load(draft / "semantic"))[-1]["why"] == "1 fact(s) added", out


def test_a_definition_that_does_not_validate_cannot_be_accepted(draft):
    edit(draft / "semantic" / "lineage.yaml", "{status: proposed, column: mer}", "{status: proposed}")
    code, out = tool("accept", draft / "semantic", "--by", "ana", "--why", "x")
    assert code == 1 and "refusing to accept" in out and "names no column" in out
    assert len(ledger.revisions(semantic.load(draft / "semantic"))) == 2
    assert tool("accept", draft / "semantic", "--by", "<you>", "--why", "x")[0] == 1                  # nobody is not a person


# ───────────────────────────── the history answers ─────────────────────────────
def test_the_definition_as_it_stood_on_a_date(draft):
    new_meaning(draft)
    tool("accept", draft / "semantic", "--by", "ana", "--why", "net of waivers", "--effective", "2026-11-01")
    h = lambda **k: kg.history(draft, fact="fields.mer.", **k)
    assert h(as_of="2026-10-03")["facts"]["semantic/lineage.yaml → fields.mer.status"] == "unmapped"      # before the column was proposed
    assert h(as_of="2026-10-20")["facts"][MER] == MEANING                                                # recorded, but applies from November
    assert h(as_of="2026-11-01")["facts"][MER].startswith("Management expense ratio of the series, net of waivers")
    assert h(known_on="2026-10-03")["revisions_applied"] == [1]
    revs = kg.history(draft, fact="fields.mer.meaning")["revisions"]
    assert [(r["revision"], [c["kind"] for c in r.get("changes", [])]) for r in revs] == [(1, []), (3, ["changed"])]
    with pytest.raises(kg.KgError, match="as_of is a date"):
        kg.history(draft, as_of="last week")


def test_the_graph_says_what_changed_who_accepted_it_and_why(draft):
    new_meaning(draft)
    tool("accept", draft / "semantic", "--by", "ana", "--why", "net of waivers")
    rows = kg.ask("CQ21", {"field": "mer"}, draft.parent)["rows"]
    meaning = next(r for r in rows if r["fact"] == MER)
    assert (meaning["revision"], meaning["by"], meaning["why"], meaning["kind"], meaning["from"]) == ("3", "ana", "net of waivers", "changed", MEANING)
    first = kg.ask("CQ20", {"report": "fund-profile-balanced"}, draft.parent)["rows"][0]
    assert (first["revision"], first["by"]) == ("1", "example-analyst") and "fact" not in first        # the baseline lists no changes
    card = kg.entity("mer", "fund-profile-balanced", draft.parent)["entity"]
    assert [c["kind"] for c in card["history"] if c["fact"] == MER] == ["changed"]


def test_a_report_without_history_is_answered_with_a_gap(draft):
    (draft / "semantic" / "history.yaml").unlink()
    r = kg.ask("CQ20", {"report": "fund-profile-balanced"}, draft.parent)
    assert r["status"] == "gap" and r["gaps"][0]["why"].startswith("report has no accepted revision")
    assert any("no accepted revision" in w["message"] for w in kg.gaps(draft)["warnings"])                 # a warning, not a block
    assert kg.stale(catalogue_dir=draft.parent)["summary"] == {"no history": 1}


# ───────────────────────────── integrity ─────────────────────────────
def test_a_history_edited_by_hand_is_refused(draft):
    edit(draft / "semantic" / "history.yaml", "    from: unmapped\n    to: proposed\n  - fact: semantic/lineage.yaml → fields.mer.column",
         "    from: verified\n    to: proposed\n  - fact: semantic/lineage.yaml → fields.mer.column")
    errors, _ = semantic.validate(semantic.load(draft / "semantic"))
    assert any("the file was edited by hand" in e for e in errors), errors
    assert kg.ask("CQ14", {}, draft.parent)["skipped"][0]["report"] == "fund-profile-balanced"


def test_revisions_are_numbered_and_dated_in_order(draft):
    p = draft / "semantic" / "history.yaml"
    h = yaml.safe_load(p.read_text()); h["revisions"][1]["at"] = "2026-10-01T00:00:00+00:00"; h["revisions"][1]["revision"] = 5
    p.write_text(yaml.safe_dump(h, allow_unicode=True))
    errors, _ = semantic.validate(semantic.load(draft / "semantic"))
    assert any("entry 2 is numbered 5" in e for e in errors) and any("recorded before revision 1" in e for e in errors), errors


def test_a_report_in_production_refuses_a_change_nobody_accepted(draft):
    m = draft / "manifest.json"
    edit(m, '"frozen": false', '"frozen": true')
    tool("accept", draft / "semantic", "--by", "lee", "--why", "release frozen")
    edit(draft / "semantic" / "provenance.yaml", "  - {status: in_validation, by: example-reviewer, at: 2026-10-05, note: blueprint approved; template under visual verification}",
         "  - {status: in_validation, by: example-reviewer, at: 2026-10-05}\n  - {status: in_production, by: lee, at: 2026-10-20}")
    assert kg.gaps(draft)["blocking"] == []
    new_meaning(draft)
    blocking = kg.gaps(draft)["blocking"]
    assert [b["file"] for b in blocking] == ["semantic/history.yaml"] and "changed without being accepted" in blocking[0]["message"]
    assert tool("accept", draft / "semantic", "--by", "ana", "--why", "net of waivers")[0] == 0           # accept is how it is resolved
    assert kg.gaps(draft)["blocking"] == []


# ───────────────────────────── stale ─────────────────────────────
def test_stale_names_unverified_mappings_idle_statuses_and_unaccepted_changes(draft):
    s = kg.stale(30, "2026-11-20", draft.parent)
    assert s["summary"] == {"status unchanged": 1, "mapping not verified": 5}
    mer = next(i for i in s["items"] if i.get("field") == "mer")
    assert (mer["since"], mer["days"], mer["revision"], mer["column"]) == ("2026-10-04", 47, 2, "mer")
    assert kg.stale(30, "2026-10-20", draft.parent)["summary"] == {}
    new_meaning(draft)
    item = next(i for i in kg.stale(30, "2026-10-20", draft.parent)["items"] if i["kind"] == "not accepted")
    assert item["first"] == [MER] and item["since"] == "2026-10-04"
