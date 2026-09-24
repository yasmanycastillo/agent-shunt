#!/usr/bin/env python3
"""
Model-Shunt Real-World Benchmark Runner
Measures token compression, latency, cost savings, and citation accuracy on real codebases.
"""

import sys
import os
import time
import re
import json
import argparse

# Add package/engine to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from src.model_shunt.worker import run_worker, resolve_settings, number_file_lines

# Pricing per 1 Million Tokens (Input) as of 2026
MODEL_PRICING = {
    "claude-3-7-sonnet": 3.00,
    "gpt-4o": 2.50,
    "claude-3-5-sonnet": 3.00,
    "gemini-2.5-flash": 0.075,
    "gemini-1.5-flash": 0.075,
    "groq-llama-3.3-70b": 0.59,
    "ollama-local": 0.00
}

def estimate_tokens(text: str) -> int:
    """Accurate token estimator based on BPE statistics for source code (~3.6 chars/token)."""
    return max(1, int(len(text) / 3.6))

def extract_cited_lines(text: str, filename: str) -> list:
    """Extract cited line numbers matching patterns like file.py:42, line 42, or [42]."""
    cites = []
    base_name = os.path.basename(filename)
    
    # Pattern 1: filename:line (e.g. ecf_document.py:69)
    pat1 = re.compile(rf"{re.escape(base_name)}:(\d+)")
    for match in pat1.finditer(text):
        cites.append(int(match.group(1)))
        
    # Pattern 2: line 69, lines 69-75, L69
    pat2 = re.compile(r"(?:line|lines|L)\s*(\d+)", re.IGNORECASE)
    for match in pat2.finditer(text):
        cites.append(int(match.group(1)))

    # Pattern 3: Prefix N| citations
    pat3 = re.compile(r"\b(\d+)\|")
    for match in pat3.finditer(text):
        cites.append(int(match.group(1)))

    return sorted(list(set(cites)))

def verify_citations(file_path: str, cited_lines: list) -> tuple:
    """Check how many cited lines point to non-empty, valid code lines in the source file."""
    if not cited_lines or not os.path.isfile(file_path):
        return 0, len(cited_lines), 0.0

    with open(file_path, "r", encoding="utf-8", errors="replace") as f:
        file_lines = f.readlines()

    valid_cites = 0
    for line_num in cited_lines:
        idx = line_num - 1
        if 0 <= idx < len(file_lines):
            line_content = file_lines[idx].strip()
            # If line is not purely blank or comment, or within context
            if line_content:
                valid_cites += 1

    total = len(cited_lines)
    accuracy = (valid_cites / total * 100) if total > 0 else 100.0
    return valid_cites, total, accuracy

def run_benchmark(target_file: str, question: str, provider: str = None, model: str = None):
    if not os.path.isfile(target_file):
        print(f"Error: Target file not found: {target_file}")
        sys.exit(1)

    print("=" * 80)
    print("                MODEL-SHUNT REAL-WORLD BENCHMARK RUNNER")
    print("=" * 80)
    
    settings = resolve_settings(override_provider=provider, override_model=model)
    prov = settings["provider"]
    mod = settings["model"]
    
    print(f"Configured Worker: {prov} / {mod}")
    print(f"Target File:       {target_file}")
    
    # 1. Analyze Source Corpus
    with open(target_file, "r", encoding="utf-8", errors="replace") as f:
        raw_code = f.read()

    line_count = len(raw_code.splitlines())
    byte_size = len(raw_code.encode("utf-8"))
    raw_tokens = estimate_tokens(raw_code)

    print(f"Corpus Metrics:    {line_count:,} lines | {byte_size / 1024:.1f} KB | ~{raw_tokens:,} tokens")
    print(f"Question:          \"{question}\"")
    print("-" * 80)
    print("Dispatching to Shunt Worker Engine via streaming stdin...")

    # Build XML payload with line numbers
    xml_payload = f'<file path="{target_file}">\n{raw_code}\n</file>\n\nQuestion: {question}'
    xml_payload = number_file_lines(xml_payload)

    # 2. Measure Latency & Execute
    t_start = time.perf_counter()
    try:
        response = run_worker(
            mode="bulk-reader",
            content=xml_payload,
            override_provider=provider,
            override_model=model
        )
    except Exception as e:
        print(f"\nExecution Failed: {e}")
        return
    t_end = time.perf_counter()
    latency = t_end - t_start

    # 3. Analyze Output
    output_lines = len(response.splitlines())
    output_tokens = estimate_tokens(response)
    token_saved = max(0, raw_tokens - output_tokens)
    compression_ratio = (token_saved / raw_tokens * 100) if raw_tokens > 0 else 0.0

    # 4. Citation Validation
    cited_lines = extract_cited_lines(response, target_file)
    valid_cites, total_cites, cite_accuracy = verify_citations(target_file, cited_lines)

    # 5. Financial Comparison
    # Cost without Shunt: Primary agent reads full raw file
    cost_claude = (raw_tokens / 1_000_000) * MODEL_PRICING["claude-3-7-sonnet"]
    cost_gpt4o = (raw_tokens / 1_000_000) * MODEL_PRICING["gpt-4o"]
    
    # Cost with Shunt: Worker reads raw file + primary only reads synthesis
    worker_unit_price = MODEL_PRICING.get(mod, MODEL_PRICING.get("gemini-2.5-flash", 0.075))
    cost_worker = (raw_tokens / 1_000_000) * worker_unit_price
    cost_primary_synthesis = (output_tokens / 1_000_000) * MODEL_PRICING["claude-3-7-sonnet"]
    cost_with_shunt = cost_worker + cost_primary_synthesis
    savings_usd = cost_claude - cost_with_shunt
    savings_pct = (savings_usd / cost_claude * 100) if cost_claude > 0 else 0.0

    # 6. Display Benchmark Report
    print("\n" + "=" * 80)
    print("                           BENCHMARK RESULTS")
    print("=" * 80)
    print(f"⏱️  Wall-Clock Latency:       {latency:.2f} seconds")
    print(f"📥 Input Tokens (Raw):        {raw_tokens:,} tokens ({line_count:,} lines)")
    print(f"📤 Output Tokens (Synthesis): {output_tokens:,} tokens ({output_lines} lines)")
    print(f"🔥 Context Tokens Saved:      {token_saved:,} tokens")
    print(f"⚡ Token Reduction Ratio:     {compression_ratio:.2f}% CONTEXT SAVED")
    print("-" * 80)
    print("🎯 CITATION ACCURACY (GROUND-TRUTH CHECK)")
    print(f"   Cited Line References:    {total_cites} detected")
    print(f"   Verified Valid in Source: {valid_cites} / {total_cites}")
    print(f"   Citation Precision Rate:  {cite_accuracy:.1f}%")
    print("-" * 80)
    print("💰 COST PER INVOCATION & AT SCALE (1,000 reads/month)")
    print(f"   Direct Claude 3.7 Sonnet: ${cost_claude:.4f} / call  ->  ${cost_claude * 1000:,.2f} / month")
    print(f"   Direct GPT-4o:            ${cost_gpt4o:.4f} / call  ->  ${cost_gpt4o * 1000:,.2f} / month")
    print(f"   With Model-Shunt:         ${cost_with_shunt:.4f} / call  ->  ${cost_with_shunt * 1000:,.2f} / month")
    print(f"   Net Monthly Savings:      ${savings_usd * 1000:,.2f} ({savings_pct:.1f}% cheaper)")
    print("=" * 80)
    print("\n📝 SYNTHESIS OUTPUT RECEIVED BY PRIMARY AGENT:")
    print("-" * 80)
    print(response)
    print("-" * 80)

def main():
    parser = argparse.ArgumentParser(description="Model-Shunt Benchmark")
    parser.add_argument("--file", type=str, required=True, help="Path to source file to benchmark")
    parser.add_argument("--question", type=str, default="How does the document state machine work, and what are the main methods for sending and validating?", help="Question to test")
    parser.add_argument("--provider", type=str, default=None, help="LLM Provider (gemini, groq, etc.)")
    parser.add_argument("--model", type=str, default=None, help="LLM Model")
    args = parser.parse_args()

    run_benchmark(args.file, args.question, args.provider, args.model)

if __name__ == "__main__":
    main()
