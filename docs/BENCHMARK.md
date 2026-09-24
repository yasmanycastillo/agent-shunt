# Model-Shunt Real-World Benchmark

Independent validation run on real files (local repositories + live API downloads),
September 23, 2026. Worker: `gemini-2.5-flash` (free tier, `SHUNT_MODEL=auto`).

## Results

| # | File | Size | Lines | ~Tokens | Mode | Latency | Result |
|---|------|------|-------|---------|------|---------|--------|
| T1 | mypy `checker.py` | 446 KB | ~12,000 | ~111k | MCP server (stdio JSON-RPC) | 10.8 s | ✅ 8/9 line citations exact, 1 within ±2 lines (same import block) |
| T2 | Odoo `test_swissdec_cases.py` | 541 KB | 2,974 | ~135k | CLI (`bulk-read`) | 12.2 s | ✅ All cited test-method lines exact (L1508, L1551, L1626…) |
| T3 | npm registry `d3` metadata — **one single 733 KB line** | 733 KB | 1 | ~183k | CLI | 8.3 s | ✅ **100% ground truth**: latest 7.9.0 ✓, license ISC ✓, all 30/30 deps exact set match |
| T4 | Kubernetes OpenAPI `swagger.json` | 4.5 MB | 110,426 | ~1.12M | CLI | 17.4 s (retries) | ❌ HTTP 429 — exceeds free-tier tokens-per-minute quota |
| T5 | SQLite amalgamation `sqlite3.c` | 9 MB | 255,680 | ~2.25M | CLI | 21.4 s (retries) | ❌ HTTP 429 — exceeds free-tier tokens-per-minute quota |
| T6 | Binary `.whl` (negative test) | 15 KB | — | — | Live MCP server | <1 s | ✅ Clean rejection: binary files never sent to the LLM |

## Findings

1. **It works, and it is verifiable.** On three real files (111k–183k est. tokens) the worker
   returned structured answers with line citations that were checked against the source:
   100% of T3's factual claims matched a ground-truth parse of the JSON; T1/T2 line
   citations were exact (one T1 import-block citation off by 2 lines).
2. **The `N|` line-numbering prevents hallucinated locations** — including on a
   single-line 733 KB minified JSON, where any "line" answer would have been meaningless;
   the worker answered with verifiable facts instead.
3. **Practical per-call ceiling is the provider quota, not the model context.**
   Gemini 2.5 Flash accepts 1M-token contexts, but the free tier's per-minute token quota
   (~250k TPM) rejects larger payloads with HTTP 429 after retries (T4/T5).
   Practical ceiling on the free tier: **~800 KB of text per call**.
   Paid tiers raise this; a client-side chunk/map-reduce pass would remove the ceiling entirely (roadmap).
4. **Binary protection works end-to-end** via the live MCP server (T6): binaries are
   detected by byte-header inspection and rejected before any API call.
5. **Cost**: each successful call moved 100k–183k tokens from a $3/MTok frontier model to a
   ~$0.30/MTok worker — ~$0.30–0.50 saved per call, ~90% context reduction in the agent.

## Reproduce

```bash
# MCP mode (sandbox expanded)
SHUNT_ALLOWED_ROOTS="$HOME/src" python3 src/model_shunt/server.py

# CLI mode
SHUNT_MODEL=auto ./plugin/scripts/bulk-read --question "..." --paths <file>
```
