import csv
import io
import json
from pathlib import Path

import pytest

from service.reports import report_response


@pytest.mark.parametrize("scenario", ["completed", "scientific-hold", "partial"])
def test_report_preserves_snapshot_and_unmeasured_values(scenario):
    fixture = json.loads(Path("service/mock_scenarios.json").read_text())
    frame = next(item for item in fixture["scenarios"] if item["name"] == scenario)
    run, result = frame["run"], frame["result"]
    result["evidence"][0]["reason"] = "=unsafe spreadsheet formula"
    response = report_response(run, result, "json")
    assert json.loads(response.body) == {"run": run, "result": result}
    rows = list(csv.DictReader(io.StringIO(report_response(run, result, "csv").body.decode("utf-8-sig"))))
    assert {r["run_status"] for r in rows} == {run["status"]}
    evidence = next(r for r in rows if r["record_type"] == "evidence")
    assert evidence["value"] == ""
    assert evidence["reason"].startswith("'=unsafe")
    assert json.loads(evidence["record_json"]) == result["evidence"][0]
    assert len([r for r in rows if r["record_type"] == "opinions"]) == len(result["opinions"])
