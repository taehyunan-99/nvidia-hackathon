"""Boundary between the persistent service and the replaceable analysis process."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import time
from pathlib import Path

from logic.contract import SCHEMA_VERSION, validate

from .db import connect


def request_for_job(dsn: str, job: dict, data_root: Path) -> dict:
    root = data_root.resolve()
    with connect(dsn) as conn:
        uploads = conn.execute(
            "SELECT u.upload_key, u.relative_path, u.sha256, u.size_bytes FROM uploads u "
            "JOIN runs r ON r.review_id = u.review_id WHERE r.id = %s ORDER BY u.upload_key",
            (job["id"],),
        ).fetchall()
    local_uploads = []
    for upload in uploads:
        path = (root / upload["relative_path"]).resolve()
        if not path.is_relative_to(root / "uploads") or not path.is_file():
            raise ValueError("업로드 파일 경로가 유효하지 않습니다.")
        content = path.read_bytes()
        if len(content) != upload["size_bytes"] or hashlib.sha256(content).hexdigest() != upload["sha256"]:
            raise ValueError("업로드 파일 무결성이 맞지 않습니다.")
        local_uploads.append({"upload_key": upload["upload_key"], "path": str(path), "sha256": upload["sha256"]})
    work_dir = root / "runs" / job["id"]
    work_dir.mkdir(parents=True, exist_ok=True)
    request = {
        "schema_version": SCHEMA_VERSION,
        "run_id": job["id"],
        "review_id": job["state"]["review_id"],
        "input": job["input"],
        "settings_version": job["state"]["settings_version"],
        "work_dir": str(work_dir),
        "uploads": local_uploads,
        "data_mode": "live",
    }
    validate(request, "LogicRequest")
    return request


def run_process(request: dict, progress, alive) -> dict:
    timeout = int(os.environ.get("ANALYSIS_TIMEOUT_SECONDS", "1200"))
    if timeout <= 0:
        raise ValueError("ANALYSIS_TIMEOUT_SECONDS must be positive")
    started = time.monotonic()
    work_dir = Path(request["work_dir"])
    request_path = work_dir / "request.json"
    output_path = work_dir / "output.json"
    progress_path = work_dir / "progress.jsonl"
    request_path.write_text(json.dumps(request, ensure_ascii=False), encoding="utf-8")
    with (work_dir / "stderr.log").open("w", encoding="utf-8") as stderr:
        process = subprocess.Popen(
            [sys.executable, "-m", "logic.run", "--request", str(request_path), "--out", str(output_path), "--progress", str(progress_path)],
            stdout=subprocess.DEVNULL, stderr=stderr,
        )
        offset = 0
        pending = ""
        try:
            while True:
                if time.monotonic() - started >= timeout:
                    raise TimeoutError("분석 실행 시간 제한을 넘었습니다.")
                if not alive():
                    raise InterruptedError("작업 점유권 또는 세션이 종료되었습니다.")
                # Observe exit before reading so the final flushed events are drained.
                returncode = process.poll()
                if progress_path.exists():
                    with progress_path.open(encoding="utf-8") as stream:
                        stream.seek(offset)
                        pending += stream.read()
                        offset = stream.tell()
                    lines = pending.split("\n")
                    pending = lines.pop()
                    for line in lines:
                        if line:
                            update = json.loads(line)
                            validate(update, "ProgressUpdate")
                            progress(update)
                if returncode is not None:
                    break
                time.sleep(1)
            if pending.strip():
                update = json.loads(pending)
                validate(update, "ProgressUpdate")
                progress(update)
            if process.returncode != 0 or not output_path.is_file():
                raise RuntimeError(f"분석 프로세스가 종료 코드 {process.returncode}로 실패했습니다.")
            output = json.loads(output_path.read_text(encoding="utf-8"))
            validate(output, "LogicOutput")
            return output
        finally:
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait()


def verified_files(output: dict, work_dir: Path) -> list[tuple[str, Path, bytes]]:
    """Resolve declared files, current predicted output, or a verified public catalog file."""
    ready = {item["artifact_id"]: item for item in output["result"]["artifacts"] if item["status"] == "ready"}
    declared = {item["artifact_id"]: item["path"] for item in output["files"]}
    artifact_ids = [item["artifact_id"] for item in output["result"]["artifacts"]]
    if len(set(artifact_ids)) != len(artifact_ids) or len(declared) != len(output["files"]) or set(declared) - set(ready):
        raise ValueError("산출물 목록이 결과와 일치하지 않습니다.")
    files = []
    root = work_dir.resolve()
    experimental = {
        structure["artifact_id"]: structure["source"].get("record_id")
        for structure in output["result"]["structures"] if structure["kind"] == "experimental"
    }
    for artifact_id, artifact in ready.items():
        if Path(artifact_id).name != artifact_id or artifact_id in {".", ".."}:
            raise ValueError("산출물 식별자에 경로 문자가 있습니다.")
        given = Path(declared.get(artifact_id, root / artifact["file_name"]))
        source = (given if given.is_absolute() else root / given).resolve()
        if artifact_id in declared and not source.is_relative_to(root):
            raise ValueError("산출물 파일이 실행 폴더 밖에 있습니다.")
        if not source.is_relative_to(root) or not source.is_file():
            public = None
            if artifact_id not in declared and artifact_id in experimental:
                from logic.structures import load_catalog
                public = load_catalog().get(experimental[artifact_id])
            if not public or public.path.name != artifact["file_name"]:
                raise ValueError("산출물 파일이 실행 폴더 밖에 있거나 없습니다.")
            source = public.path.resolve()
            if not source.is_file() or hashlib.sha256(source.read_bytes()).hexdigest() != public.verified_sha256:
                raise ValueError("공개 산출물 파일 무결성이 맞지 않습니다.")
        content = source.read_bytes()
        if len(content) != artifact["size_bytes"] or hashlib.sha256(content).hexdigest() != artifact["sha256"]:
            raise ValueError("산출물 파일 무결성이 맞지 않습니다.")
        files.append((artifact_id, source, content))
    return files
