"""응답 순서에 관계없이 선택한 구조와 신뢰도가 함께 이동해야 한다."""
import pytest

from logic.flow import run_flow
from logic.tests.test_flow import StubClient, _prediction_candidates, make_request


@pytest.mark.parametrize("scores,index,value", [
    ([0.2, 0.9, 0.4], 1, 0.9),
    ([0.9, 0.9, 0.4], 0, 0.9),
    ([None, 0.7, float("nan")], 1, 0.7),
    ([True, float("inf"), -0.1], 0, None),
    ([0.9], 0, None),
    (0.9, 0, None),
    (None, 0, None),
])
def test_selected_structure_and_confidence_stay_paired(tmp_path, scores, index, value):
    bodies = [f"data_sample_{i}\n#\n" for i in range(3)]

    class Client(StubClient):
        def predict_complex(self, polymers, **kwargs):
            assert kwargs.get("diffusion_samples", 1) == 1
            return {"structures": [{"structure": b} for b in bodies], "confidence_scores": scores}

    output, _ = run_flow(make_request(_prediction_candidates(), tmp_path), client=Client())
    for artifact in output["result"]["artifacts"]:
        if artifact["role"] == "structure":
            assert (tmp_path / artifact["file_name"]).read_text() == bodies[index]
    evidence = [e for e in output["result"]["evidence"] if e["topic"] == "prediction_confidence"]
    assert len(evidence) == 2
    assert all(e["value"] == value for e in evidence)
    assert all(e["measurement_state"] == ("unknown" if value is None else "measured") for e in evidence)


def test_empty_structure_is_not_selected_even_with_high_confidence(tmp_path):
    response = {"structures": [{"structure": ""}, {"structure": "data_good\n#\n"}],
                "confidence_scores": [0.99, 0.8]}
    output, _ = run_flow(make_request(_prediction_candidates(), tmp_path),
                         client=StubClient(response=response))
    assert all((tmp_path / a["file_name"]).read_text() == "data_good\n#\n"
               for a in output["result"]["artifacts"] if a["role"] == "structure")


def test_the_chosen_index_is_reported_and_not_guessed_from_the_file_text():
    """같은 본문이 두 번 오면 파일 대조로는 어느 것을 골랐는지 알 수 없다.

    채점 스크립트가 선택 지점을 되찾으려고 본문을 비교하면 첫 번째를 집어
    신뢰도·점수를 잘못 붙인다. 선택을 계산한 쪽이 인덱스를 돌려줘야 한다.
    """
    from logic.flow import select_structure

    same = {"structures": [{"structure": "data_x\n#\n"}, {"structure": "data_x\n#\n"}],
            "confidence_scores": [0.10, 0.90]}
    assert select_structure(same) == (1, [0.10, 0.90])
    assert select_structure({"structures": [], "confidence_scores": [0.9]}) == (None, [])
    assert select_structure({"structures": [{"structure": " "}, {"structure": "data_y\n#\n"}],
                             "confidence_scores": "nope"}) == (1, [None, None])


def test_a_predicted_structure_is_compared_against_the_reference_interface(tmp_path):
    """예측 구조에는 기준 계면과의 겹침 근거가 따라붙어야 한다."""
    response = {"structures": [{"structure": "data_pred\n#\n"}], "confidence_scores": [0.5]}
    output, _ = run_flow(make_request(_prediction_candidates(), tmp_path),
                         client=StubClient(response=response))
    predicted = {s["structure_id"] for s in output["result"]["structures"] if s["kind"] == "predicted"}
    assert predicted
    topics = {e["topic"] for e in output["result"]["evidence"] if e["structure_id"] in predicted}
    assert "predicted_epitope_overlap_with_reference" in topics
