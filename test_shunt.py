#!/usr/bin/env python3
"""
Model-Shunt Test Suite
Verifies engine resolution, model discovery, binary checks, hooks, and MCP stdio protocol.
"""
import sys
import os
import json
import subprocess

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from engine.worker import (
    resolve_settings,
    clean_markdown_fences,
    is_binary_file,
    get_best_model,
    RECOMMENDED_MODELS
)

def test_engine_resolution():
    print("[1/5] Testing engine settings resolution and model selection...")
    os.environ["SHUNT_PROVIDER"] = "gemini"
    os.environ["SHUNT_MODEL"] = "gemini-2.5-flash"
    os.environ["SHUNT_API_KEY"] = "dummy_key"
    cfg = resolve_settings()
    assert cfg["provider"] == "gemini", f"Expected gemini, got {cfg['provider']}"
    assert cfg["model"] == "gemini-2.5-flash", f"Expected gemini-2.5-flash, got {cfg['model']}"
    assert "googleapis" in cfg["base_url"], f"Unexpected base_url: {cfg['base_url']}"
    assert cfg["timeout"] >= 60, f"Expected timeout >= 60, got {cfg['timeout']}"

    # Test overrides
    cfg_override = resolve_settings(override_provider="groq", override_model="llama-3.3-70b-versatile")
    assert cfg_override["provider"] == "groq"
    assert cfg_override["model"] == "llama-3.3-70b-versatile"

    # Test best model recommendations
    best_reader = get_best_model("bulk-reader", provider="gemini")
    assert "flash" in best_reader
    best_writer = get_best_model("code-writer", provider="groq")
    assert best_writer in RECOMMENDED_MODELS["groq"]["writer"]

    code_with_fences = "```python\nprint('hello world')\n```"
    assert clean_markdown_fences(code_with_fences) == "print('hello world')"
    print("  -> Engine resolution & model selection passed.")

def test_binary_detection():
    print("[2/5] Testing binary file detection...")
    bin_file = "/tmp/test_binary.bin"
    txt_file = "/tmp/test_text.txt"
    try:
        with open(bin_file, "wb") as f:
            f.write(b"Hello\x00World\x01\x02\x03")
        with open(txt_file, "w", encoding="utf-8") as f:
            f.write("Normal text file with lines\nLine 2\n")

        assert is_binary_file(bin_file) is True, "Expected binary file detection to return True"
        assert is_binary_file(txt_file) is False, "Expected text file detection to return False"
        print("  -> Binary detection passed.")
    finally:
        for p in (bin_file, txt_file):
            if os.path.exists(p):
                os.remove(p)

def test_hooks():
    print("[3/5] Testing PreToolUse hooks (agent-agnostic)...")
    hook_size = os.path.join(os.path.dirname(os.path.abspath(__file__)), "plugin/hooks/check-file-size")
    hook_bash = os.path.join(os.path.dirname(os.path.abspath(__file__)), "plugin/hooks/check-bash-read")

    # 1. Targeted read with limit/offset should allow
    p = subprocess.Popen([hook_size], stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    out, _ = p.communicate(json.dumps({"tool_input": {"file_path": "/etc/hosts", "limit": 10}}))
    res = json.loads(out.strip())
    assert res.get("decision") == "allow", f"Expected allow, got {res}"

    # 2. Large file whole read should block
    test_large_file = "/tmp/test_large_file.txt"
    with open(test_large_file, "w") as f:
        f.write("\n" * 400)

    try:
        p = subprocess.Popen([hook_size], stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        out, _ = p.communicate(json.dumps({"tool_input": {"file_path": test_large_file}}))
        res = json.loads(out.strip())
        assert res.get("decision") == "block", f"Expected block, got {res}"

        # 3. Test check-bash-read with flags (e.g. cat -n /tmp/test_large_file.txt)
        p = subprocess.Popen([hook_bash], stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        out, _ = p.communicate(json.dumps({"tool_input": {"command": f"cat -n {test_large_file}"}}))
        res = json.loads(out.strip())
        assert res.get("decision") == "block", f"Expected block on cat -n, got {res}"

        # 4. Pipe should be allowed
        p = subprocess.Popen([hook_bash], stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        out, _ = p.communicate(json.dumps({"tool_input": {"command": f"cat {test_large_file} | grep foo"}}))
        res = json.loads(out.strip())
        assert res.get("decision") == "allow", f"Expected allow on piped cat, got {res}"
        print("  -> Hooks tests passed.")
    finally:
        if os.path.exists(test_large_file):
            os.remove(test_large_file)

def test_mcp_server():
    print("[4/5] Testing MCP stdio server protocol & tools...")
    server_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "mcp/server.py")
    proc = subprocess.Popen(
        [sys.executable, server_path],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True
    )

    # 1. Initialize
    init_req = json.dumps({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}}) + "\n"
    proc.stdin.write(init_req)
    proc.stdin.flush()
    init_resp = json.loads(proc.stdout.readline())
    assert init_resp["result"]["serverInfo"]["name"] == "model-shunt-mcp"

    # 2. List tools
    tools_req = json.dumps({"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}}) + "\n"
    proc.stdin.write(tools_req)
    proc.stdin.flush()
    tools_resp = json.loads(proc.stdout.readline())
    tools = {t["name"] for t in tools_resp["result"]["tools"]}
    assert "bulk_read" in tools and "code_write" in tools and "get_available_models" in tools, f"Missing tools: {tools}"

    # 3. Call get_available_models tool
    models_req = json.dumps({
        "jsonrpc": "2.0",
        "id": 3,
        "method": "tools/call",
        "params": {
            "name": "get_available_models",
            "arguments": {"provider": "gemini"}
        }
    }) + "\n"
    proc.stdin.write(models_req)
    proc.stdin.flush()
    models_resp = json.loads(proc.stdout.readline())
    assert not models_resp.get("result", {}).get("isError")
    info = json.loads(models_resp["result"]["content"][0]["text"])
    assert info["provider"] == "gemini"
    assert "best_model_for_reader" in info

    # 4. Call bulk_read on binary file -> should return error
    bin_file = "/tmp/test_binary_mcp.bin"
    with open(bin_file, "wb") as f:
        f.write(b"data\x00nullbyte")
    try:
        call_req = json.dumps({
            "jsonrpc": "2.0",
            "id": 4,
            "method": "tools/call",
            "params": {
                "name": "bulk_read",
                "arguments": {"question": "What is this?", "file_paths": [bin_file]}
            }
        }) + "\n"
        proc.stdin.write(call_req)
        proc.stdin.flush()
        call_resp = json.loads(proc.stdout.readline())
        assert call_resp["result"].get("isError") is True, f"Expected error for binary file, got {call_resp}"
        assert "binary" in call_resp["result"]["content"][0]["text"]
    finally:
        if os.path.exists(bin_file):
            os.remove(bin_file)

    proc.terminate()
    print("  -> MCP server protocol & tool execution passed.")

def test_cli_list_models():
    print("[5/5] Testing CLI --list-models flag...")
    worker_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "engine/worker.py")
    res = subprocess.run([sys.executable, worker_path, "--list-models", "--provider", "gemini"], capture_output=True, text=True)
    assert res.returncode == 0, f"Expected returncode 0, got {res.returncode}: {res.stderr}"
    assert "Recommended Reader Model" in res.stdout
    assert "Recommended Writer Model" in res.stdout
    print("  -> CLI --list-models passed.")

if __name__ == "__main__":
    test_engine_resolution()
    test_binary_detection()
    test_hooks()
    test_mcp_server()
    test_cli_list_models()
    print("\nALL VERIFICATION TESTS PASSED SUCCESSFULLY!")
