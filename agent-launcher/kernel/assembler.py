"""Load card profiles and assemble prompts according to CONTRACT.md."""

import json
from pathlib import Path


def load_profiles(lib_root: str) -> dict:
    """Load and return the complete profiles.json object."""
    with (Path(lib_root) / "profiles.json").open(encoding="utf-8") as profiles_file:
        return json.load(profiles_file)


def _resolve_profile_id(data: dict, profile_id: str) -> str:
    aliases = data.get("id_aliases", {})
    resolved = profile_id
    seen: set[str] = set()
    while isinstance(aliases, dict) and resolved in aliases:
        if resolved in seen:
            raise ValueError(f"profile alias cycle: {profile_id}")
        seen.add(resolved)
        target = aliases[resolved]
        if not isinstance(target, str) or not target:
            raise ValueError(f"invalid profile alias target for {resolved}")
        resolved = target
    return resolved


def resolve_profile_id(lib_root: str, profile_id: str) -> str:
    """Resolve a profile alias to its canonical id, rejecting alias cycles."""
    return _resolve_profile_id(load_profiles(lib_root), profile_id)


def aliases_for_profile(lib_root: str, profile_id: str) -> list[str]:
    """Return aliases that resolve to one active canonical profile id."""
    data = load_profiles(lib_root)
    aliases = data.get("id_aliases", {})
    if not isinstance(aliases, dict):
        return []
    found = []
    for alias in aliases:
        try:
            if _resolve_profile_id(data, alias) == profile_id:
                found.append(alias)
        except (ValueError, TypeError):
            continue
    return sorted(found)


def get_profile(lib_root: str, profile_id: str) -> dict:
    """Return one active profile by canonical id or alias, else raise KeyError."""
    data = load_profiles(lib_root)
    canonical_id = _resolve_profile_id(data, profile_id)
    for profile in data["profiles"]:
        if profile.get("id") == canonical_id:
            return profile
    raise KeyError(profile_id)


def role_prompt_path(lib_root: str, profile_id: str) -> str:
    """Return the absolute role-specific system prompt path."""
    role = get_profile(lib_root, profile_id)["role"]
    filename = {
        "U": "SYSTEM_PROMPT.md",
        "L": "L_SYSTEM_PROMPT.md",
        "B": "B_SYSTEM_PROMPT.md",
    }[role]
    return str((Path(lib_root) / filename).resolve())


def base_skill_path(lib_root: str, profile_id: str) -> str:
    """Return the absolute path to the role's required base skill."""
    role = get_profile(lib_root, profile_id)["role"]
    skill_name = {
        "U": "workflow-harness",
        "B": "daybreaker",
        "L": "deep-search",
    }[role]
    library_skill = Path(lib_root) / "skills" / skill_name / "SKILL.md"
    if library_skill.is_file():
        return str(library_skill.resolve())
    return str(
        (Path(r"~\.agents\skills") / skill_name / "SKILL.md").resolve()
    )


_CLI_CHANNELS = {
    "Codex CLI": "Use the Codex CLI's own shell and file tools available in this session. Do not call a card-launcher MCP. If this profile explicitly sets local_exec_mcp=true, use only mcp__card_local_exec__exec_command for local commands.",
    "Claude Code": "Use Claude Code's native terminal and file tools available in this session.",
    "Claude Code via MiniMax Bridge": "Use Claude Code's native terminal and file tools available in this session. The MiniMax bridge supplies the model only; it does not provide tools.",
    "Claude Code via OpenRouter Bridge": "Use Claude Code's native terminal and file tools available in this session. The OpenRouter bridge supplies the model only; it does not provide tools.",
    "OpenCode CLI": "Use OpenCode's native terminal and file tools available in this session.",
    "Ollama": "This is a model-only local channel; no agent tool interface is supplied.",
    "Cline CLI": "Use Cline's native terminal and file tools available in this session.",
    "GitHub Copilot CLI": "Use GitHub Copilot CLI's native terminal and file tools available in this session.",
    "TRAE CLI": "Use TRAE CLI's native terminal and file tools available in this session.",
    "Antigravity CLI": "Use Antigravity CLI's native terminal and file tools available in this session. The MiniMax bridge supplies the model only; it does not provide tools.",
    "OpenCursor Worker": "Work inside the task workspace using OpenCursor's built-in file and shell tools. Your final deliverable must be a REPORT.md written at the workspace root. This channel runs the community OpenCursor worker (Pawan Osman, MIT), not official Cursor.",
    "Antigravity SDK Wrapper": "Use the Antigravity SDK's enabled file tools available in this session. This profile runs the Antigravity SDK wrapper over the local MiniMax bridge, not the original agy.exe.",
    "Grok Build CLI": "Use Grok Build's native terminal and file tools available in this session. Use the assigned working directory and leave a report with evidence.",
}


def _channel_notice(profile: dict) -> str:
    cli = profile.get("cli")
    channel = _CLI_CHANNELS.get(cli, "Use the command and file tools provided by your current agent CLI.")
    if cli == "Codex CLI" and profile.get("local_exec_mcp") is True:
        channel = "Use only mcp__card_local_exec__exec_command for local commands; do not use built-in shell tools."
    return (
        "# AVAILABLE CHANNELS (authoritative)\n\n"
        + channel
        + "\n\nThe orchestrator's card-launcher MCP is not available to this card. "
        "Do not call list_profiles, launch_card, check_status, collect_report, or stop_card.\n"
        "If a needed tool is missing, state the exact limitation and continue with work the available tools can do.\n"
    )


def assemble(
    lib_root: str,
    profile_id: str,
    task_text: str,
    extra_paths: list[str] | None = None,
    profile_override: dict | None = None,
) -> str:
    """Assemble the role prompt, shared index, skill paths, and task text."""
    profile = profile_override or get_profile(lib_root, profile_id)
    channel_notice = _channel_notice(profile)
    if profile.get("supervisor"):
        role_prompt = (Path(lib_root) / "U_SUPERVISOR_SYSTEM_PROMPT.md").read_text(encoding="utf-8")
        return role_prompt + "\n\nUse the scoped card-launcher MCP installed for this act.\n\n# TASK\n" + task_text
    base_prompt = profile.get("base_prompt", "role")
    if base_prompt != "role" and base_prompt != "none":
        raise ValueError(
            "base_prompt must be either 'role' or 'none'; "
            f"got {base_prompt!r}"
        )

    if base_prompt == "none":
        prompt = (
            "# NO ROLE PROMPT (bare card)\n"
            "This card runs without a role system prompt or base skill. Follow the task text exactly; "
            "the deliverable path and evidence requirements stated in it are binding."
            "\n\n" + channel_notice
        )
        if extra_paths:
            prompt += "\n\n# EXTRA MATERIALS\n" + "\n".join(extra_paths)
        return prompt + "\n\n# TASK\n" + task_text

    role_prompt = Path(role_prompt_path(lib_root, profile_id)).read_text(
        encoding="utf-8"
    ).rstrip("\r\n")
    knowledge_index = str((Path(lib_root) / "knowledge" / "INDEX.md").resolve())
    skill_path = base_skill_path(lib_root, profile_id)

    prompt = (
        "# ROLE SYSTEM PROMPT\n"
        + role_prompt
        + "\n\n# SHARED KNOWLEDGE INDEX (read on demand)\n"
        + knowledge_index
        + "\n\n# BASE SKILL (read before work)\n"
        + skill_path
        + "\n\n"
        + channel_notice
    )
    if extra_paths:
        prompt += "\n\n# EXTRA MATERIALS\n" + "\n".join(extra_paths)
    return prompt + "\n\n# TASK\n" + task_text


if __name__ == "__main__":
    import tempfile

    with tempfile.TemporaryDirectory() as temp_root:
        root = Path(temp_root)
        profiles = {
            "profiles": [
                {"id": "U-TEST", "role": "U"},
                {"id": "L-TEST", "role": "L"},
                {"id": "B-TEST", "role": "B"},
                {"id": "U-ROLE-TEST", "role": "U", "base_prompt": "role"},
                {"id": "BARE-TEST", "role": "NOT-USED", "base_prompt": "none"},
                {"id": "BAD-TEST", "role": "U", "base_prompt": "unexpected"},
            ]
        }
        (root / "profiles.json").write_text(
            json.dumps(profiles), encoding="utf-8"
        )
        (root / "knowledge").mkdir()
        (root / "knowledge" / "INDEX.md").write_text("index", encoding="utf-8")
        for role, filename, skill_name in (
            ("U", "SYSTEM_PROMPT.md", "workflow-harness"),
            ("L", "L_SYSTEM_PROMPT.md", "deep-search"),
            ("B", "B_SYSTEM_PROMPT.md", "daybreaker"),
        ):
            (root / filename).write_text(f"{role} role\n", encoding="utf-8")
            skill_file = root / "skills" / skill_name / "SKILL.md"
            skill_file.parent.mkdir(parents=True)
            skill_file.write_text("skill", encoding="utf-8")

        assert load_profiles(str(root)) == profiles
        assert get_profile(str(root), "U-TEST") == profiles["profiles"][0]
        for profile_id, filename in (
            ("U-TEST", "SYSTEM_PROMPT.md"),
            ("L-TEST", "L_SYSTEM_PROMPT.md"),
            ("B-TEST", "B_SYSTEM_PROMPT.md"),
        ):
            assert Path(role_prompt_path(str(root), profile_id)).name == filename
        assert Path(base_skill_path(str(root), "U-TEST")).name == "SKILL.md"

        assembled = assemble(
            str(root), "U-TEST", "Do the work.", ["first.md", "second.md"]
        )
        expected = (
            "# ROLE SYSTEM PROMPT\nU role"
            + "\n\n# SHARED KNOWLEDGE INDEX (read on demand)\n"
            + str((root / "knowledge" / "INDEX.md").resolve())
            + "\n\n# BASE SKILL (read before work)\n"
            + base_skill_path(str(root), "U-TEST")
            + "\n\n# EXTRA MATERIALS\nfirst.md\nsecond.md"
            + "\n\n# TASK\nDo the work."
        )
        assert assembled == expected

        explicit_role = assemble(str(root), "U-ROLE-TEST", "Same role behavior.")
        assert explicit_role.startswith("# ROLE SYSTEM PROMPT\nU role")
        assert "# SHARED KNOWLEDGE INDEX (read on demand)\n" in explicit_role
        assert "# BASE SKILL (read before work)\n" in explicit_role

        bare_task = "Write exactly this.\nKeep the second line."
        bare = assemble(
            str(root), "BARE-TEST", bare_task, ["payload.txt", "evidence.md"]
        )
        bare_expected = (
            "# NO ROLE PROMPT (bare card)\n"
            "This card runs without a role system prompt or base skill. Follow the task text exactly; "
            "the deliverable path and evidence requirements stated in it are binding."
            "\n\n# EXTRA MATERIALS\npayload.txt\nevidence.md"
            "\n\n# TASK\n"
            + bare_task
        )
        assert bare == bare_expected
        assert "# ROLE SYSTEM PROMPT" not in bare
        assert "# SHARED KNOWLEDGE INDEX" not in bare
        assert "# BASE SKILL" not in bare

        try:
            assemble(str(root), "BAD-TEST", "This should fail.")
        except ValueError as error:
            assert "'role' or 'none'" in str(error)
        else:
            raise AssertionError("invalid base_prompt must raise ValueError")

        print("OK")
