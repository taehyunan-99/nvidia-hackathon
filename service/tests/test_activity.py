"""Activity survives polling/reconnect and cannot overwrite workflow state."""
from copy import deepcopy

import pytest
from fastapi.testclient import TestClient

from logic.contract import now_rfc3339
from service.operational import create_app
from service.tests.test_live import DSN, live_service
from service.tests.test_operational import review
from service.worker import claim, save_progress, fail_live


def test_activity_is_private_bounded_idempotent_and_preserved_on_failure(live_service):
    client, root = live_service
    review_id = review(client)
    run_id = client.post(f"/api/reviews/{review_id}/runs", json={"request_key": "activity"}).json()["run_id"]
    owner = "activity-worker"
    job = claim(DSN, owner, mode="live")
    assert job["id"] == run_id
    before = client.get(f"/api/runs/{run_id}").json()["candidates"]
    update = {"schema_version": "0.1.0", "run_id": run_id, "candidate_id": before[0]["candidate_id"],
              "step_id": "prediction", "status": "completed", "reason": None, "updated_at": now_rfc3339(),
              "activity": {"event_id": "one", "kind": "tool", "name": "predict_structure", "phase": "running", "actor": "agent"}}
    assert not save_progress(DSN, run_id, "wrong-owner", update)
    assert save_progress(DSN, run_id, owner, update)
    assert save_progress(DSN, run_id, owner, update)
    state = client.get(f"/api/runs/{run_id}").json()
    assert state["candidates"] == before
    assert state["activity_events"] == [update]
    wrong = deepcopy(update)
    wrong["candidate_id"] = "foreign-candidate"
    with pytest.raises(ValueError):
        save_progress(DSN, run_id, owner, wrong)
    wrong["run_id"] = "foreign-run"
    with pytest.raises(ValueError):
        save_progress(DSN, run_id, owner, wrong)
    for index in range(201):
        update["activity"]["event_id"] = f"event-{index}"
        assert save_progress(DSN, run_id, owner, update)
    assert fail_live(DSN, run_id, owner, "검사 중단")
    with TestClient(create_app(DSN, root, mode="live")) as restarted:
        restarted.cookies.update(client.cookies)
        state = restarted.get(f"/api/runs/{run_id}").json()
        assert state["status"] == "failed"
        assert len(state["activity_events"]) == 200
        assert state["activity_events"][0]["activity"]["event_id"] == "event-1"
        assert state["activity_events"][-1]["activity"]["event_id"] == "event-200"
    with TestClient(create_app(DSN, root, mode="live")) as stranger:
        stranger.post("/api/session")
        assert stranger.get(f"/api/runs/{run_id}").status_code == 404


def test_process_exit_drains_final_activity_before_finishing(tmp_path, monkeypatch):
    import json
    from pathlib import Path
    from service import live

    result = json.loads(Path("docs/frontend-hosting/fixtures/scenarios.json").read_text())["scenarios"]
    result = next(frame["result"] for frame in result if frame["result"])
    update = {"schema_version": "0.1.0", "run_id": result["run_id"], "candidate_id": result["candidate_ids"][0],
              "step_id": "reporting", "status": "completed", "reason": None, "updated_at": now_rfc3339(),
              "activity": {"event_id": "last", "kind": "tool", "name": "submit_opinion", "phase": "completed", "actor": "agent"}}

    class ExitingProcess:
        returncode = 0

        def poll(self):
            # The child writes its final event immediately before the parent sees exit.
            (tmp_path / "progress.jsonl").write_text(json.dumps(update) + "\n")
            (tmp_path / "output.json").write_text(json.dumps({"result": result, "files": []}))
            return 0

    monkeypatch.setattr(live.subprocess, "Popen", lambda *args, **kwargs: ExitingProcess())
    received = []
    live.run_process({"work_dir": str(tmp_path)}, received.append, lambda: True)
    assert received == [update]
