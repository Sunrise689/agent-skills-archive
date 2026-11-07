"""Deterministic model routing; original profile IDs remain stable."""
DEFAULT_MODEL = "MiniMax-M3.1-Flash"
DEFAULT_FREE_MODEL = "openrouter/nvidia/nemotron-3-ultra-550b-a55b:free"

def resolve(profile: dict, model: str) -> tuple[dict, str, str]:
    effective = dict(profile)
    selected = model.strip()
    reason = "profile_cli"
    if profile.get("universal_provider"):
        from adapters.provider_config import resolve as supplier_config
        supplier = supplier_config(selected)
        effective["supplier"] = supplier["name"]
        effective["upstream_api"] = supplier["api"]
        effective["model"] = selected
        return effective, selected, "selected_cli_configured_supplier"
    if profile.get("provider") == "opencursor-worker":
        effective["model"] = selected
        return effective, selected, "opencursor_worker_pinned"
    if profile.get("provider") == "ark-agent-plan":
        effective["model"] = selected
        return effective, selected, "ark_agent_plan"
    # One-profile exception: preserve Claude Code for the pinned free model.
    # All existing profiles continue through the historical routing below.
    if profile.get("id") in ("CC-U-OR-free", "CC-U-OR-free-nemotron"):
        if selected != profile.get("model"):
            raise ValueError("CC OpenRouter profile accepts only its pinned free model")
        effective["cli"] = "Claude Code via OpenRouter Bridge"
        effective["fallback_candidates"] = []
        effective["model"] = selected
        return effective, selected, "cc_or_free_pinned"
    is_free = selected.endswith(":free") or selected.endswith("-free")
    if is_free:
        effective["cli"] = "OpenCode CLI"
        if selected.endswith(":free") and not selected.startswith(("openrouter/", "opencode/")):
            selected = "openrouter/" + selected
        elif "/" not in selected and selected.endswith("-free"):
            selected = "opencode/" + selected
        reason = "free_model_uses_oc"
    elif selected.startswith("gpt-6"):
        effective["cli"] = "Codex CLI"
        effective["local_exec_mcp"] = False
        reason = "native_codex_override"
    elif "/" in selected and not selected.startswith("minimax-token-plan/"):
        effective["cli"] = "OpenCode CLI"
        reason = "qualified_provider_uses_oc"
    if selected.startswith("minimax-token-plan/") and effective.get("cli") != "OpenCode CLI":
        selected = selected.split("/", 1)[1]
    if effective.get("cli") == "OpenCode CLI" and selected.startswith("MiniMax-"):
        selected = "minimax-token-plan/" + selected
    effective["model"] = selected
    return effective, selected, reason
