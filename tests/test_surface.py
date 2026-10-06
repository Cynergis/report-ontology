"""The query surface (tools/kg.py): the operations a consumer calls, the SQLite export and the MCP server.

Runs against the two reports in fixtures/. The questions asked first are the ones the surface was built for:
which reports exist, what a report shows, where its data comes from, which reports are similar, which share a component.
"""
import asyncio, json, os, pathlib, shutil, sqlite3, subprocess, sys
import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
import kg  # noqa: E402

FIXTURES = ROOT / "fixtures"
needs_flow = pytest.mark.skipif(not os.environ.get("FLOW_ROOT"), reason="FLOW_ROOT not set: no flow instance to check")


def ask(question, **params):
    return kg.ask(question, params, FIXTURES)


@pytest.fixture
def draft(tmp_path):
    """A copy of the example report that a test may break."""
    shutil.copytree(FIXTURES / "fund-profile-balanced", tmp_path / "draft", ignore=shutil.ignore_patterns("*.graph.json"))
    return tmp_path / "draft"


def edit(path, old, new):
    text = path.read_text()
    assert text.count(old) == 1, old
    path.write_text(text.replace(old, new))


def accept(report, by, why=None):
    """Accept a report folder's definition the way a person does, through semantic.py accept."""
    r = subprocess.run([sys.executable, str(ROOT / "tools" / "semantic.py"), "accept", str(report / "semantic"), "--by", by, *(["--why", why] if why else [])],
                       capture_output=True, text=True)
    return r.returncode, r.stdout + r.stderr


# ───────────────────────────── questions and ask ─────────────────────────────
def test_questions_list_both_vocabularies_with_their_parameters():
    qs = {q["id"]: q for q in kg.questions()["questions"]}
    assert sum(q["vocabulary"] == "report" for q in qs.values()) == 21
    assert sum(q["vocabulary"] == "flow" for q in qs.values()) == 17
    assert qs["CQ14"]["parameters"] == [] and qs["CQ7"]["parameters"] == ["report"] and qs["CQ16"]["parameters"] == ["component"]
    assert qs["flow:CQ04"]["parameters"] == ["step"]


def test_which_report_types_exist():
    r = ask("CQ14")
    assert r["status"] == "answered" and [x["report"] for x in r["rows"]] == ["fund-profile-balanced", "fund-profile-equity"]
    assert r["rows"][0]["owner"] == "example-analyst" and r["rows"][0]["status"] == "in_validation" and r["skipped"] == []


def test_which_sections_and_fields_a_report_shows():
    r = ask("CQ2", report="fund-profile-balanced")
    assert len(r["rows"]) == 14 and r["rows"][0]["section"] == "header" and "fund_name" in r["rows"][0]["fields"]


def test_where_a_reports_data_comes_from():
    r = ask("CQ7", report="fund-profile-balanced")
    assert {(x["source"], x["kind"], x["dataset"], x["table"]) for x in r["rows"]} == {("warehouse", "bigquery", "reports", "fund_profile_balanced")}
    assert {x["param"]: x["column"] for x in r["rows"]} == {"fund_id": "fund_id", "series": "series", "as_of": "as_of"}
    r = ask("CQ5", report="fund-profile-balanced")
    assert r["status"] == "gap"                                    # most fields are not mapped yet, and the answer says so
    mapped = {x["fid"]: x["column"] for x in r["rows"] if "column" in x}
    assert mapped["mer"] == "mer" and len(mapped) == 5 and len(r["gaps"]) == 30
    stored = {x["fid"]: (x["type"], x["stored"]) for x in r["rows"]}       # one field, one column: structured fields are JSON text
    assert stored["holdings"] == ("grouped_list", "json") and stored["returns"] == ("list", "json") and stored["mer"] == ("percent_by_series", "json")
    assert stored["holdings_top_pct"] == ("percent", "value") and stored["fund_name"] == ("text", "value")


def test_which_other_reports_show_the_same_fields():
    r = ask("CQ15", report="fund-profile-balanced")
    assert [(x["other"], x["shared"]) for x in r["rows"]] == [("fund-profile-equity", "33")]


def test_which_reports_use_a_component():
    r = ask("CQ16", component="two_column_allocation")
    assert [(x["report"], x["section"]) for x in r["rows"]] == [("fund-profile-balanced", "credit"), ("fund-profile-balanced", "sector"), ("fund-profile-equity", "sector")]


def test_when_a_report_runs_and_what_is_expected_of_a_run():
    assert ask("CQ10", report="fund-profile-equity")["rows"][0]["runOn"] == "business_day:3"
    row = ask("CQ17", report="fund-profile-equity")["rows"][0]
    assert row["deliverWithinHours"] == "24" and row["runLog"] == "ops.report_runs" and set(row["alerts"].split("|")) == {"operations", "report-owner"}


def test_which_fields_the_catalogue_already_defines():
    rows = {x["fid"]: x for x in ask("CQ18")["rows"]}
    assert len(rows) == 35 and rows["mer"]["reports"] == "2" and rows["mer"]["label"] == "MER" and rows["credit_allocation"]["reports"] == "1"
    assert rows["holdings"]["type"] == "grouped_list" and "Major holdings" in rows["holdings"]["definition"]


def test_a_report_can_be_defined_before_any_build_run(draft):
    import yaml
    p = draft / "semantic" / "provenance.yaml"
    prov = yaml.safe_load(p.read_text()); del prov["runs"]; del prov["template"]
    p.write_text(yaml.safe_dump(prov, sort_keys=False))
    r = kg.gaps(draft)
    assert r["blocking"] == [] and r["shapes_checked"]


def test_ask_says_what_to_change():
    with pytest.raises(kg.KgError, match="CQ2 needs: report"):
        ask("CQ2")
    with pytest.raises(kg.KgError, match="unknown report nope; known: fund-profile-balanced, fund-profile-equity"):
        ask("CQ2", report="nope")
    with pytest.raises(kg.KgError, match="unknown question CQ99"):
        ask("CQ99")


def test_a_report_that_fails_validation_is_left_out_and_named(tmp_path):
    shutil.copytree(FIXTURES, tmp_path / "reports", ignore=shutil.ignore_patterns("*.graph.json"))
    edit(tmp_path / "reports" / "fund-profile-equity" / "semantic" / "lineage.yaml", "{status: proposed, column: mer}", "{status: proposed}")
    r = kg.ask("CQ14", {}, tmp_path / "reports")
    assert [x["report"] for x in r["rows"]] == ["fund-profile-balanced"]
    assert r["skipped"][0]["report"] == "fund-profile-equity" and "names no column" in r["skipped"][0]["errors"][0]
    with pytest.raises(kg.KgError, match="refusing to export: fund-profile-equity fails validation"):
        kg.export_sqlite(tmp_path / "reports", tmp_path / "out.db")
    assert not (tmp_path / "out.db").exists()


# ───────────────────────────── lifecycle ─────────────────────────────
def lifecycle(draft, *entries, frozen=None):
    """Rewrite a draft's status history (and optionally its manifest's frozen flag)."""
    import yaml
    p = draft / "semantic" / "provenance.yaml"
    prov = yaml.safe_load(p.read_text()); prov.pop("template", None)
    prov["lifecycle"] = [dict(zip(("status", "by", "at"), e)) for e in entries]
    p.write_text(yaml.safe_dump(prov, sort_keys=False))
    if frozen is not None:
        m = json.loads((draft / "manifest.json").read_text()); m["frozen"] = frozen
        (draft / "manifest.json").write_text(json.dumps(m))
    return kg.gaps(draft)


def test_where_a_report_is_in_its_lifecycle_and_who_recorded_each_step():
    rows = ask("CQ19", report="fund-profile-balanced")["rows"]
    assert [(x["step"], x["status"], x["by"], x["at"]) for x in rows] == [
        ("1", "inception", "example-analyst", "2026-10-02"), ("2", "saved", "example-analyst", "2026-10-02"),
        ("3", "in_validation", "example-reviewer", "2026-10-05")]
    assert [x.get("current") for x in rows] == [None, None, "yes"]


def test_the_status_is_updated_step_by_step(draft):
    r = lifecycle(draft, ("inception", "ana", "2026-10-01"))
    assert r["blocking"] == [] and r["lifecycle_status"] == "inception"
    r = lifecycle(draft, ("inception", "ana", "2026-10-01"), ("saved", "ana", "2026-10-02"), ("in_validation", "raj", "2026-10-06"))
    assert r["blocking"] == [] and r["lifecycle_status"] == "in_validation"
    r = lifecycle(draft, ("inception", "ana", "2026-10-01"), ("saved", "ana", "2026-10-02"), ("in_validation", "raj", "2026-10-06"),
                  ("saved", "raj", "2026-10-07"), ("in_validation", "raj", "2026-10-09"))             # sent back, then resubmitted
    assert r["blocking"] == [] and r["lifecycle_status"] == "in_validation"


def test_production_needs_a_frozen_release_and_says_who_deployed_it_when(draft, tmp_path):
    steps = [("inception", "ana", "2026-10-01"), ("saved", "ana", "2026-10-02"), ("in_validation", "raj", "2026-10-06"), ("in_production", "lee", "2026-10-20")]
    r = lifecycle(draft, *steps, frozen=False)
    assert [(b["path"], b["message"]) for b in r["blocking"]] == [("lifecycle.3.status", "lifecycle: in_production needs a frozen release (manifest.frozen is not true)")]
    r = lifecycle(draft, *steps, frozen=True)           # freezing changes the release contract: in production it must be accepted
    assert [b["file"] for b in r["blocking"]] == ["semantic/history.yaml"] and "first manifest.json → frozen" in r["blocking"][0]["message"]
    assert accept(draft, "lee", "release 1.0.0 frozen for production")[0] == 0
    assert kg.gaps(draft)["blocking"] == []
    (tmp_path / "reports").mkdir(); shutil.copytree(draft, tmp_path / "reports" / "fund-profile-balanced")
    last = kg.ask("CQ19", {"report": "fund-profile-balanced"}, tmp_path / "reports")["rows"][-1]
    assert (last["status"], last["by"], last["at"], last["current"]) == ("in_production", "lee", "2026-10-20", "yes")


def test_lifecycle_rules(draft):
    said = lambda *entries: [b["message"] for b in lifecycle(draft, *entries)["blocking"]]
    assert said(("saved", "ana", "2026-10-01")) == ["lifecycle: the first status is saved; a report starts at inception"]
    assert said(("inception", "ana", "2026-10-01"), ("in_validation", "raj", "2026-10-02")) == [
        "lifecycle: in_validation cannot follow inception; the status after inception is saved"]
    assert said(("inception", "ana", "2026-10-05"), ("saved", "ana", "2026-10-01")) == ["lifecycle: step 2 (2026-10-01) is dated before step 1 (2026-10-05)"]
    assert said(("inception", None, "2026-10-01")) == ["provenance: lifecycle.0.by: None is not of type 'string'"]          # who is never optional
    import yaml
    p = draft / "semantic" / "provenance.yaml"; prov = yaml.safe_load(p.read_text()); del prov["lifecycle"]; p.write_text(yaml.safe_dump(prov))
    assert [(b["file"], b["path"]) for b in kg.gaps(draft)["blocking"]] == [("semantic/provenance.yaml", "lifecycle")]


def test_a_report_still_at_inception_shows_its_status_even_when_it_does_not_compile(tmp_path):
    shutil.copytree(FIXTURES, tmp_path / "reports", ignore=shutil.ignore_patterns("*.graph.json"))
    d = tmp_path / "reports" / "fund-profile-equity"
    lifecycle(d, ("inception", "ana", "2026-10-01"))
    edit(d / "semantic" / "lineage.yaml", "{status: proposed, column: mer}", "{status: proposed}")
    r = kg.ask("CQ14", {}, tmp_path / "reports")
    assert [x["report"] for x in r["rows"]] == ["fund-profile-balanced"]
    assert (r["skipped"][0]["report"], r["skipped"][0]["lifecycle_status"]) == ("fund-profile-equity", "inception")


# ───────────────────────────── explain ─────────────────────────────
def test_explain_an_edge():
    m = {x["term"]: x for x in kg.explain("sourcedFrom")["matches"]}
    assert set(m) == {"rpt:sourcedFrom", "dt:sourcedFrom"}        # same name in two vocabularies: both are returned
    e = m["rpt:sourcedFrom"]
    assert e["domain"] == ["rpt:Field"] and e["range"] == ["rpt:Column"] and e["questions"] == ["CQ5", "CQ6"]
    assert e["written_in"] == ["semantic/lineage.yaml → fields.*.column"] and "analyst verifies" in e["definition"]
    assert kg.explain("reads table")["matches"][0]["term"] == "rpt:readsTable"           # by label
    assert kg.explain("rpt:purpose")["matches"][0]["domain"] == ["rpt:ReportType", "rpt:Section"]   # a union domain


def test_explain_a_class_lists_its_edges():
    c = kg.explain("rpt:Field")["matches"][0]
    assert {"term": "rpt:sourcedFrom", "to": ["rpt:Column"]} in c["properties"]
    assert {"term": "rpt:hasField", "from": ["rpt:Section"]} in c["referenced_by"]
    assert "CQ15" in c["questions"]


def test_explain_unknown_term_suggests():
    r = kg.explain("sourcedFrm")
    assert r["matches"] == [] and "rpt:sourcedFrom" not in r["matches"] and "dt:sourcedFrom" in r["did_you_mean"]


def test_every_term_of_the_three_vocabularies_explains_itself():
    lacking = []
    for term, (_, kind) in kg.all_terms().items():
        d = kg.describe(term)
        need = ["label", "definition"] + ([] if kind == "class" else ["domain", "range"])
        lacking += [f"{term}: {k}" for k in need if not d[k]]
    assert len(kg.all_terms()) == 265 and lacking == []


def test_bindings_name_only_declared_classes():
    from rdflib import Graph
    g = Graph(); g.parse(ROOT / "ontology" / "bindings.ttl")
    named = {kg.short(o) for p in ("carries", "concerns") for o in g.objects(None, kg.kgctl.FLOW[p])}
    assert named and named - {t for t, (_, k) in kg.all_terms().items() if k == "class"} == set()


# ───────────────────────────── navigation ─────────────────────────────
def test_resolve_finds_a_field_by_any_of_its_names():
    ids = lambda r: [e["id"] for e in r["entities"]]
    both = ["report/fund-profile-balanced/field/mer", "report/fund-profile-equity/field/mer"]
    assert ids(kg.resolve("management expense ratio", catalogue_dir=FIXTURES)) == both          # an alias
    assert ids(kg.resolve("RFG", catalogue_dir=FIXTURES)) == both                               # the French label
    assert ids(kg.resolve("mer", "fund-profile-equity", FIXTURES)) == ["report/fund-profile-equity/field/mer", "report/fund-profile-equity/field/mer_as_of"]
    assert ids(kg.resolve("mer", catalogue_dir=FIXTURES))[2:4] == ["table/warehouse.reports.fund_profile_balanced/mer", "table/warehouse.reports.fund_profile_equity/mer"]
    r = kg.resolve("Field", catalogue_dir=FIXTURES)
    assert [t["term"] for t in r["terms"]] == ["flow:Field", "rpt:Field"]                     # the same name in two vocabularies
    assert "management fee" in kg.resolve("managment fee", catalogue_dir=FIXTURES)["did_you_mean"]


def test_entity_shows_values_edges_both_ways_and_history():
    r = kg.entity("mer", "fund-profile-balanced", FIXTURES)
    e = r["entity"]
    assert e["values"]["rpt:alias"] == ["management expense ratio", "ratio des frais de gestion"] and e["values"]["rpt:lineageStatus"] == ["proposed"]
    assert {"property": "rpt:sourcedFrom", "to": "table/warehouse.reports.fund_profile_balanced/mer", "label": "mer", "type": "rpt:Column"} in e["out"]
    assert [x["from"] for x in e["in"]] == ["report/fund-profile-balanced/section/key_data"]
    assert [(h["revision"], h["fact"].split(" → ")[1], h["kind"]) for h in e["history"]] == [(2, "fields.mer.column", "added"), (2, "fields.mer.status", "changed")]
    assert kg.entity("fund-profile-balanced", catalogue_dir=FIXTURES)["entity"]["history"]["revisions"] == 2
    assert kg.entity("nothing like it", catalogue_dir=FIXTURES)["entity"] is None


def test_neighbors_walk_the_graph():
    r = kg.neighbors("fund-profile-equity", "hasSection", "out", catalogue_dir=FIXTURES)
    assert len(r["edges"]) == 13 and {e["property"] for e in r["edges"]} == {"rpt:hasSection"}
    two = kg.neighbors("two_column_allocation", direction="in", depth=2, catalogue_dir=FIXTURES)
    assert {"report/fund-profile-balanced/", "report/fund-profile-equity/"} <= set(two["nodes"])        # component ← section ← report
    with pytest.raises(kg.KgError, match="direction is out, in or both"):
        kg.neighbors("mer", direction="up", catalogue_dir=FIXTURES)


def test_search_reads_meanings_in_every_locale_purposes_and_rules():
    r = kg.search("frais de gestion", catalogue_dir=FIXTURES)
    assert {e["id"].rsplit("/", 1)[1] for e in r["entities"]} == {"mer", "management_fee"}
    r = kg.search("sums to 100", "Section", "fund-profile-balanced", catalogue_dir=FIXTURES)
    assert [e["id"] for e in r["entities"]] == ["report/fund-profile-balanced/section/regional", "report/fund-profile-balanced/section/sector"]
    assert kg.search("superseded never overwritten", catalogue_dir=FIXTURES)["entities"] == []
    assert kg.search("waivers net", catalogue_dir=FIXTURES)["count"] == 0
    with pytest.raises(kg.KgError):
        kg.search("?", catalogue_dir=FIXTURES)


def test_overview_is_the_map_of_the_catalogue():
    o = kg.overview(catalogue_dir=FIXTURES)
    assert o["reports"]["by_status"] == {"in_validation": 2} and o["mapping"] == {"proposed": 10, "unmapped": 58}
    assert o["nodes_by_class"]["rpt:Field"] == 68 and o["components"][0] == {"component": "two_column_allocation", "sections": 3}
    assert o["history"]["recent"][0] == {"report": "fund-profile-balanced", "revision": 2, "at": "2026-10-04T14:00:00+00:00", "by": "example-analyst",
                                         "why": "the agent proposed a column of the report's table for five fields; the analyst still has to verify them", "changes": 10}
    assert o["history"]["not_accepted"] == [] and o["history"]["no_history"] == []
    assert o["rationale"]["report"]["with_why"] >= 4 and "a map, not an answer" in o["hint"]


def test_gaps_name_the_last_accepted_revision():
    r = kg.gaps(FIXTURES / "fund-profile-balanced")
    assert r["history"]["last"]["revision"] == 2 and r["pending"]["count"] == 0


# ───────────────────────────── requirements ─────────────────────────────
def test_requirements_say_where_what_and_who():
    r = kg.requirements()
    items = {(i["file"], i["path"]): i for i in r["items"]}
    owner = items[("semantic/report.yaml", "report.owner")]
    assert owner["provided_by"] == "analyst" and owner["term"] == "rpt:owner" and "analyst responsible" in owner["meaning"]
    col = items[("semantic/lineage.yaml", "fields.*.column")]
    assert col["provided_by"] == "agent" and col["when"] == "for each entry of fields" and col["required"] is False
    assert items[("semantic/lineage.yaml", "source.kind")]["when"] == "source is given"
    assert items[("manifest.json", "observability.run_log")] == {**items[("manifest.json", "observability.run_log")], "required": True, "provided_by": "analyst"}
    assert items[("semantic/provenance.yaml", "source_reports[].sha256")]["provided_by"] == "flow"
    assert all(i["provided_by"] in kg.PROVIDERS for i in r["items"])
    assert [i["path"] for i in r["items"] if i.get("term", "").startswith("rpt:") and not i.get("meaning") and not i["term"][4].isupper()] == []


def test_requirements_for_the_analyst_start_the_interview():
    always = {i["path"] for i in kg.requirements("analyst")["items"] if i["required"] and "when" not in i}
    assert {"report.id", "report.purpose", "report.parameters", "schedule.cadence", "publish.path",
            "observability.deliver_within_hours", "observability.alert", "source_reports"} <= always
    assert not any(p.startswith(("sections", "fields")) for p in always)        # those are drafted by the agent


# ───────────────────────────── gaps ─────────────────────────────
def test_gaps_of_the_example_are_warnings_only():
    r = kg.gaps(FIXTURES / "fund-profile-balanced")
    assert r["status"] == "incomplete" and r["blocking"] == [] and r["shapes_checked"]
    unmapped = next(w for w in r["warnings"] if w.get("term") == "rpt:lineageStatus")
    assert unmapped["count"] == 30 and unmapped["written_in"] == ["semantic/lineage.yaml → fields.*.status"]
    assert kg.gaps("fund-profile-equity", FIXTURES)["report"] == "fund-profile-equity"      # by name in the catalogue


def test_gaps_list_exactly_what_was_removed(draft):
    manifest = json.loads((draft / "manifest.json").read_text())
    del manifest["observability"]; del manifest["schedule"]["timezone"]
    (draft / "manifest.json").write_text(json.dumps(manifest))
    edit(draft / "semantic" / "report.yaml", "    purpose: The teams and named individuals responsible for the portfolio.\n", "")
    edit(draft / "semantic" / "lineage.yaml", "{status: proposed, column: mer}", "{status: proposed}")
    r = kg.gaps(draft)
    assert r["status"] == "blocked" and not r["shapes_checked"]
    assert sorted((b["file"], b["path"]) for b in r["blocking"]) == [
        ("manifest.json", "observability"), ("manifest.json", "schedule.timezone"),
        ("semantic/lineage.yaml", "fields.mer.column"), ("semantic/report.yaml", "sections.5.purpose")]


def test_gaps_report_a_missing_owner_as_a_warning_with_its_place(draft):
    edit(draft / "semantic" / "report.yaml", "  owner: example-analyst      # the report analyst responsible for the definition and the mapping\n", "")
    r = kg.gaps(draft)
    owner = next(w for w in r["warnings"] if w.get("term") == "rpt:owner")
    assert r["status"] == "incomplete" and owner["written_in"] == ["semantic/report.yaml → report.owner"] and owner["subjects"] == ["report"]


def test_gaps_of_an_empty_draft(tmp_path):
    (tmp_path / "new-report").mkdir()
    r = kg.gaps(tmp_path / "new-report")
    assert r["status"] == "blocked" and r["blocking"][0]["message"] == "report.yaml missing"


# ───────────────────────────── SQLite export ─────────────────────────────
def test_sqlite_export_matches_the_graph(tmp_path):
    from rdflib import RDF, URIRef
    r = kg.export_sqlite(FIXTURES, tmp_path / "catalogue.db")
    data = kg.catalogue(FIXTURES)["data"]
    nodes = set(data.subjects(RDF.type, None))
    edges = {(s, p, o) for s, p, o in data if isinstance(o, URIRef) and p != RDF.type}
    db = sqlite3.connect(tmp_path / "catalogue.db")
    one = lambda sql: db.execute(sql).fetchone()[0]
    assert one("SELECT count(*) FROM nodes") == len(nodes) == r["nodes"]
    assert one("SELECT count(*) FROM edges") == len(edges) == r["edges"]
    assert one("SELECT count(*) FROM terms") == len(kg.all_terms()) and one("SELECT count(*) FROM questions") == 38
    assert one("SELECT count(*) FROM edges e WHERE NOT EXISTS (SELECT 1 FROM nodes n WHERE n.id = e.source) OR NOT EXISTS (SELECT 1 FROM nodes n WHERE n.id = e.target)") == 0
    assert one("SELECT count(*) FROM edges e WHERE NOT EXISTS (SELECT 1 FROM terms t WHERE t.term = e.property AND t.definition <> '')") == 0
    # the export answers the catalogue question on its own, and explains the edge it follows
    assert [x[0] for x in db.execute("SELECT label FROM nodes WHERE type = 'rpt:ReportType' ORDER BY label")] == ["Fund Profile (Balanced)", "Fund Profile (Equity)"]
    table = db.execute("""SELECT json_extract(t.properties, '$."rpt:tableName"[0]') FROM nodes r JOIN edges e ON e.source = r.id AND e.property = 'rpt:readsTable'
                          JOIN nodes t ON t.id = e.target WHERE r.report = 'fund-profile-equity' AND r.type = 'rpt:ReportType'""").fetchone()[0]
    assert table == "fund_profile_equity"
    assert dict(db.execute("SELECT key, value FROM meta"))["report_ontology_version"] == "2.1.0"
    assert one("SELECT rationale FROM terms WHERE term = 'rpt:Revision'").startswith("Without it a corrected meaning")


@needs_flow
def test_flow_questions_and_flow_export(tmp_path):
    r = kg.ask("flow:CQ04", {"step": "B10_verify"})
    assert r["status"] == "answered" and "fidelity" in {x["checkId"] for x in r["rows"]}
    with pytest.raises(kg.KgError, match="flow:CQ04 needs: step"):
        kg.ask("flow:CQ04", {})
    out = kg.export_sqlite(FIXTURES, tmp_path / "with-flow.db", with_flow=True)
    db = sqlite3.connect(tmp_path / "with-flow.db")
    assert out["includes_flow"] and db.execute("SELECT count(*) FROM nodes WHERE type = 'flow:DeterministicStep'").fetchone()[0] > 0
    dangling = "SELECT count(*) FROM edges e WHERE NOT EXISTS (SELECT 1 FROM nodes n WHERE n.id = e.target) AND NOT EXISTS (SELECT 1 FROM terms t WHERE t.iri = e.target)"
    assert db.execute(dangling).fetchone()[0] == 0


# ───────────────────────────── command line and MCP ─────────────────────────────
def test_command_line_prints_json_and_reports_errors_as_json():
    import subprocess
    run = lambda *a: subprocess.run([sys.executable, str(ROOT / "tools" / "kg.py"), *a], capture_output=True, text=True)
    r = run("ask", "CQ14", "--catalogue", str(FIXTURES))
    assert r.returncode == 0 and len(json.loads(r.stdout)["rows"]) == 2
    r = run("ask", "CQ14")
    assert r.returncode == 2 and "no catalogue" in json.loads(r.stdout)["error"]


def test_catalogue_defaults_to_a_reports_folder_in_the_working_directory(tmp_path, monkeypatch):
    shutil.copytree(FIXTURES, tmp_path / "reports", ignore=shutil.ignore_patterns("*.graph.json"))
    monkeypatch.delenv("REPORTS_ROOT", raising=False); monkeypatch.chdir(tmp_path)
    assert len(kg.ask("CQ14")["rows"]) == 2
    assert kg.gaps("fund-profile-equity")["report"] == "fund-profile-equity"           # a report named, not pathed
    with pytest.raises(kg.KgError, match="no report folder nope in the catalogue"):
        kg.gaps("nope")


def test_the_catalogue_shows_the_scheduled_cadence_when_the_report_declares_none(tmp_path):
    shutil.copytree(FIXTURES, tmp_path / "reports", ignore=shutil.ignore_patterns("*.graph.json"))
    edit(tmp_path / "reports" / "fund-profile-equity" / "semantic" / "report.yaml", "  cadence: monthly\n", "")
    rows = {x["report"]: x for x in kg.ask("CQ14", {}, tmp_path / "reports")["rows"]}
    assert rows["fund-profile-equity"]["cadence"] == "monthly"                         # from the release's schedule


def test_mcp_server_serves_the_operations():
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client

    async def session_calls():
        params = StdioServerParameters(command=sys.executable, args=[str(ROOT / "tools" / "mcp_server.py")],
                                       env={**os.environ, "REPORTS_ROOT": str(FIXTURES)})
        async with stdio_client(params) as streams, ClientSession(streams[0], streams[1]) as session:
            await session.initialize()
            tools = sorted(t.name for t in (await session.list_tools()).tools)
            call = lambda name, **args: session.call_tool(name, args)
            results = [await call("ask", question="CQ14"), await call("ask", question="CQ2"), await call("explain", term="readsTable"),
                       await call("gaps", report="fund-profile-balanced"), await call("requirements", provided_by="analyst"),
                       await call("list_questions", vocabulary="report"), await call("resolve", term="management expense ratio"),
                       await call("history", report="fund-profile-balanced", as_of="2026-10-03", fact="fields.mer.status"),
                       await call("neighbors", term="bar_chart", direction="in")]
            return tools, [json.loads(r.content[0].text) for r in results]

    tools, (catalogue, missing, edge, gaps, reqs, qs, named, before, around) = asyncio.run(session_calls())
    assert tools == ["ask", "entity", "explain", "gaps", "history", "list_questions", "neighbors", "overview", "requirements", "resolve", "search", "stale"]
    assert [x["report"] for x in catalogue["rows"]] == ["fund-profile-balanced", "fund-profile-equity"]
    assert missing == {"error": "CQ2 needs: report"}
    assert edge["matches"][0]["range"] == ["rpt:Table"] and gaps["status"] == "incomplete"
    assert reqs["count"] > 40 and len(qs["questions"]) == 21
    assert {e["id"] for e in named["entities"]} == {"report/fund-profile-balanced/field/mer", "report/fund-profile-equity/field/mer"}
    assert before["facts"] == {"semantic/lineage.yaml → fields.mer.status": "unmapped"}
    assert {e["source"] for e in around["edges"]} == {"report/fund-profile-balanced/section/calendar", "report/fund-profile-equity/section/calendar"}
