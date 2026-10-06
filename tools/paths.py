"""Where the ontology package keeps its files.

Everything is relative to the repository root, except:
  FLOW_ROOT            the folder of the flow instance (holds flow/flow.json and the step scripts). The flow is owned
                       by whoever runs it, not by this package; only the flow commands of kgctl need it.
  ONTOLOGY_BUILD_DIR   where generated graphs go (default: build/). Generated files are never committed.
"""
import os, pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent
ONT = ROOT / "ontology"
SCHEMAS = ROOT / "schemas"
QUESTIONS = ROOT / "questions"
BUILD = pathlib.Path(os.environ.get("ONTOLOGY_BUILD_DIR") or ROOT / "build")
FIXTURES = ROOT / "fixtures"
EXAMPLE = FIXTURES / "fund-profile-balanced"
# the files of one report folder, as a person writes them (relative to the report folder)
FILE_OF = {"report": "semantic/report.yaml", "provenance": "semantic/provenance.yaml", "lineage": "semantic/lineage.yaml",
           "manifest": "manifest.json", "history": "semantic/history.yaml"}


def flow_root(arg=None):
    """The flow instance folder, from --flow-root or FLOW_ROOT. Exits with a clear message when neither is set."""
    p = arg or os.environ.get("FLOW_ROOT")
    if not p:
        raise SystemExit("this command reads the flow instance: pass --flow-root <folder holding flow/flow.json> or set FLOW_ROOT")
    p = pathlib.Path(p).expanduser().resolve()
    if not (p / "flow" / "flow.json").exists():
        raise SystemExit(f"no flow/flow.json under {p}")
    return p
