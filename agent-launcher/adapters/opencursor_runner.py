"""OpenCursor worker runner（evaluate 模式，2026-10-18 接入）。

契约：prompt 经 stdin（UTF-8）；--model 模型名；--cwd 卡工作区。
流程：
  1. 卡工作区无 .git 则 git init + 全量基线提交（worker 需要 repositories+revision）。
  2. 生成 .opencursor/worker.json + tasks.json（apiBaseUrl=方舟 OpenAI 兼容端点，
     apiKey 经 OPENCURSOR_API_KEY 环境变量注入，不落盘）。
  3. node dist/worker.cjs evaluate ...；agent 在 jobs/<id>/workspace 的
     pinned clone 里干活，最终产物 REPORT.md。
  4. 判分器（opencursor_grader.cjs）检 REPORT.md ≥200 字节。
  5. 收尾：把 workspace/REPORT.md 与 changes.patch 路径写回卡工作区，
     生成 report.md 摘要；全部 outcome=passed 退出 0，否则退出 1。

OpenCursor = Pawan Osman 社区复刻（MIT），与 Cursor 厂商 Anysphere 无关。
"""
from __future__ import annotations

import argparse
import io
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

DEPLOY = Path(r"~\Documents\Codex\2026-10-17\glm-5-3-flash-0-5\outputs\SHOW_R15\R15C\R15C-TOOL03\deploy\OpenCursor-main")
WORKER_CJS = DEPLOY / "dist" / "worker.cjs"
RESPONSES_BRIDGE = Path(os.environ.get("CARD_GATEWAY_SCRIPT", str(Path(__file__).with_name("minimax_responses_bridge_upstream.py"))))
GRADER = Path(__file__).with_name("opencursor_grader.cjs")
NODE = r"C:\Program Files\nodejs\node.exe"

TASK_SUFFIX = (
    "\n\n---\n硬性收尾要求：把全部工作成果整理成一份 REPORT.md 写在当前工作目录"
    "（仓库根目录），少于 200 字节视为未交付；只写半成品也可以，但必须有实质内容。"
)


def _free_port() -> int:
    import socket
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _wait_healthy(proc: subprocess.Popen, url: str, model: str, seconds: float = 20.0) -> None:
    import time
    import urllib.request
    deadline = time.monotonic() + seconds
    last_error: Exception | None = None
    while time.monotonic() < deadline:
        if proc.poll() is not None:
            raise RuntimeError("MiniMax Responses bridge exited before becoming healthy")
        try:
            with urllib.request.urlopen(url, timeout=0.8) as response:
                data = json.loads(response.read())
                if data.get("ok"):
                    return
                last_error = ValueError("bridge health payload did not report ok")
        except Exception as exc:
            last_error = exc
            time.sleep(0.2)
    detail = f"; last probe error: {type(last_error).__name__}" if last_error else ""
    raise TimeoutError("MiniMax Responses bridge health check timed out" + detail)


def git(cwd: Path, *args: str) -> str:
    r = subprocess.run(["git", *args], cwd=str(cwd), capture_output=True, text=True,
                       encoding="utf-8", errors="replace", timeout=120)
    if r.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)}: {r.stderr.strip()[:300]}")
    return r.stdout.strip()


def ensure_repo(cwd: Path) -> str:
    if not (cwd / ".git").exists():
        git(cwd, "init", "-q")
    for k, v in (("user.name", "card-runner"), ("user.email", "card-runner@local")):
        subprocess.run(["git", "config", k, v], cwd=str(cwd), capture_output=True)
    # .opencursor 是 runner 自身产物（jobs workspace 深嵌套），绝不进基线，否则自我嵌套克隆
    gi = cwd / ".gitignore"
    lines = gi.read_text(encoding="utf-8", errors="replace").splitlines() if gi.exists() else []
    if ".opencursor/" not in lines:
        gi.write_text("\n".join(lines + [".opencursor/"]), encoding="utf-8")
    subprocess.run(["git", "rm", "-r", "-q", "--cached", ".opencursor"],
                   cwd=str(cwd), capture_output=True)
    # 上轮的 stale 交付物必须从基线剔除（文件与索引都清），否则判分器被旧 REPORT.md 骗过（空过）
    for stale in ("REPORT.md", "report.md"):
        subprocess.run(["git", "rm", "-q", "--cached", "--ignore-unmatch", stale],
                       cwd=str(cwd), capture_output=True)
        try:
            (cwd / stale).unlink()
        except OSError:
            pass
    git(cwd, "add", "-A")
    r = subprocess.run(["git", "commit", "-q", "-m", "card baseline", "--allow-empty"],
                       cwd=str(cwd), capture_output=True, text=True, encoding="utf-8", errors="replace")
    if r.returncode != 0 and "nothing to commit" not in (r.stdout + r.stderr):
        raise RuntimeError("baseline commit failed: " + (r.stderr or r.stdout)[:300])
    return git(cwd, "rev-parse", "HEAD")


def _taskbook_inputs(prompt_text: str, cwd: Path) -> list[Path]:
    r"""从任务书文本里抽「只读输入」引用的文件（相对 cwd 的路径）。

    只认带明确扩展名的相对路径（如 probe\probe_input.md），
    绝对路径与目录不抽（避免把整个项目拖进来）。
    """
    found: list[Path] = []
    seen: set[str] = set()
    # 形如 `probe\probe_input.md` 或 `probe/probe_input.md` 的反引号内相对路径
    for raw in re.findall(r"`([^`\n]{2,160})`", prompt_text):
        token = raw.strip()
        if not token or token.startswith(("http", "<", "{")):
            continue
        if os.path.isabs(token) or ":" in token:
            continue
        if not re.search(r"\.(md|txt|csv|json|jsonl|py)$", token, re.IGNORECASE):
            continue
        if " " in token and not token.endswith((".md", ".txt")):
            continue
        rel = token.replace("/", os.sep)
        target = (cwd / rel)
        if target.is_file() and str(rel).lower() not in seen:
            seen.add(str(rel).lower())
            found.append(target)
    return found


def _make_isolated(cwd: Path, cfg: Path, prompt_text: str) -> tuple[Path, list[Path]]:
    """建隔离工作区，只放任务书引用的输入文件；返回 (工作区, 复制的输入列表)。"""
    inputs = _taskbook_inputs(prompt_text, cwd)
    iso = cfg / "isolated"
    iso.mkdir(parents=True, exist_ok=True)
    copied: list[Path] = []
    for src_file in inputs:
        try:
            rel = src_file.relative_to(cwd)
        except ValueError:
            continue
        dst = iso / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src_file, dst)
        copied.append(dst)
    return iso, copied


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", required=True)
    ap.add_argument("--cwd", required=True)
    args = ap.parse_args()
    cwd = Path(args.cwd).resolve()
    prompt_text = sys.stdin.read()

    cfg = cwd / ".opencursor"
    (cfg / "jobs").mkdir(parents=True, exist_ok=True)

    # 隔离工作区（2026-10-22）：CR 通道会把工作区整个 clone 给 agent。
    # 若工作区是整个项目（300+ 文件），agent 会一头扎进项目级分析，
    # 实测 19 轮工具调用 40 万 token 零产物。改成只给任务书引用的输入文件。
    isolate = os.environ.get("CARD_OPEN_CURSOR_ISOLATE", "1") != "0"
    work_root = cwd
    iso_copied: list[Path] = []
    if isolate:
        iso_root, iso_copied = _make_isolated(cwd, cfg, prompt_text)
        if iso_copied:
            work_root = iso_root
            print("[cr] 隔离工作区 %s（只含 %d 个输入文件）" % (work_root, len(iso_copied)), flush=True)
        else:
            print("[cr] 未识别到输入文件，退回整目录工作区", flush=True)

    base_rev = ensure_repo(work_root)

    # 2026-10-22：改走本地 MiniMax Responses 桥。
    #   旧路径：直连方舟 Agent Plan（ARK 密钥来自 secret.json），协议是 chat/completions。
    #   新路径：本地 Responses 桥对外提供 chat/completions，对内改打 MiniMax 原生
    #   /v1/responses（function tools / streaming / reasoning.effort 均实测可用）。
    #   真实 MiniMax 密钥只存在桥进程内存（从 Pi 的 models.json 读），OPENCURSOR_API_KEY
    #   只放占位串，桥不校验。旧的 ARK secret.json 不再是本通道的依赖。
    port = _free_port()
    bridge_env = dict(os.environ)
    bridge_env["CARD_USAGE_FILE"] = str(
        Path(cwd) / ".card_usage" / ("usage_pid%d_cr.jsonl" % os.getpid()))
    bridge_env["CARD_USAGE_CHANNEL"] = "opencursor"
    bridge_env.update({
        "MINIMAX_RESP_HOST": "127.0.0.1",
        "MINIMAX_RESP_PORT": str(port),
        "CARD_GATEWAY_PORT": str(port),
        "MINIMAX_RESP_TIMEOUT": "300",
        "CARD_LAUNCHER_MODEL": args.model,
        "PI_MODELS_JSON": str(Path.home() / ".pi" / "agent" / "models.json"),
    })
    # 桥的输出必须落文件：出问题时（比如上游断连、协议不匹配）只有日志能定位。
    bridge_log_path = cfg / "bridge.log"
    bridge_log = io.open(bridge_log_path, "w", encoding="utf-8")
    bridge = subprocess.Popen(
        [sys.executable, str(RESPONSES_BRIDGE)], cwd=str(cwd), env=bridge_env,
        stdin=subprocess.DEVNULL, stdout=bridge_log, stderr=subprocess.STDOUT,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    try:
        _wait_healthy(bridge, f"http://127.0.0.1:{port}/health", args.model)
        return _run_worker(cwd, cfg, args.model, prompt_text, port, base_rev, work_root)
    finally:
        if bridge.poll() is None:
            bridge.terminate()
            try:
                bridge.wait(timeout=3)
            except subprocess.TimeoutExpired:
                bridge.kill()


def _run_worker(cwd: Path, cfg: Path, model: str, prompt_text: str, port: int, base_rev: str,
                work_root: Path) -> int:
    api_base = f"http://127.0.0.1:{port}/v1"

    # 2026-10-22 实测修正：tokenBudget 400000 不够。
    #   CRU4 在 436682 tokens 时报 "goal token budget exhausted before tool execution"，
    #   后续所有工具调用被拒 → outcome=failed（不是协议问题，也不是超时）。
    #   缓存命中占 91%+ 时，累计 token 会远大于实际计费量，必须留足余量。
    token_budget = int(os.environ.get("CARD_OPEN_CURSOR_TOKEN_BUDGET", "4000000"))
    max_steps = int(os.environ.get("CARD_OPEN_CURSOR_MAX_STEPS", "200"))
    worker_json = {
        "directory": str(cfg / "jobs"),
        "repositories": {"task": str(work_root)},
        "models": [model],
        "apiBaseUrl": api_base,
        "execution": {"kind": "local"},
        "maxTokens": 16384,
        "contextTokens": 128000,
        "tokenBudget": token_budget,
        "maxSteps": max_steps,
        "timeoutMs": 5400000,
    }
    tasks_json = [{
        "name": f"CR card task {cwd.name}",
        "split": "development",
        "repository": "task",
        "revision": base_rev,
        "model": model,
        "prompt": prompt_text + TASK_SUFFIX,
        "grader": {"executable": NODE, "args": [str(GRADER)], "timeoutMs": 60000},
    }]
    wpath, tpath, rpath = cfg / "worker.json", cfg / "tasks.json", cfg / "report.json"
    io.open(wpath, "w", encoding="utf-8").write(json.dumps(worker_json, ensure_ascii=False, indent=1))
    io.open(tpath, "w", encoding="utf-8").write(json.dumps(tasks_json, ensure_ascii=False, indent=1))

    env = dict(os.environ)
    env["OPENCURSOR_API_KEY"] = "local-bridge"
    env["OPENCURSOR_TRUSTED_LOCAL_WORKER"] = "1"
    # 回搬范围限定：只搬本次运行新建的 job 工作区（历史 job 的 workspace 可能含旧基线全量文件，
    # 全搬一遍会把几百个未改动文件的 mtime 刷新到当前窗口，污染台账「产出层」判据）。
    jobs_dir = cfg / "jobs"
    jobs_root_pre = set()
    if jobs_dir.exists():
        jobs_root_pre = {p.name for p in jobs_dir.iterdir() if p.is_dir()}
    cmd = [NODE, str(WORKER_CJS), "evaluate", str(wpath), str(tpath), str(rpath)]
    log_path = cfg / "runner.log"
    with io.open(log_path, "w", encoding="utf-8") as log:
        proc = subprocess.run(cmd, cwd=str(DEPLOY), env=env, stdout=log, stderr=subprocess.STDOUT)

    outcomes, tokens_used, details = [], [], []
    if rpath.exists():
        rep = json.load(io.open(rpath, encoding="utf-8"))
        for res in rep.get("results", []):
            outcomes.append(res.get("outcome"))
            details.append(f"{res.get('name')}: {res.get('outcome')} — {str(res.get('details'))[:300]}")
            if res.get("tokensUsed"):
                tokens_used.append(res["tokensUsed"])

    report_md = ["# CR 卡运行报告（OpenCursor evaluate）", "",
                 f"- model: {model}", f"- worker exit: {proc.returncode}",
                 f"- outcomes: {outcomes or 'NO REPORT'}", f"- tokensUsed: {tokens_used or '未计量'}", ""]
    report_md += ["## 判分详情"] + [f"- {d}" for d in details] or []
    # 搬运产物：整个 workspace（基线 clone + agent 修改）回写卡工作区（workspace 即 cwd 基线+差异）
    # 隔离工作区里的输入文件要跳过：它们是原样复制的，搬回去只污染 mtime。
    input_rel_set: set[str] = set()
    iso_root = cfg / "isolated"
    if work_root == iso_root and iso_root.is_dir():
        for p in iso_root.rglob("*"):
            if p.is_file():
                input_rel_set.add(str(p.relative_to(iso_root)).replace("\\", "/"))
    jobs_root = cfg / "jobs"
    copied = None
    if jobs_root.exists():
        for job in jobs_root.iterdir():
            if job.name in jobs_root_pre:
                continue
            ws = job / "workspace"
            if not ws.exists():
                continue
            for src in ws.rglob("*"):
                if not src.is_file() or ".git" in src.parts:
                    continue
                rel = src.relative_to(ws)
                # 隔离工作区里，输入文件是原样复制的；搬回去没有意义，
                # 而且会覆盖原文件（虽然内容相同，但会刷新 mtime，污染产物 mtime 口径）。
                if str(rel).replace("\\", "/") in input_rel_set:
                    continue
                dst = cwd / rel
                dst.parent.mkdir(parents=True, exist_ok=True)
                blob = src.read_bytes()
                try:
                    if dst.exists() and dst.read_bytes() == blob:
                        continue  # 内容没变：不重写，避免刷新 mtime 污染产出层判据
                except OSError:
                    pass
                dst.write_bytes(blob)
            copied = str(ws)
            if (job / "changes.patch").exists():
                report_md.append(f"- changes.patch: {job / 'changes.patch'}")
    if copied:
        report_md.append(f"- REPORT.md 已从 {copied} 搬回卡工作区")
    # Windows 大小写不敏感：runner 摘要不得占用 agent 交付的 REPORT.md 名字
    io.open(cwd / ".opencursor" / "runner-report.md", "w", encoding="utf-8").write("\n".join(report_md) + "\n")

    ok = outcomes and all(o == "passed" for o in outcomes)
    print(json.dumps({"ok": bool(ok), "outcomes": outcomes, "worker_exit": proc.returncode}))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
