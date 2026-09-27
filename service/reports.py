"""Download the same saved run/result snapshot; never synthesize measurements."""
import csv
import io
import json

from fastapi import Response

from logic.contract import validate


def report_response(run: dict, result: dict, format: str) -> Response:
    validate(run, "Run")
    validate(result, "Result")
    if any(run[key] != result[key] for key in ("run_id", "review_id", "data_mode", "settings_version")):
        raise ValueError("보고서와 실행이 일치하지 않습니다.")
    if format == "json":
        content = json.dumps({"run": run, "result": result}, ensure_ascii=False, indent=2).encode()
        media = "application/json"
    elif format == "csv":
        stream = io.StringIO(newline="")
        columns = ["run_id", "schema_version", "settings_version", "data_mode", "run_status",
                   "record_type", "candidate_id", "condition_id", "topic", "measurement_state",
                   "value", "unit", "decision", "reason", "record_json"]
        writer = csv.DictWriter(stream, fieldnames=columns)
        writer.writeheader()
        for kind, records in [("run", [run]), ("candidate", run["candidates"]),
                              *[(key, result[key]) for key in ("structures", "conditions", "evidence", "opinions", "artifacts")]]:
            for record in records:
                row = {key: run[key] for key in ("run_id", "schema_version", "settings_version", "data_mode")}
                row.update(run_status=run["status"], record_type=kind,
                           record_json=json.dumps(record, ensure_ascii=False, separators=(",", ":")))
                row.update({key: record.get(key) for key in columns[6:-1]})
                # Spreadsheet applications must not execute user-supplied formulas.
                writer.writerow({key: "'" + value if isinstance(value, str) and value.lstrip().startswith(("=", "+", "-", "@")) else value
                                 for key, value in row.items()})
        content = stream.getvalue().encode("utf-8-sig")
        media = "text/csv"
    else:
        raise ValueError("지원하지 않는 보고서 형식입니다.")
    return Response(content, media_type=media, headers={"Cache-Control": "no-store",
        "X-Content-Type-Options": "nosniff", "Content-Disposition": f'attachment; filename="report.{format}"'})
