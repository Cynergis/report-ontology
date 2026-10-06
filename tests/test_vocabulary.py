"""Change control of the vocabularies (tools/vocabulary.py, kgctl.py ontology check|accept, kgctl.py rationale): every
change to a term, a shape or a question is sorted into breaking, additive or cosmetic, counted against the catalogue,
and refused when the version does not say so.

Each test edits a copy of ontology/ and questions/ and checks it against the repository's lock.
"""
import json, pathlib, shutil, sys
import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
import kg, vocabulary  # noqa: E402

FIXTURES = ROOT / "fixtures"


@pytest.fixture
def copy(tmp_path):
    shutil.copytree(ROOT / "ontology", tmp_path / "ontology")
    shutil.copytree(ROOT / "questions", tmp_path / "questions")
    return tmp_path


def edit(path, old, new):
    text = path.read_text()
    assert text.count(old) == 1, old
    path.write_text(text.replace(old, new))


def bump(copy, to):
    edit(copy / "ontology" / "report.ttl", 'owl:versionInfo "2.1.0"', f'owl:versionInfo "{to}"')
    edit(copy / "questions" / "report_cq.yaml", 'version: "2.1.0"', f'version: "{to}"')


def check(copy, catalogue=None):
    return vocabulary.check(copy / "ontology", copy / "questions", catalogue)


def kinds(r):
    return {(c["severity"], c["kind"], c["subject"]) for c in r["changes"]}


def test_the_repository_matches_its_lock(copy):
    r = check(copy)
    assert r["changes"] == [] and r["problems"] == [] and r["lock"]["versions"]["report"] == "2.1.0"


def test_a_removed_class_is_breaking_counted_and_needs_a_major_version(copy):
    ttl = copy / "ontology" / "report.ttl"
    text = ttl.read_text()
    start = text.index("rpt:Rule a owl:Class")
    ttl.write_text(text[:start] + text[text.index("rpt:DataSource a owl:Class"):])
    r = check(copy, FIXTURES)
    removed = next(c for c in r["changes"] if c["subject"] == "rpt:Rule")
    assert (removed["severity"], removed["kind"], removed["affected"]) == ("breaking", "class removed", 15)    # 8 + 7 rules in the fixtures
    assert r["problems"] == ["report: breaking change(s) since 2.1.0 need version 3.0.0 or later; the files say 2.1.0"]
    bump(copy, "3.0.0")
    assert check(copy)["problems"] == []


def test_a_new_property_needs_a_minor_version(copy):
    edit(copy / "ontology" / "report.ttl", "rpt:ruleText a owl:DatatypeProperty", '''rpt:ruleSource a owl:DatatypeProperty ; rdfs:label "rule source" ; rdfs:domain rpt:Rule ; rdfs:range xsd:string ;
    skos:definition "Where the rule comes from." .
rpt:ruleText a owl:DatatypeProperty''')
    r = check(copy)
    assert kinds(r) == {("additive", "datatype property added", "rpt:ruleSource")}
    assert r["problems"] == ["report: additive change(s) since 2.1.0 need version 2.2.0 or later; the files say 2.1.0"]
    bump(copy, "2.2.0")
    assert check(copy)["problems"] == []
    bump_back = copy / "ontology" / "report.ttl"
    edit(bump_back, 'owl:versionInfo "2.2.0"', 'owl:versionInfo "2.0.9"')
    assert "report: version went back from 2.1.0 to 2.0.9" in check(copy)["problems"]


def test_a_widened_domain_is_additive_and_a_narrowed_one_breaking(copy):
    ttl = copy / "ontology" / "report.ttl"
    edit(ttl, 'rpt:owner a owl:DatatypeProperty ; rdfs:label "owner" ; rdfs:domain rpt:ReportType ;',
         'rpt:owner a owl:DatatypeProperty ; rdfs:label "owner" ; rdfs:domain [ a owl:Class ; owl:unionOf ( rpt:ReportType rpt:Section ) ] ;')
    assert kinds(check(copy)) == {("additive", "domain widened", "rpt:owner")}
    edit(ttl, 'rdfs:label "owner" ; rdfs:domain [ a owl:Class ; owl:unionOf ( rpt:ReportType rpt:Section ) ] ;', 'rdfs:label "owner" ; rdfs:domain rpt:Section ;')
    r = check(copy, FIXTURES)
    assert [(c["kind"], c["affected"]) for c in r["changes"]] == [("domain changed", 2)]       # both fixture reports name an owner


def test_shapes_violations_break_warnings_add_messages_are_wording(copy):
    shapes = copy / "ontology" / "report-shapes.ttl"
    edit(shapes, '''sh:message "Report names no owner (CQ14)" ]''', '''sh:message "Report does not name its owner (CQ14)" ]''')
    assert kinds(check(copy)) == {("cosmetic", "message changed", "report-shapes.ttl#ReportData property rpt:owner")}
    edit(shapes, '''    sh:property [ sh:path rpt:purpose ; sh:minCount 1 ; sh:message "Section has no purpose" ] ;''',
         '''    sh:property [ sh:path rpt:purpose ; sh:minCount 1 ; sh:message "Section has no purpose" ] ;
    sh:property [ sh:path rpt:presentWhen ; sh:minCount 1 ; sh:message "Section does not say when it is present" ] ;''')
    r = check(copy, FIXTURES)
    added = next(c for c in r["changes"] if c["kind"] == "constraint added")
    assert added["severity"] == "breaking" and added["affected"] == 26 and "need version 3.0.0" in r["problems"][0]    # 27 sections, 1 conditional


def test_questions_removed_columns_break_rewording_does_not(copy):
    cq = copy / "questions" / "report_cq.yaml"
    edit(cq, "      SELECT ?fid ?rule ?regulatory WHERE {", "      SELECT ?fid ?rule WHERE {")
    edit(cq, '"Which fields of report $REPORT carry rules, and which rules are regulatory?"', '"Which fields of report $REPORT carry rules?"')
    assert kinds(check(copy)) == {("breaking", "answer columns removed", "CQ4"), ("cosmetic", "question reworded", "CQ4")}


def test_a_confirmation_covers_the_text_it_confirmed(copy):
    ttl = copy / "ontology" / "report.ttl"
    edit(ttl, 'rpt:Table a owl:Class ; rdfs:label "Table" ;', 'rpt:Table a owl:Class ; rdfs:label "Table" ; meta:validatedBy "dana" ; meta:validatedOn "2026-10-05" ;')
    r = check(copy)
    assert ("cosmetic", "validated", "rpt:Table") in kinds(r) and r["reconfirm"] == []
    vocabulary.accept("dana", copy / "ontology", copy / "questions", now="2026-10-06T00:00:00+00:00")
    edit(ttl, "A table of a data source, identified by dataset and name.", "A table or view of a data source, identified by dataset and name.")
    r = check(copy)
    assert r["reconfirm"] and r["reconfirm"][0].startswith("rpt:Table was validated by dana on 2026-10-05, before this change (definition changed)")


def test_accept_writes_the_lock_and_appends_to_the_changelog(copy):
    edit(copy / "ontology" / "report.ttl", 'rdfs:label "Approval" ;', 'rdfs:label "Approval" ; meta:rationale "A run without its gate decisions cannot be audited." ;')
    entry = vocabulary.accept("dana", copy / "ontology", copy / "questions", now="2026-10-06T00:00:00+00:00")
    assert entry["changes"] == [{"severity": "cosmetic", "kind": "rationale recorded", "subject": "rpt:Approval"}]
    lock = json.loads((copy / "ontology" / "ontology.lock.json").read_text())
    assert lock["accepted_by"] == "dana" and lock["terms"]["rpt:Approval"]["rationale"].startswith("A run without")
    assert (copy / "ontology" / "changelog.yaml").read_text().count("- at: ") == 3
    assert vocabulary.accept("dana", copy / "ontology", copy / "questions") is None                  # nothing left to accept
    bump(copy, "2.0.5")
    with pytest.raises(ValueError, match="refusing to accept: report: version went back"):
        vocabulary.accept("dana", copy / "ontology", copy / "questions")


def test_rationale_is_counted_and_confirmations_name_who_and_when(copy):
    r = vocabulary.rationale()
    report = r["summary"]["report"]
    assert report["classes"] == {"total": 20, "rationale": 2, "validated": 0} and report["questions"]["rationale"] == 2
    assert "rpt:ReportType" in r["missing_rationale"] and "CQ20" not in r["missing_rationale"]
    edit(copy / "ontology" / "report.ttl", 'rpt:Table a owl:Class ; rdfs:label "Table" ;', 'rpt:Table a owl:Class ; rdfs:label "Table" ; meta:validatedBy "dana" ;')
    edit(copy / "questions" / "report_cq.yaml", "    who: data team\n    question: \"If column", "    who: data team\n    validated_on: 5 October\n    question: \"If column")
    problems = vocabulary.confirmation_problems(vocabulary.snapshot(copy / "ontology", copy / "questions"))
    assert problems == ["rpt:Table records who it was validated but not when", "CQ6 records when it was validated but not who"]


def test_explain_says_why_a_term_exists_and_whether_it_was_confirmed():
    d = kg.explain("rpt:Revision")["matches"][0]
    assert d["rationale"].startswith("Without it a corrected meaning") and "git history" in d["alternatives"] and d["validated"] is False
    assert "CQ20" in d["questions"] and "rationale" not in kg.explain("rpt:Table")["matches"][0]
