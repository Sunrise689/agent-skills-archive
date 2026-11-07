"""Preserve child exit codes in card logs, including clients that fail silently."""
import json
import subprocess
import sys

def main():
    try:
        prompt = sys.stdin.buffer.read()
        process = subprocess.Popen(sys.argv[1:], stdin=subprocess.PIPE, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        process.communicate(prompt)
        code = process.returncode
    except Exception as exc:
        print(json.dumps({"card_process_error": type(exc).__name__}), flush=True)
        code = 1
    print(json.dumps({"card_process_exit": code}), flush=True)
    return code

if __name__ == "__main__":
    raise SystemExit(main())
