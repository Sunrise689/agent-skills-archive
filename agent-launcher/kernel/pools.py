"""Load model pools and resolve their ordered candidates."""

import json
import os
import tempfile
from datetime import datetime


def load_pools(path: str) -> dict:
    """Load a pool mapping from a UTF-8 JSON file."""
    with open(path, "r", encoding="utf-8") as stream:
        value = json.load(stream)
    if not isinstance(value, dict):
        raise ValueError("pools file must contain a JSON object")
    return value


def load_overrides(path: str) -> dict:
    """Load a pool override mapping from a UTF-8 JSON file."""
    with open(path, "r", encoding="utf-8") as stream:
        value = json.load(stream)
    if not isinstance(value, dict):
        raise ValueError("overrides file must contain a JSON object")
    return value


def resolve(pool_name: str, profile_default: str, pools: dict,
            overrides: dict) -> list[str]:
    """Return candidates using force, pool with deny, then default priority."""
    override = overrides.get(pool_name, {})
    if "force" in override:
        return [override["force"]]

    candidates = pools.get(pool_name, [])
    denied = set(override.get("deny", []))
    resolved = [candidate for candidate in candidates if candidate not in denied]
    return resolved or [profile_default]


def load_probe_cache(path: str) -> dict:
    """Load a probe cache, returning an empty cache if it is missing or damaged."""
    try:
        with open(path, "r", encoding="utf-8") as stream:
            value = json.load(stream)
    except (OSError, UnicodeError, json.JSONDecodeError):
        return {"generated_at": None, "models": {}}

    if not isinstance(value, dict) or not isinstance(value.get("models"), dict):
        return {"generated_at": None, "models": {}}
    return value


def save_probe_cache(path: str, cache: dict) -> None:
    """Write a probe cache atomically, creating its parent directory if needed."""
    parent = os.path.dirname(os.path.abspath(path))
    os.makedirs(parent, exist_ok=True)

    temporary_path = None
    try:
        with tempfile.NamedTemporaryFile(
                mode="w", encoding="utf-8", dir=parent,
                prefix=f".{os.path.basename(path)}.", suffix=".tmp",
                delete=False) as stream:
            temporary_path = stream.name
            json.dump(cache, stream, ensure_ascii=False, indent=2)
            stream.write("\n")
        os.replace(temporary_path, path)
    finally:
        if temporary_path is not None and os.path.exists(temporary_path):
            os.unlink(temporary_path)


def resolve_chain(pool_name: str, profile_default: str, pools: dict,
                  overrides: dict, probe_cache: dict | None = None) -> list[str]:
    """Return pool candidates with denied and failed models ordered by contract."""
    override = overrides.get(pool_name, {})
    force = override.get("force")
    if force is not None:
        return [force]

    candidates = pools.get(pool_name, [])
    denied = set(override.get("deny", []))
    resolved = [candidate for candidate in candidates if candidate not in denied]
    if not resolved:
        resolved = [profile_default]

    if probe_cache is None:
        return resolved

    models = probe_cache.get("models", {})
    if not isinstance(models, dict):
        return resolved
    ready = [candidate for candidate in resolved
             if not (isinstance(models.get(candidate), dict)
                     and models[candidate].get("ok") is False)]
    failed = [candidate for candidate in resolved
              if isinstance(models.get(candidate), dict)
              and models[candidate].get("ok") is False]
    return ready + failed


def record_attempt(cache: dict, model: str, ok: bool, latency: float | None,
                   checked_at: str | None = None) -> dict:
    """Return a copied cache with the latest result for one model."""
    updated_cache = dict(cache)
    models = dict(updated_cache.get("models", {}))
    models[model] = {
        "ok": bool(ok),
        "latency": latency,
        "checked_at": checked_at or datetime.now().astimezone().isoformat(),
    }
    updated_cache["models"] = models
    return updated_cache


if __name__ == "__main__":
    assert resolve("cc-free", "default", {"cc-free": ["a", "b"]},
                   {"cc-free": {"force": "x", "deny": ["a"]}}) == ["x"]
    assert resolve("cc-free", "default", {"cc-free": ["a", "b"]},
                   {"cc-free": {"deny": ["a"]}}) == ["b"]
    assert resolve("cc-free", "default", {"cc-free": ["a"]},
                   {"cc-free": {"deny": ["a"]}}) == ["default"]
    assert resolve("missing", "default", {}, {}) == ["default"]

    assert resolve_chain(
        "pool", "default", {"pool": ["a", "b", "c", "d"]}, {},
        {"models": {"a": {"ok": True}, "b": {"ok": False},
                    "d": {"ok": False}}}) == ["a", "c", "b", "d"]
    assert resolve_chain(
        "pool", "default", {"pool": ["a", "b"]},
        {"pool": {"force": "forced", "deny": ["a", "b"]}},
        {"models": {"forced": {"ok": False}}}) == ["forced"]
    assert resolve_chain(
        "pool", "default", {"pool": ["a"]},
        {"pool": {"force": None, "deny": ["a"]}}) == ["default"]
    assert resolve_chain(
        "pool", "default", {"pool": ["a", "b"]}, {}, None) == ["a", "b"]

    empty_cache = {"generated_at": None, "models": {}}
    assert load_probe_cache(__file__ + ".missing") == empty_cache
    assert load_probe_cache(__file__) == empty_cache

    with tempfile.TemporaryDirectory() as directory:
        cache_path = os.path.join(directory, "nested", "probe_cache.json")
        save_probe_cache(cache_path, empty_cache)
        assert load_probe_cache(cache_path) == empty_cache

    original_cache = {"generated_at": None, "models": {"old": {"ok": True}}}
    updated_cache = record_attempt(original_cache, "new", False, None, "fixed-time")
    assert updated_cache is not original_cache
    assert updated_cache["models"] is not original_cache["models"]
    assert updated_cache["models"]["new"] == {
        "ok": False, "latency": None, "checked_at": "fixed-time"}
    assert "new" not in original_cache["models"]
    generated_attempt = record_attempt({}, "model", True, 1.2)
    datetime.fromisoformat(generated_attempt["models"]["model"]["checked_at"])
    print("OK")
