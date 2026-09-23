#!/usr/bin/env python3
"""
Model-Shunt Worker Engine
Zero-dependency universal LLM client for delegating bulk I/O and boilerplate code generation.
Agnostic to calling agents (Cursor, Antigravity, Claude Code, Windsurf, Aider, etc.).
Supports Google Gemini, OpenAI, Groq, DeepSeek, Anthropic, Ollama, OpenRouter, and any OpenAI-compatible endpoint.
"""

import sys
import os
import json
import re
import time
import argparse
import urllib.request
import urllib.error

DEFAULT_CONFIG_PATHS = [
    os.path.expanduser("~/.config/model-shunt/config.json"),
    # repo root when running from a checkout (src/model_shunt/worker.py -> 3 levels up)
    os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "config.json")
]

SYSTEM_PROMPTS = {
    "bulk-reader": (
        "You are a precise code analyst. Read the provided files and answer the question concisely.\n"
        "Every line inside each <file> block is prefixed with 'N|' where N is its 1-based line number.\n"
        "When citing locations, use those exact prefixes as line numbers — never count or guess lines yourself.\n"
        "Output structured bullets only. No greetings, no prose, no preambles, no conversational filler.\n"
        "Lead every bullet with the exact filename, class, function, or line number reference.\n"
        "Use nested bullets for details. Skip anything the caller did not ask for."
    ),
    "code-writer": (
        "You generate code files based on a specification and reference files.\n"
        "Match the existing patterns, conventions, naming, style, and structure of the reference file exactly.\n"
        "Output ONLY the raw code — no explanations, no commentary, no markdown code fences (do not wrap in ```).\n"
        "If the spec is ambiguous, make reasonable choices that match the reference code's conventions."
    )
}

PROVIDER_DEFAULTS = {
    "gemini": {
        "base_url": "https://generativelanguage.googleapis.com/v1beta/openai",
        "model": "gemini-2.5-flash",
        "env_key": "GEMINI_API_KEY"
    },
    "openai": {
        "base_url": "https://api.openai.com/v1",
        "model": "gpt-4o-mini",
        "env_key": "OPENAI_API_KEY"
    },
    "groq": {
        "base_url": "https://api.groq.com/openai/v1",
        "model": "llama-3.3-70b-versatile",
        "env_key": "GROQ_API_KEY"
    },
    "deepseek": {
        "base_url": "https://api.deepseek.com/v1",
        "model": "deepseek-chat",
        "env_key": "DEEPSEEK_API_KEY"
    },
    "openrouter": {
        "base_url": "https://openrouter.ai/api/v1",
        "model": "google/gemini-2.5-flash",
        "env_key": "OPENROUTER_API_KEY"
    },
    "anthropic": {
        "base_url": "https://api.anthropic.com/v1",
        "model": "claude-3-5-haiku-20241022",
        "env_key": "ANTHROPIC_API_KEY"
    },
    "ollama": {
        "base_url": "http://localhost:11434/v1",
        "model": "qwen2.5-coder:latest",
        "env_key": None
    }
}

RECOMMENDED_MODELS = {
    "gemini": {
        "reader": ["gemini-2.5-flash", "gemini-2.0-flash", "gemini-1.5-flash"],
        "writer": ["gemini-2.5-flash", "gemini-2.0-flash", "gemini-1.5-pro"]
    },
    "openai": {
        "reader": ["gpt-4o-mini", "gpt-4.1-mini", "gpt-4o"],
        "writer": ["gpt-4o-mini", "gpt-4o", "o3-mini"]
    },
    "groq": {
        "reader": ["llama-3.3-70b-versatile", "llama-3.1-8b-instant"],
        "writer": ["llama-3.3-70b-versatile", "qwen-2.5-coder-32b"]
    },
    "deepseek": {
        "reader": ["deepseek-chat"],
        "writer": ["deepseek-coder", "deepseek-chat"]
    },
    "openrouter": {
        "reader": ["google/gemini-2.5-flash", "meta-llama/llama-3.3-70b-instruct:free"],
        "writer": ["qwen/qwen-2.5-coder-32b-instruct", "google/gemini-2.5-flash"]
    },
    "anthropic": {
        "reader": ["claude-3-5-haiku-20241022", "claude-3-haiku-20240307"],
        "writer": ["claude-3-5-haiku-20241022", "claude-3-5-sonnet-20241022"]
    },
    "ollama": {
        "reader": ["qwen2.5-coder:latest", "llama3.2:latest", "mistral:latest"],
        "writer": ["qwen2.5-coder:latest", "deepseek-coder-v2:latest", "codellama:latest"]
    }
}

def is_binary_file(filepath: str, check_bytes: int = 8192) -> bool:
    """Check if a file appears to be binary by inspecting initial bytes for null characters."""
    try:
        with open(filepath, "rb") as f:
            chunk = f.read(check_bytes)
        if b"\x00" in chunk:
            return True
        text_characters = bytes(range(32, 127)) + b"\n\r\t\b\f"
        non_text = sum(1 for byte in chunk if byte not in text_characters)
        if len(chunk) > 0 and (non_text / len(chunk)) > 0.30:
            return True
        return False
    except Exception:
        return False

def load_file_config():
    for path in DEFAULT_CONFIG_PATHS:
        if os.path.isfile(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                pass
    return {}

def resolve_settings(override_provider: str = None, override_model: str = None):
    cfg = load_file_config()

    # 1. Detect provider
    provider = (
        override_provider or
        os.environ.get("SHUNT_PROVIDER") or
        cfg.get("provider")
    )
    if not provider:
        for p, info in PROVIDER_DEFAULTS.items():
            if info["env_key"] and os.environ.get(info["env_key"]):
                provider = p
                break
        if not provider:
            provider = "gemini"

    p_defaults = PROVIDER_DEFAULTS.get(provider, PROVIDER_DEFAULTS["gemini"])

    # 2. Base URL
    base_url = (
        os.environ.get("SHUNT_BASE_URL") or
        cfg.get("base_url") or
        p_defaults["base_url"]
    ).rstrip("/")

    # 3. Model
    model = (
        override_model or
        os.environ.get("SHUNT_MODEL") or
        cfg.get("model") or
        p_defaults["model"]
    )

    # 4. API Key
    api_key = (
        os.environ.get("SHUNT_API_KEY") or
        cfg.get("api_key") or
        (os.environ.get(p_defaults["env_key"]) if p_defaults["env_key"] else None) or
        "none"
    )

    # 5. Timeout & Max tokens
    timeout = int(os.environ.get("SHUNT_TIMEOUT") or cfg.get("timeout") or 90)
    max_tokens = int(os.environ.get("SHUNT_MAX_TOKENS") or cfg.get("max_tokens") or 0)

    return {
        "provider": provider,
        "base_url": base_url,
        "model": model,
        "api_key": api_key,
        "timeout": timeout,
        "max_tokens": max_tokens
    }

def fetch_available_models(provider: str = None, timeout: int = 10) -> list:
    """Dynamically queries the provider's models endpoint to list current active models."""
    settings = resolve_settings(override_provider=provider)
    prov = provider or settings["provider"]
    b_url = settings["base_url"]
    key = settings["api_key"]

    headers = {"Content-Type": "application/json"}
    if prov == "anthropic":
        endpoint = f"{b_url}/models"
        headers["x-api-key"] = key
        headers["anthropic-version"] = "2023-06-01"
    elif prov == "ollama" and b_url.endswith("/v1"):
        # Ollama v1 endpoint or native api
        endpoint = f"{b_url}/models"
    else:
        endpoint = f"{b_url}/models"
        if key and key != "none":
            headers["Authorization"] = f"Bearer {key}"

    try:
        req = urllib.request.Request(endpoint, headers=headers)
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            models = []
            if isinstance(data, dict):
                if "data" in data and isinstance(data["data"], list):
                    for item in data["data"]:
                        if isinstance(item, dict) and "id" in item:
                            models.append(item["id"])
                elif "models" in data and isinstance(data["models"], list):
                    for item in data["models"]:
                        if isinstance(item, dict) and "name" in item:
                            models.append(item["name"])
            return models
    except Exception:
        # Fallback to recommended list if online discovery fails or is unsupported
        return RECOMMENDED_MODELS.get(prov, {}).get("reader", []) + RECOMMENDED_MODELS.get(prov, {}).get("writer", [])

def get_best_model(mode: str, provider: str = None, available_models: list = None) -> str:
    """Selects the best available model for reader or writer tasks."""
    settings = resolve_settings(override_provider=provider)
    prov = provider or settings["provider"]
    task = "writer" if mode in ["code-writer", "writer"] else "reader"
    recs = RECOMMENDED_MODELS.get(prov, {}).get(task, [])

    if available_models:
        # 1. Exact priority match against curated recommendations
        for rec in recs:
            if rec in available_models:
                return rec
        # 2. Heuristic match
        keywords = ["coder", "code"] if task == "writer" else ["flash", "mini", "haiku", "instant"]
        for kw in keywords:
            for m in available_models:
                if kw in m.lower():
                    return m
        # 3. Fallback to first available model
        return available_models[0]

    # Return top recommendation if no active list is provided
    if recs:
        return recs[0]
    return settings["model"]

def execute_http_request(req: urllib.request.Request, timeout: int = 90, max_retries: int = 2) -> dict:
    """Execute HTTP request with automatic retry and backoff for rate limits and server errors."""
    attempt = 0
    while True:
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            if e.code in (429, 500, 502, 503, 504) and attempt < max_retries:
                attempt += 1
                time.sleep(2 ** attempt)
                continue
            err_body = e.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"API request failed with HTTP {e.code}: {err_body}") from e
        except (urllib.error.URLError, TimeoutError) as e:
            if attempt < max_retries:
                attempt += 1
                time.sleep(2 ** attempt)
                continue
            raise RuntimeError(f"Network error communicating with LLM endpoint: {e}") from e

def call_anthropic(base_url, api_key, model, system_prompt, user_content, temperature=0.2, max_tokens=4096, timeout=90):
    endpoint = f"{base_url}/messages"
    payload = {
        "model": model,
        "max_tokens": max_tokens,
        "temperature": temperature,
        "system": system_prompt,
        "messages": [
            {"role": "user", "content": user_content}
        ]
    }
    headers = {
        "Content-Type": "application/json",
        "x-api-key": api_key,
        "anthropic-version": "2023-06-01"
    }
    req = urllib.request.Request(endpoint, data=json.dumps(payload).encode("utf-8"), headers=headers)
    data = execute_http_request(req, timeout=timeout)
    texts = [b["text"] for b in data.get("content", []) if b.get("type") == "text"]
    return "".join(texts)

def call_openai_compatible(base_url, api_key, model, system_prompt, user_content, temperature=0.2, max_tokens=4096, timeout=90):
    endpoint = f"{base_url}/chat/completions"
    payload = {
        "model": model,
        "temperature": temperature,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content}
        ]
    }
    if max_tokens > 0:
        payload["max_tokens"] = max_tokens

    headers = {
        "Content-Type": "application/json"
    }
    if api_key and api_key != "none":
        headers["Authorization"] = f"Bearer {api_key}"

    req = urllib.request.Request(endpoint, data=json.dumps(payload).encode("utf-8"), headers=headers)
    data = execute_http_request(req, timeout=timeout)
    choices = data.get("choices", [])
    if not choices:
        raise RuntimeError(f"No choices returned from LLM: {data}")
    return choices[0].get("message", {}).get("content", "")

def run_worker(
    mode: str,
    content: str,
    temperature: float = 0.2,
    override_provider: str = None,
    override_model: str = None
) -> str:
    settings = resolve_settings(override_provider=override_provider, override_model=override_model)
    system_prompt = SYSTEM_PROMPTS.get(mode, SYSTEM_PROMPTS["bulk-reader"])

    model = settings["model"]
    # If auto model requested
    if model == "auto":
        live_models = fetch_available_models(provider=settings["provider"])
        model = get_best_model(mode, provider=settings["provider"], available_models=live_models)

    # Determine default max tokens if not explicitly configured
    max_toks = settings["max_tokens"]
    if max_toks <= 0:
        max_toks = 8192 if mode == "code-writer" else 4096

    timeout = settings["timeout"]

    if settings["provider"] == "anthropic":
        return call_anthropic(
            settings["base_url"], settings["api_key"], model,
            system_prompt, content, temperature, max_tokens=max_toks, timeout=timeout
        )
    else:
        return call_openai_compatible(
            settings["base_url"], settings["api_key"], model,
            system_prompt, content, temperature, max_tokens=max_toks, timeout=timeout
        )

def clean_markdown_fences(text: str) -> str:
    lines = text.splitlines()
    if lines and lines[0].strip().startswith("```"):
        lines = lines[1:]
    if lines and lines[-1].strip() == "```":
        lines = lines[:-1]
    return "\n".join(lines).strip()

FILE_BLOCK_RE = re.compile(r'(<file path="[^"]*">\n)(.*?)(\n</file>)', re.DOTALL)

def number_file_lines(payload: str) -> str:
    """Prefix every line inside <file> blocks with its 1-based line number.

    The corpus arrives without line numbers (streamed via stdin by bulk-read
    or assembled by the MCP server), so the worker model cannot cite exact
    locations. Adding 'N|' prefixes makes verifiable line references possible.
    """
    def _number(match):
        lines = match.group(2).split("\n")
        numbered = "\n".join(f"{i}|{ln}" for i, ln in enumerate(lines, 1))
        return match.group(1) + numbered + match.group(3)
    return FILE_BLOCK_RE.sub(_number, payload)

def main():
    parser = argparse.ArgumentParser(description="Model-Shunt Universal Worker Engine")
    parser.add_argument("--mode", choices=["bulk-reader", "code-writer"], default="bulk-reader")
    parser.add_argument("--provider", type=str, default=None, help="Provider override (gemini, groq, openai, ollama, etc.)")
    parser.add_argument("--model", type=str, default=None, help="Model override or 'auto'")
    parser.add_argument("--auto-model", action="store_true", help="Automatically pick best model for task")
    parser.add_argument("--list-models", action="store_true", help="List available models for the provider and recommendations")
    parser.add_argument("--temperature", type=float, default=0.2)
    parser.add_argument("--target", type=str, default=None, help="Target file to write output directly to disk")
    args = parser.parse_args()

    if args.list_models:
        settings = resolve_settings(override_provider=args.provider)
        prov = settings["provider"]
        print(f"Provider: {prov} ({settings['base_url']})")
        print(f"Configured model: {settings['model']}")
        print("\nFetching available models from endpoint...")
        models = fetch_available_models(provider=prov)
        if models:
            print("Available models:")
            for m in models:
                print(f"  - {m}")
        else:
            print("  (No models listed from endpoint; checking recommendations)")

        best_reader = get_best_model("bulk-reader", provider=prov, available_models=models)
        best_writer = get_best_model("code-writer", provider=prov, available_models=models)
        print(f"\nRecommended Reader Model (Bulk I/O): {best_reader}")
        print(f"Recommended Writer Model (Code/Tests): {best_writer}")
        sys.exit(0)

    model_override = "auto" if args.auto_model else args.model

    content = sys.stdin.read()
    if not content.strip():
        sys.stderr.write("Error: empty input received on stdin\n")
        sys.exit(1)

    if args.mode == "bulk-reader":
        content = number_file_lines(content)

    result = run_worker(
        mode=args.mode,
        content=content,
        temperature=args.temperature,
        override_provider=args.provider,
        override_model=model_override
    )

    if args.mode == "code-writer":
        result = clean_markdown_fences(result)

    if args.target:
        os.makedirs(os.path.dirname(os.path.abspath(args.target)), exist_ok=True)
        with open(args.target, "w", encoding="utf-8") as f:
            f.write(result + "\n")
        sys.stderr.write(f"[model-shunt] Wrote {len(result.splitlines())} lines to {args.target}\n")
    else:
        print(result)

if __name__ == "__main__":
    main()
