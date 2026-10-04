import importlib.util
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1] / "evals" / "interpretation_phase0"


def _runner():
    spec = importlib.util.spec_from_file_location("interpretation_phase0", ROOT / "run.py")
    module = importlib.util.module_from_spec(spec)
    assert spec.loader
    spec.loader.exec_module(module)
    return module


def test_all_phase0_packets_validate():
    module = _runner()
    packet = json.loads((ROOT / "cases.json").read_text())
    for case in packet["cases"]:
        module.validate_case(case)


def test_fixture_covers_required_domains_and_relations():
    packet = json.loads((ROOT / "cases.json").read_text())
    cases = packet["cases"]
    assert {"sophie", "rpd2", "bloom", "oracle", "worldview"} <= {
        case["product"] for case in cases
    }
    assert any(len(case["sidecar"]["hypotheses"]) > 1 for case in cases)
    assert any(
        hypothesis["evidence"]["contradicts"]
        for case in cases
        for hypothesis in case["sidecar"]["hypotheses"]
    )
    assert any(
        hypothesis["state"] == "superseded"
        for case in cases
        for hypothesis in case["sidecar"]["hypotheses"]
    )

