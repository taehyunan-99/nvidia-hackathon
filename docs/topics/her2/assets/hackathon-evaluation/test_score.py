"""The scorecard must not hide failures, missing evidence or unrun checks."""
import copy
import importlib.util
import shutil
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("hackathon_score", HERE / "score.py")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def completed():
    card = module.read(HERE / "scorecard-template.json")
    card.update(reviewer="synthetic scorer test", evaluated_commit="synthetic-test-only")
    for row in card["results"]:
        row.update(status="pass", evidence=["synthetic-test-observation"])
    return card


def test_all_pass_scores_twenty():
    result = module.score(module.read(HERE / "cases.json"), completed())
    assert result["score_out_of_20"] == 20
    assert result["readiness"] == "internal_target_met"


def test_critical_failure_blocks_even_nineteen_points():
    card = completed()
    card["results"][0]["status"] = "fail"
    result = module.score(module.read(HERE / "cases.json"), card)
    assert result["score_out_of_20"] == 19
    assert result["critical_failures"] == ["I1"]
    assert result["readiness"] == "blocked_by_critical_failure"


def test_unrun_is_not_zero_or_a_completed_score():
    card = completed()
    card["results"][0]["status"] = "not_run"
    result = module.score(module.read(HERE / "cases.json"), card)
    assert result["score_out_of_20"] is None
    assert result["readiness"] == "incomplete"
    assert result["areas"]["입력·대응"]["evaluated"] == 3


@pytest.mark.parametrize("change", ["duplicate", "missing_evidence", "bad_status", "wrong_version", "no_reviewer"])
def test_invalid_scorecard_is_rejected(change):
    card = completed()
    if change == "duplicate":
        card["results"][1] = copy.deepcopy(card["results"][0])
    elif change == "missing_evidence":
        card["results"][0]["evidence"] = []
    elif change == "bad_status":
        card["results"][0]["status"] = "skip_and_pass"
    elif change == "wrong_version":
        card["dataset_version"] = "other"
    else:
        card["reviewer"] = None
    with pytest.raises(ValueError):
        module.score(module.read(HERE / "cases.json"), card)


def test_modified_input_is_rejected(tmp_path, monkeypatch):
    target = tmp_path / "data"
    shutil.copytree(HERE, target, ignore=shutil.ignore_patterns("__pycache__"))
    changed = target / "inputs/variant.json"
    changed.write_text(changed.read_text() + " ")
    monkeypatch.setattr(module, "HERE", target)
    with pytest.raises(ValueError, match="File changed"):
        module.validate_dataset()
