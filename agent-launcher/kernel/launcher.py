"""Windows process launcher helpers for the card launcher."""

import ctypes
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path
from ctypes import wintypes


_WINDOWS_PATH_LIMIT = 7800
_REQUIRED_CHILD_COMMANDS = (
    "node", "codex", "claude", "opencode", "rg", "git",
    "pwsh", "powershell", "npm",
)


def _child_environment(env: dict | None = None) -> dict:
    """Return a child environment with a Windows PATH safe for shell lookup.

    Codex's shell runner can fail to resolve commands near the end of a long
    inherited PATH. Keep the directories for the configured card CLIs and the
    basic shell tools first, then retain as many remaining entries as fit.
    """
    child = dict(os.environ if env is None else env)
    if os.name != "nt":
        return child

    raw_path = child.get("PATH", "")
    if len(raw_path) <= _WINDOWS_PATH_LIMIT:
        return child

    required_dirs: list[str] = []
    for name in _REQUIRED_CHILD_COMMANDS:
        executable = shutil.which(name, path=raw_path)
        if executable:
            required_dirs.append(os.path.dirname(os.path.abspath(executable)))
    for executable in (sys.executable,):
        if executable:
            required_dirs.append(os.path.dirname(os.path.abspath(executable)))
    system_root = child.get("SystemRoot") or child.get("WINDIR")
    if system_root:
        required_dirs.extend([os.path.join(system_root, "System32"), system_root])

    def key(value: str) -> str:
        return os.path.normcase(os.path.normpath(value.strip().strip('"')))

    original = [item for item in raw_path.split(os.pathsep) if item]
    required_keys = {key(item) for item in required_dirs}
    prioritized = [item for item in original if key(item) in required_keys]
    prioritized_keys = {key(item) for item in prioritized}
    prioritized.extend(item for item in required_dirs if key(item) not in prioritized_keys)

    selected: list[str] = []
    selected_keys: set[str] = set()
    for item in prioritized + original:
        item_key = key(item)
        if item_key in selected_keys:
            continue
        candidate = os.pathsep.join(selected + [item])
        if len(candidate) > _WINDOWS_PATH_LIMIT:
            if item_key in required_keys:
                raise OSError("required card CLI paths exceed the safe Windows PATH limit")
            continue
        selected.append(item)
        selected_keys.add(item_key)

    child["PATH"] = os.pathsep.join(selected)
    return child


def _spawn(argv: list[str], cwd: str, stdin_text: str | None, log_path: str,
           env: dict | None = None) -> subprocess.Popen:
    """Start argv in the background with output appended to log_path."""
    stdin = subprocess.PIPE if stdin_text is not None else subprocess.DEVNULL
    child_env = _child_environment(env)
    with open(log_path, "ab", buffering=0) as log_file:
        process = subprocess.Popen(
            [sys.executable, str(Path(__file__).with_name("process_runner.py")), *argv],
            cwd=cwd,
            stdin=stdin,
            stdout=log_file,
            stderr=subprocess.STDOUT,
            env=child_env,
            # 2026-10-09 集成期修正：DETACHED_PROCESS 会让 npm .CMD shim（codex/opencode）
            # 静默 0 字节退出；改 CREATE_NO_WINDOW，子进程照旧无窗口、可后台常驻。
            # 实测：DETACHED 下 `codex --version` 输出为空；NO_WINDOW 正常。
            creationflags=subprocess.CREATE_NO_WINDOW | subprocess.CREATE_NEW_PROCESS_GROUP,
        )

        if stdin_text is not None:
            try:
                process.stdin.write(stdin_text.encode("utf-8"))
            except BrokenPipeError:
                pass
            finally:
                try:
                    process.stdin.close()
                except BrokenPipeError:
                    pass

    return process


def launch(argv: list[str], cwd: str, stdin_text: str | None, log_path: str,
           env: dict | None = None) -> int:
    """Start argv in the background, append its output to log_path, and return its PID."""
    return _spawn(argv, cwd, stdin_text, log_path, env).pid


def probe_alive(pid: int, wait_sec: float = 10.0) -> bool:
    """Wait for the requested interval, then check whether the process is alive."""
    time.sleep(wait_sec)
    return is_alive_now(pid)


def stop_tree(pid: int) -> str:
    """Stop a process and its descendants with taskkill."""
    try:
        result = subprocess.run(
            ["taskkill", "/PID", str(pid), "/T", "/F"],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
    except OSError:
        return "finished" if not is_alive_now(pid) else "stop_failed"

    if result.returncode == 0:
        return "stopped"
    return "finished" if not is_alive_now(pid) else "stop_failed"


def is_alive_now(pid: int) -> bool:
    """Check process liveness with OpenProcess and GetExitCodeProcess."""
    if pid <= 0:
        return False

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.OpenProcess.argtypes = (wintypes.DWORD, wintypes.BOOL, wintypes.DWORD)
    kernel32.OpenProcess.restype = wintypes.HANDLE
    kernel32.GetExitCodeProcess.argtypes = (
        wintypes.HANDLE,
        ctypes.POINTER(wintypes.DWORD),
    )
    kernel32.GetExitCodeProcess.restype = wintypes.BOOL
    kernel32.CloseHandle.argtypes = (wintypes.HANDLE,)
    kernel32.CloseHandle.restype = wintypes.BOOL

    handle = kernel32.OpenProcess(0x1000, False, pid)
    if not handle:
        return False

    try:
        exit_code = wintypes.DWORD()
        if not kernel32.GetExitCodeProcess(handle, ctypes.byref(exit_code)):
            return False
        return exit_code.value == 259
    finally:
        kernel32.CloseHandle(handle)


def _log_size(path: str) -> int:
    try:
        return os.path.getsize(path)
    except OSError:
        return 0


def probe_survived(proc: subprocess.Popen, log_path: str, grace_sec: float = 3.0,
                   probe_sec: float = 25.0) -> bool:
    """Return True when the launched CLI really got going.

    2026-10-09 A3 集成期修正（探针语义两次兑付，终版）：
      * v1 `probe_alive(pid, N)` = 睡 N 秒再看活不活。对**跑得快的卡**误判：
        卡在 N 秒前已完工退出 → 被当成启动失败（A3 实测：10 秒完成的卡在 probe_sec=25
        下被判死，整条链误报 failed）。
      * 第一版修正（“日志有产出即算成功”）也错：坏模型（`opencode/definitely-not-a-model`）
        1.8s 退出、**exit code=1**、写 167 字节错误 JSON → 被当成成功了。
      * 终版**以退出码为准**：
          存活 ≥ grace_sec        → True（立刻返回，不必等满窗口）
          在 grace_sec 内退出     → 仅当 exit code == 0 才算成功；
                                  非 0（含 npm shim 静默退出）算失败，触发回退
          窗口用尽仍在跑          → True
    """
    started = time.time()
    deadline = started + max(probe_sec, grace_sec)
    while True:
        elapsed = time.time() - started
        code = proc.poll()
        if code is None:
            if elapsed >= grace_sec:
                return True
        else:
            return code == 0
        if time.time() >= deadline:
            return proc.poll() is None or proc.poll() == 0
        time.sleep(0.5)


def launch_chain(make_argv, candidates: list[str], cwd: str,
                 stdin_text: str | None, log_path: str,
                 env: dict | None = None, probe_sec: float = 25.0,
                 grace_sec: float = 3.0) -> dict:
    """Launch candidates in order and return the first process that survives probing."""
    attempts = []

    for model in candidates:
        try:
            argv = make_argv(model)
        except Exception:
            attempts.append({"model": model, "ok": False, "pid": None})
            continue

        proc = _spawn(argv, cwd, stdin_text, log_path, env)
        ok = probe_survived(proc, log_path, grace_sec, probe_sec)
        attempts.append({"model": model, "ok": ok, "pid": proc.pid})
        if ok:
            return {
                "status": "running",
                "model_used": model,
                "pid": proc.pid,
                "attempts": attempts,
                "log_path": log_path,
            }

    return {
        "status": "failed",
        "model_used": None,
        "pid": None,
        "attempts": attempts,
        "log_path": log_path,
    }


if __name__ == "__main__":
    if not is_alive_now(os.getpid()):
        raise SystemExit("launcher self-test failed")

    test_commands = {
        "dead-first": ["cmd.exe", "/c", "exit 1"],
        "alive-second": ["cmd.exe", "/c", "ping -n 30 127.0.0.1"],
        "dead-final": ["cmd.exe", "/c", "exit 1"],
    }
    test_pids = []

    def remember_pids(result: dict) -> None:
        test_pids.extend(
            attempt["pid"]
            for attempt in result["attempts"]
            if attempt["pid"] is not None
        )

    try:
        switched = launch_chain(
            lambda model: test_commands[model],
            ["dead-first", "alive-second"],
            os.getcwd(), None, os.devnull, probe_sec=0.3,
        )
        remember_pids(switched)
        assert switched["status"] == "running"
        assert switched["model_used"] == "alive-second"
        assert [item["ok"] for item in switched["attempts"]] == [False, True]

        all_dead = launch_chain(
            lambda model: test_commands[model],
            ["dead-first", "dead-final"],
            os.getcwd(), None, os.devnull, probe_sec=0.3,
        )
        remember_pids(all_dead)
        assert all_dead["status"] == "failed"
        assert all_dead["model_used"] is None
        assert all_dead["pid"] is None
        assert len(all_dead["attempts"]) == 2
        assert all(not item["ok"] for item in all_dead["attempts"])

        def make_argv_with_error(model: str) -> list[str]:
            if model == "argv-error":
                raise ValueError("intentional self-test error")
            return test_commands[model]

        argv_error = launch_chain(
            make_argv_with_error,
            ["argv-error", "alive-second"],
            os.getcwd(), None, os.devnull, probe_sec=0.3,
        )
        remember_pids(argv_error)
        assert argv_error["status"] == "running"
        assert argv_error["attempts"][0] == {
            "model": "argv-error", "ok": False, "pid": None,
        }
        assert argv_error["model_used"] == "alive-second"
    finally:
        cleanup_failures = []
        for pid in reversed(test_pids):
            result = stop_tree(pid)
            if result == "stop_failed":
                deadline = time.monotonic() + 35.0
                while is_alive_now(pid) and time.monotonic() < deadline:
                    time.sleep(0.1)
                if not is_alive_now(pid):
                    stop_tree(pid)
            if is_alive_now(pid):
                cleanup_failures.append(pid)
        if cleanup_failures:
            raise AssertionError(f"launcher self-test cleanup failed: {cleanup_failures}")

    print("OK")
