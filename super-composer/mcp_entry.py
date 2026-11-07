import sys
from server import handle_line

for line in sys.stdin:
    if not line.strip():
        continue
    try:
        out = handle_line(line)
    except Exception as exc:
        out = {"jsonrpc":"2.0","id":None,"error":{"code":-32603,"message":type(exc).__name__+": "+str(exc)}}
    sys.stdout.write(__import__('json').dumps(out, ensure_ascii=False)+"\n")
    sys.stdout.flush()
