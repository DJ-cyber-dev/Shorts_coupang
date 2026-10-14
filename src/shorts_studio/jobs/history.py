"""Small atomic job ledger for recovery and retry after application restarts."""
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
from uuid import uuid4
from urllib.parse import parse_qs, urlencode, urlsplit, urlunsplit

from shorts_studio.core.engine import cleanup_stale_workdirs
from shorts_studio.providers.settings import settings_path


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class JobHistory:
    def __init__(self, directory: Path | None = None, *, max_records: int = 100):
        self.directory = Path(directory) if directory else settings_path().parent / "jobs"
        self.max_records = max_records
        if not 1 <= max_records <= 1000:
            raise ValueError("max_records must be 1~1000")

    def create(self, *, kind: str, source: str, output: str = "") -> dict:
        if not re.fullmatch(r"[a-z][a-z0-9_-]{0,39}", kind):
            raise ValueError("invalid job kind")
        source = str(source)
        if "://" in source:
            parsed = urlsplit(source)
            query = urlencode({"v": parse_qs(parsed.query).get("v", [""])[0]}) if parsed.hostname in {"youtube.com", "www.youtube.com", "m.youtube.com"} and parsed.path == "/watch" and parse_qs(parsed.query).get("v") else ""
            source = urlunsplit((parsed.scheme, parsed.hostname or "", parsed.path, query, ""))
        record = {
            "id": uuid4().hex,
            "kind": kind,
            "source": source[:2000],
            "output": str(output)[:2000],
            "status": "running",
            "stage": "starting",
            "progress": 0.0,
            "created_at": _now(),
            "updated_at": _now(),
            "error": "",
        }
        self._write(record)
        self._prune()
        return record

    def update(self, job_id: str, **changes) -> dict:
        allowed = {"status", "stage", "progress", "error", "output"}
        if changes.keys() - allowed:
            raise ValueError("unknown job fields")
        path = self._path(job_id)
        record = json.loads(path.read_text(encoding="utf-8"))
        if "status" in changes and changes["status"] not in {"running", "completed", "failed", "cancelled", "interrupted"}:
            raise ValueError("invalid job status")
        if "progress" in changes:
            value = float(changes["progress"])
            if not 0 <= value <= 1:
                raise ValueError("progress must be between 0 and 1")
            changes["progress"] = value
        for key, value in changes.items():
            record[key] = str(value)[:2000] if key in {"stage", "error", "output"} else value
        record["updated_at"] = _now()
        self._write(record)
        return record

    def list_recent(self, limit: int = 100) -> list[dict]:
        if not 1 <= limit <= 1000:
            raise ValueError("invalid job history limit")
        self.directory.mkdir(parents=True, exist_ok=True)
        records = []
        for path in self.directory.glob("job-*.json"):
            try:
                record = json.loads(path.read_text(encoding="utf-8"))
                if isinstance(record, dict) and record.get("id") == path.stem.removeprefix("job-"):
                    records.append(record)
            except (OSError, ValueError):
                continue
        return sorted(records, key=lambda row: row.get("updated_at", ""), reverse=True)[:limit]

    def reconcile_running(self) -> int:
        recovered = 0
        for record in self.list_recent(self.max_records):
            if record.get("status") == "running":
                output = record.get("output")
                if output:
                    try:
                        parent = Path(output).expanduser().parent
                        cleanup_stale_workdirs(parent)
                    except (OSError, ValueError):
                        pass
                self.update(record["id"], status="interrupted", stage="app_closed")
                recovered += 1
        return recovered

    def _path(self, job_id: str) -> Path:
        if not re.fullmatch(r"[a-f0-9]{32}", job_id):
            raise ValueError("invalid job id")
        return self.directory / f"job-{job_id}.json"

    def _write(self, record: dict):
        self.directory.mkdir(parents=True, exist_ok=True)
        path = self._path(record["id"])
        temporary = path.with_suffix(".tmp")
        temporary.write_text(json.dumps(record, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        os.replace(temporary, path)

    def _prune(self):
        files = sorted(self.directory.glob("job-*.json"), key=lambda item: item.stat().st_mtime, reverse=True)
        for path in files[self.max_records:]:
            path.unlink(missing_ok=True)
