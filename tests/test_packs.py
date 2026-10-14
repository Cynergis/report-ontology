"""The packs of this repository: `report`, `product-report` and `flow`, each embedding the unit
maintained here (`oto/report`, `oto/product-report`, `oto/flow`) and the engine's own bases. Each
checks clean, and each embeds exactly the committed unit and the engine's copy of every base: after
a unit or the engine changes, `oto pack refresh packs/<name>` re-embeds it and this test says so
until then. Needs the OTO engine importable: OTO_HOME or ../oto beside this repository, or the
installed package."""
import filecmp
import json
import os
import pathlib
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent
UNITS = ROOT / "oto"
PACKS = sorted(p.name for p in (ROOT / "packs").iterdir() if (p / "manifest.json").exists())
PROVENANCE = ("source", "path", "ref", "commit", "registry", "fetched_at", "_about")
OTO = pathlib.Path(os.environ.get("OTO_HOME") or ROOT.parent / "oto")
if (OTO / "oto" / "__init__.py").exists() and str(OTO) not in sys.path:
    sys.path.insert(0, str(OTO))
try:
    import oto  # noqa: F401
    HAVE_OTO = True
except ImportError:
    HAVE_OTO = False
pytestmark = pytest.mark.skipif(not HAVE_OTO, reason="OTO engine not importable: set OTO_HOME or pip install oto-kg")


@pytest.fixture(autouse=True)
def bare_machine(tmp_path, monkeypatch):
    monkeypatch.setenv("OTO_ONTOLOGIES", str(tmp_path / "no-ontologies"))
    monkeypatch.setenv("OTO_PACKS", str(tmp_path / "no-packs"))
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(tmp_path / "no-claude"))


def _manifest(path):
    manifest = json.load(open(os.path.join(path, "manifest.json"), encoding="utf-8"))
    return {k: v for k, v in manifest.items() if k not in PROVENANCE}


def _same(a, b):
    """The same files; a manifest compared without the provenance that embedding it records."""
    if os.path.exists(os.path.join(a, "manifest.json")) and _manifest(a) != _manifest(b):
        return False
    cmp = filecmp.dircmp(a, b, ignore=[".DS_Store", "__pycache__", "manifest.json"])
    if cmp.left_only or cmp.right_only or cmp.funny_files:
        return False
    if filecmp.cmpfiles(a, b, cmp.common_files, shallow=False)[1:] != ([], []):
        return False
    return all(_same(os.path.join(a, d), os.path.join(b, d)) for d in cmp.common_dirs)


def test_the_three_packs_are_here():
    assert set(PACKS) == {"report", "product-report", "flow"}


@pytest.mark.parametrize("pack", PACKS)
def test_the_pack_checks_clean(pack):
    from oto.model import packs
    assert packs.check(str(ROOT / "packs" / pack)) == []


@pytest.mark.parametrize("pack", PACKS)
def test_the_pack_embeds_the_units_maintained_here_and_the_engines_bases(pack):
    from oto.model import ontologies
    embedded = ROOT / "packs" / pack / "ontology"
    for unit in sorted(os.listdir(embedded)):
        mine = UNITS / unit
        source = str(mine) if (mine / "manifest.json").exists() else ontologies.dir_for(unit)
        assert source and (mine.exists() or ontologies.origin(unit) == ontologies.BUILTIN), \
            "%s embeds %s, which neither this repository nor the engine holds" % (pack, unit)
        assert _same(str(embedded / unit), source), "packs/%s embeds an outdated %s: oto pack refresh packs/%s" % (pack, unit, pack)


def test_every_pack_skill_talks_in_plain_language():
    """Technical details are the record's: no skill talks in codes, ids or engine output, none offers
    them, and the examples are a generic report's."""
    for pack in PACKS:
        for skill in sorted((ROOT / "packs" / pack / "skills").glob("*/SKILL.md")):
            text = skill.read_text(encoding="utf-8")
            assert text.count("## Talking with the person") == 1 and "Never offer them" in text, skill
            assert "engine's words" not in text and "N of M" not in text, skill
    for skill in ("new-report", "ask-reports"):
        text = (ROOT / "packs" / "report" / "skills" / skill / "SKILL.md").read_text(encoding="utf-8").lower()
        assert "fund" not in text, skill
