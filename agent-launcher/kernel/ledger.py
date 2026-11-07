"""Append-only JSONL execution ledger."""

import json
import os
from datetime import datetime


def append(ledger_path: str, entry: dict) -> None:
    """Append exactly one UTF-8 JSON object line to the ledger."""
    directory = os.path.dirname(os.path.abspath(ledger_path))
    os.makedirs(directory, exist_ok=True)
    with open(ledger_path, "a", encoding="utf-8", newline="\n") as ledger:
        ledger.write(json.dumps(entry, ensure_ascii=False, separators=(",", ":")))
        ledger.write("\n")
        ledger.flush()
        os.fsync(ledger.fileno())


def read_all(ledger_path: str) -> list[dict]:
    """Read all nonblank JSONL records; return an empty list if absent."""
    try:
        with open(ledger_path, "r", encoding="utf-8") as ledger:
            return [json.loads(line) for line in ledger if line.strip()]
    except FileNotFoundError:
        return []


def finalize(ledger_path: str, card_id: str, exit_code: int | None,
             seconds: float | None, result: str) -> None:
    """Append one terminal record without changing the ledger history."""
    if result not in ("finished", "failed", "stopped", "stop_failed"):
        raise ValueError(f"unsupported final result: {result!r}")

    append(ledger_path, {
        "ts": datetime.now().astimezone().isoformat(),
        "card_id": card_id,
        "exit": exit_code,
        "seconds": seconds,
        "result": result,
        "final": True,
    })


def latest_by_card(ledger_path: str) -> dict[str, dict]:
    """Return the last ledger record for each card ID."""
    latest = {}
    for record in read_all(ledger_path):
        card_id = record.get("card_id")
        if isinstance(card_id, str):
            latest[card_id] = record
    return latest


if __name__ == "__main__":
    import tempfile

    with tempfile.TemporaryDirectory() as temporary_directory:
        path = os.path.join(temporary_directory, "ledger.jsonl")
        entry = {"ts": "2026-10-09T12:00:00+08:00", "card_id": "test-C01", "result": "finished"}
        assert read_all(path) == []
        assert latest_by_card(path) == {}
        append(path, entry)
        append(path, {**entry, "card_id": "test-C02"})
        assert read_all(path) == [entry, {**entry, "card_id": "test-C02"}]
        before_finalize = read_all(path)
        finalize(path, "test-C01", 0, 1.25, "finished")
        after_finalize = read_all(path)
        assert len(after_finalize) == len(before_finalize) + 1
        assert after_finalize[:len(before_finalize)] == before_finalize
        assert after_finalize[-1]["final"] is True
        assert after_finalize[-1]["exit"] == 0
        assert after_finalize[-1]["seconds"] == 1.25
        datetime.fromisoformat(after_finalize[-1]["ts"])
        assert latest_by_card(path)["test-C01"] == after_finalize[-1]
        assert latest_by_card(path)["test-C01"]["result"] == "finished"
    print("OK")
