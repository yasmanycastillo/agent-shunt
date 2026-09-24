#!/usr/bin/env python3
"""MCP protocol benchmark: spawn the real model-shunt stdio server with an
expanded sandbox, run initialize + tools/call bulk_read, time it, save output."""
import json, os, subprocess, sys, time

server = os.path.expanduser("~/src/model-shunt/src/model_shunt/server.py")
env = dict(os.environ)
env["SHUNT_ALLOWED_ROOTS"] = os.path.expanduser("~/src")
env["SHUNT_MODEL"] = "auto"

def call(proc, mid, method, params):
    req = json.dumps({"jsonrpc": "2.0", "id": mid, "method": method, "params": params}) + "\n"
    proc.stdin.write(req)
    proc.stdin.flush()
    return json.loads(proc.stdout.readline())

proc = subprocess.Popen([sys.executable, server], stdin=subprocess.PIPE,
                        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, env=env)
init = call(proc, 1, "initialize", {})
print("serverInfo:", init["result"]["serverInfo"])

question, path = sys.argv[1], sys.argv[2]
t0 = time.time()
resp = call(proc, 3, "tools/call", {"name": "bulk_read",
          "arguments": {"question": question, "file_paths": [path]}})
dt = time.time() - t0
result = resp.get("result", {})
text = result["content"][0]["text"] if result.get("content") else str(resp)
open(sys.argv[3], "w").write(text)
print(f"latencia: {dt:.2f}s | isError: {result.get('isError', False)} | chars respuesta: {len(text)}")
print("--- primeras 400 chars ---")
print(text[:400])
proc.terminate()
