"""JSONL snapshot registry for launched cards."""

from datetime import datetime
from contextlib import contextmanager
import json
import os
import tempfile
import threading
import time


_LOCAL_LOCK = threading.RLock()


@contextmanager
def _registry_lock(registry_path: str):
    """Serialize registry snapshots across threads and MCP server processes.

    Multiple client hosts (or direct stdio callers) can launch cards at once.
    A temporary-file replace alone is atomic but does not protect the read/modify/
    write sequence, and Windows may reject concurrent replacements with WinError 5.
    """
    absolute = os.path.abspath(registry_path)
    directory = os.path.dirname(absolute)
    os.makedirs(directory, exist_ok=True)
    lock_path = absolute + ".lock"
    with _LOCAL_LOCK:
        with open(lock_path, "a+b") as lock_file:
            lock_file.seek(0, os.SEEK_END)
            if lock_file.tell() == 0:
                lock_file.write(b"\0")
                lock_file.flush()
            deadline = time.monotonic() + 30.0
            locked = False
            while not locked:
                lock_file.seek(0)
                try:
                    if os.name == "nt":
                        import msvcrt
                        msvcrt.locking(lock_file.fileno(), msvcrt.LK_NBLCK, 1)
                    else:
                        import fcntl
                        fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                    locked = True
                except OSError:
                    if time.monotonic() >= deadline:
                        raise TimeoutError(f"timed out locking card registry: {absolute}")
                    time.sleep(0.05)
            try:
                yield
            finally:
                lock_file.seek(0)
                if os.name == "nt":
                    msvcrt.locking(lock_file.fileno(), msvcrt.LK_UNLCK, 1)
                else:
                    fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)


def _read_records(registry_path: str) -> list[dict]:
    records = []
    try:
        with open(registry_path, "r", encoding="utf-8") as source:
            for line in source:
                if line.strip():
                    records.append(json.loads(line))
    except FileNotFoundError:
        pass
    return records


def _write_records(registry_path: str, records: list[dict]) -> None:
    directory = os.path.dirname(os.path.abspath(registry_path))
    temporary_path = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", newline="\n", dir=directory,
            prefix=".registry-", suffix=".tmp", delete=False
        ) as temporary:
            temporary_path = temporary.name
            for item in records:
                temporary.write(json.dumps(item, ensure_ascii=False, separators=(",", ":")))
                temporary.write("\n")
            temporary.flush()
            os.fsync(temporary.fileno())
        os.replace(temporary_path, registry_path)
    finally:
        if temporary_path is not None and os.path.exists(temporary_path):
            os.unlink(temporary_path)


def _upsert_locked(registry_path: str, record: dict) -> None:
    card_id = record["card_id"]
    records = _read_records(registry_path)
    replacement_index = None
    for index, existing in enumerate(records):
        if existing.get("card_id") == card_id:
            replacement_index = index
    if replacement_index is None:
        records.append(record)
    else:
        records[replacement_index] = record
        records = [
            item for index, item in enumerate(records)
            if item.get("card_id") != card_id or index == replacement_index
        ]
    _write_records(registry_path, records)


def new_card_id(show_slug: str, group_slug: str, n: int) -> str:
    """Return a card ID using today's date and a two-digit card number."""
    return f"{datetime.now().strftime('%Y%m%d')}-{show_slug}-{group_slug}-C{n:02d}"


def upsert(registry_path: str, record: dict) -> None:
    """Replace the record with the same card_id under a cross-process lock."""
    with _registry_lock(registry_path):
        _upsert_locked(registry_path, record)


def get(registry_path: str, card_id: str) -> dict | None:
    """Return the matching snapshot record, or None when absent."""
    with _registry_lock(registry_path):
        for record in _read_records(registry_path):
            if record.get("card_id") == card_id:
                return record
    return None


def all_records(registry_path: str) -> list[dict]:
    """Return the latest snapshot per card_id.

    The registry is upsert-appended: earlier lines keep their historical status,
    so a naive read makes a long-finished card look like it is still running.
    Later lines win, which is what upsert() guarantees.
    Added 2026-10-10 alongside the list_cards MCP tool.
    """
    latest: dict[str, dict] = {}
    with _registry_lock(registry_path):
        try:
            with open(registry_path, "r", encoding="utf-8") as source:
                for line in source:
                    if not line.strip():
                        continue
                    try:
                        record = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    card_id = record.get("card_id")
                    if isinstance(card_id, str) and card_id:
                        latest[card_id] = record
        except FileNotFoundError:
            return []
    return list(latest.values())


def is_running(registry_path: str, card_id: str) -> bool:
    """Return whether the card exists in a starting or running state."""
    record = get(registry_path, card_id)
    return record is not None and record.get("status") in {"starting", "running"}


def validate(record: dict) -> list[str]:
    """Return field-level violations against the CardRecord contract."""
    violations = []
    required = (
        "card_id", "vehicle", "model", "effort", "taskbook", "pid",
        "timestamp", "attempt", "status", "updated_at", "command",
    )
    for field in required:
        if field not in record:
            violations.append(f"missing required field: {field}")

    for field in ("card_id", "vehicle", "model", "effort", "taskbook", "status"):
        if field in record and (not isinstance(record[field], str) or not record[field].strip()):
            violations.append(f"{field} must be a non-empty string")

    if "vehicle" in record and (
        not isinstance(record["vehicle"], str)
        or record["vehicle"] not in {"codex", "opencode", "claude", "ollama", "cline", "copilot", "trae", "agy", "kimi", "mcode", "zcode", "opencursor", "grok"}
    ):
        violations.append("vehicle must be codex, opencode, claude, ollama, cline, copilot, trae, agy, kimi, mcode, zcode, opencursor, or grok")

    if "status" in record and (
        not isinstance(record["status"], str)
        or record["status"] not in {
            "starting", "running", "finished", "failed", "stopped", "stop_failed"
        }
    ):
        violations.append("status is not a supported card status")

    pid = record.get("pid")
    status = record.get("status")
    if "pid" in record:
        if status == "starting":
            if pid is not None:
                violations.append("pid must be null when status is starting")
        elif isinstance(status, str) and status in {"running", "finished", "stopped", "stop_failed"}:
            if isinstance(pid, bool) or not isinstance(pid, int) or pid <= 0:
                violations.append(f"pid must be a positive integer when status is {status}")
        elif pid is not None and (isinstance(pid, bool) or not isinstance(pid, int) or pid <= 0):
            violations.append("pid must be null or a positive integer")

    if "attempt" in record and (
        isinstance(record["attempt"], bool)
        or not isinstance(record["attempt"], int)
        or record["attempt"] < 1
    ):
        violations.append("attempt must be a positive integer")

    if "command" in record and (
        not isinstance(record["command"], list)
        or any(not isinstance(part, str) for part in record["command"])
    ):
        violations.append("command must be a list of strings")

    for field in ("timestamp", "updated_at", "finished_at", "stopped_at"):
        if field not in record:
            continue
        value = record[field]
        if field in {"finished_at", "stopped_at"} and value is None:
            continue
        if not isinstance(value, str):
            violations.append(f"{field} must be an ISO8601 string")
            continue
        try:
            datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            violations.append(f"{field} must be an ISO8601 string")

    if "error" in record and record["error"] is not None and not isinstance(record["error"], str):
        violations.append("error must be a string when provided")

    return violations


def set_status(registry_path: str, card_id: str, status: str, **fields) -> dict | None:
    """Update an existing card record and atomically persist the snapshot."""
    with _registry_lock(registry_path):
        records = _read_records(registry_path)
        record_index = None
        for index, record in enumerate(records):
            if record.get("card_id") == card_id:
                record_index = index
        if record_index is None:
            return None

        updated_record = dict(records[record_index])
        updated_record.update(fields)
        updated_record["card_id"] = card_id
        updated_record["status"] = status
        updated_record["updated_at"] = datetime.now().astimezone().isoformat()
        _upsert_locked(registry_path, updated_record)
        return updated_record


def finalize_record(registry_path: str, card_id: str,
                    exit_code: int | None, seconds: float | None,
                    result: str) -> dict | None:
    """Set a card's terminal status and the matching terminal timestamp."""
    if result not in ("finished", "failed", "stopped", "stop_failed"):
        raise ValueError(f"unsupported final result: {result!r}")

    timestamp_field = "finished_at" if result in {"finished", "failed"} else "stopped_at"
    fields = {
        "exit": exit_code,
        "seconds": seconds,
        timestamp_field: datetime.now().astimezone().isoformat(),
    }
    return set_status(registry_path, card_id, result, **fields)


if __name__ == "__main__":
    import tempfile

    sample = {
        "card_id": new_card_id("kernel", "G1", 1),
        "vehicle": "codex",
        "model": "gpt-6-luna",
        "effort": "xhigh",
        "taskbook": "tb/T1.md",
        "pid": None,
        "timestamp": "2026-10-09T12:00:00+08:00",
        "attempt": 1,
        "status": "starting",
        "updated_at": "2026-10-09T12:00:00+08:00",
        "command": ["codex", "exec"],
    }
    assert validate(sample) == []
    with tempfile.TemporaryDirectory() as temporary_directory:
        path = os.path.join(temporary_directory, "cards_registry.jsonl")
        upsert(path, sample)
        assert get(path, sample["card_id"]) == sample
        assert is_running(path, sample["card_id"])
        sample["status"] = "finished"
        sample["pid"] = 12345
        upsert(path, sample)
        assert get(path, sample["card_id"]) == sample
        assert not is_running(path, sample["card_id"])

        status_record = set_status(
            path, sample["card_id"], "running", pid=54321, error="status updated"
        )
        assert status_record is not None
        assert status_record["status"] == "running"
        assert status_record["pid"] == 54321
        assert status_record["error"] == "status updated"
        assert isinstance(status_record["updated_at"], str)
        assert get(path, sample["card_id"]) == status_record

        for result in ("finished", "failed", "stopped", "stop_failed"):
            record = {
                **sample,
                "card_id": f"finalize-{result}",
                "status": "running",
                "updated_at": "2026-10-09T12:00:00+08:00",
            }
            upsert(path, record)
            final_record = finalize_record(path, record["card_id"], 0, 1.5, result)
            assert final_record is not None
            assert final_record["status"] == result
            assert isinstance(final_record["updated_at"], str)
            timestamp_field = "finished_at" if result in {"finished", "failed"} else "stopped_at"
            assert isinstance(final_record[timestamp_field], str)
            assert final_record["exit"] == 0
            assert final_record["seconds"] == 1.5
            assert get(path, record["card_id"]) == final_record

        with open(path, "r", encoding="utf-8") as source:
            record_count = len(source.readlines())
        assert set_status(path, "missing-card", "finished") is None
        assert finalize_record(path, "missing-card", None, None, "finished") is None
        with open(path, "r", encoding="utf-8") as source:
            assert len(source.readlines()) == record_count
    print("OK")
