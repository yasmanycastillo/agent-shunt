# Model-Shunt Real-World Benchmark

Independent validation run on real files (local repositories + live API downloads),
September 23, 2026. Worker: `gemini-2.5-flash` (free tier, `SHUNT_MODEL=auto`).

## Results

| # | File | Size | Lines | ~Tokens | Mode | Latency | Result |
|---|------|------|-------|---------|------|---------|--------|
| T1 | mypy `checker.py` | 446 KB | 9,891 | ~111k | MCP server (stdio JSON-RPC) | 10.8 s | ⚠️ Of 13 `N\|` citations in the saved answer, 6 name the symbol on that line; 5 sit inside the named function; N\|86 and N\|2838 name a different symbol |
| T2 | Odoo `test_swissdec_cases.py` | 541 KB | 2,974 | ~135k | CLI (`bulk-read`) | 12.2 s | ✅ All cited test-method lines exact (L1508, L1551, L1626…) |
| T3 | npm registry `d3` metadata — **one single 733 KB line** | 733 KB | 1 | ~183k | CLI | 8.3 s | ✅ **100% ground truth**: latest 7.9.0 ✓, license ISC ✓, all 30/30 deps exact set match |
| T4 | Kubernetes OpenAPI `swagger.json` | 4.5 MB | 110,426 | ~1.29M | CLI (v1.1.3, direct) | 17.4 s (retries) | ❌ HTTP 429 — exceeds free-tier tokens-per-minute quota |
| T4b | Same `swagger.json` — **map-reduce (v1.2.0)** | 4.5 MB | 110,426 | ~1.29M | CLI, 9 chunks | ~2.5 min (1 quota wait) | ✅ **4/4 claims verified 100%**: `required: [schedule, jobTemplate]` at exact lines N\|4690/N\|4691, group `batch` N\|60211, `swagger: 2.0` N\|110425 |
| T5 | SQLite amalgamation `sqlite3.c` | 9.02 MB | 255,680 | ~2.25M | CLI (v1.1.3, direct) | 21.4 s (retries) | ❌ HTTP 429 — exceeds free-tier tokens-per-minute quota. v1.2.0 map-reduce completes it (T5b, 18 chunks) |
| T5b | SQLite amalgamation — **map-reduce (v1.2.0)** | 9 MB | 255,680 | ~2.67M | CLI, 18 chunks | ~6 min (4 quota waits) | ⚠️ Architecture answer 100% correct (`sqlite3RunParser`, `sqlite3GetToken`, `sLastToken`, `pzTail` loop, LEMON parser — all real); spot-check citation exactness 3/8 — misses are in-chunk region confusion (~1–3k lines off), not number corruption |
| T6 | Binary `.whl` (negative test) | 15 KB | — | — | Live MCP server | <1 s | ✅ Clean rejection: binary files never sent to the LLM |

> **Citation precision vs chunk size:** T2 and T4b cite the exact construct. T1, on a file that
> fits in one call, already mixes exact lines with in-function offsets. On 14k-line chunks (T5b)
> the misses get larger: a real line of the right region, the wrong construct. For citation-critical
> workloads on huge files, lower `SHUNT_CHUNK_CHARS` (e.g. `300000` ≈ 7k-line chunks). That costs
> more quota waits.

## Findings

1. **The factual checks hold.** T3's 30 dependencies, version 7.9.0 and ISC license match
   the npm registry. T2's 49 `L…` citations each land on a `def test_…`. T4b's four claims
   are on those exact lines of `swagger.json` (4.48 MB, 110,426 lines).
2. **T1 was not 8/9.** Re-checked against the 446,988-byte `checker.py` (9,891 lines, ~111k
   tokens at 4 chars/token). Six of thirteen `N|` citations name the symbol on that line.
   Five more are inside the named function but not on the cited line. Two name another symbol.
3. **`N|` numbering makes a citation checkable. It does not make it exact.** On the one-line
   733 KB JSON the worker returned facts instead of a meaningless line number. On 14k-line
   chunks (T5b) it still cites a real line of the right region and the wrong construct.
4. **The per-call ceiling is the provider quota. Map-reduce is already in v1.2.0.**
   A direct call above `SHUNT_MAX_DIRECT_TOKENS` (default 200k, `len//4`) is split by
   `run_bulk_reader`. The free tier still returns HTTP 429 on one large direct call (T4/T5,
   v1.1.3, practical ceiling ~800 KB) and inserts quota waits during the fan-out
   (T4b one wait, T5b four). Raw `sqlite3.c` is ~2.25M tokens; the numbered payload is ~2.67M
   and ran as 18 chunks of 600k characters, not ~16.
5. **This run was the Gemini free tier, so the provider charge was $0.** The agent received
   a short synthesis instead of the file. Dollar savings depend on paid list prices and were
   not measured here.

## Rerun (2026-09-24)

Same files, `gemini-2.5-flash`, through `run_bulk_reader`. A new probe plants three
defs at known lines and requires the cited line to contain that name.

| Case | Latency | Check |
|------|---------|--------|
| Probe | 1.5 s | 3/3 exact: `shunt_marker_alpha` L81, `shunt_marker_beta` L203, `shunt_marker_gamma` L356 |
| T1 mypy | 6.7 s | 6/11 bare `(line)` citations contain the named symbol. `check_func_item` L1349 is exact; `check_call` L2838 is not |
| T2 swissdec | 6.6 s | 48/49 `def` lines exact. `test_tf25_lehmann_nadine` cited L973; the def is L972 |
| T3 d3 | 5.8 s | 7.9.0, ISC, 30/30 dependencies, re-checked against the npm registry |
| T4b swagger | 131.8 s | 9 chunks, one 60 s quota wait. `schedule`/`jobTemplate` L4690/L4691, `batch` L4609 and L60211, `"swagger": "2.0"` L110425. Also cited real `"version"` lines L4611 (`v1`) and L25873 (`unversioned`) |
| T5b sqlite3.c | 287.1 s | 18 chunks, three 60 s quota waits, 2,674,247 est. tokens. 18/26 `name (N\|line)` citations contain the name |
| T6 binary | <1 s | A buffer with a null byte is classified binary and is not sent |

The non-empty-line counter in `benchmark.py` used to miss `N\|81` (it looked for `81\|`). It now counts both forms. The symbol check is `score_named_citations`. `run_bulk_reader` applies the same check before returning: a `name (N|k)` citation is removed when source line `k` does not contain that name.

## Reproduce

The rows above were produced by calling the worker directly, which is also what the CLI does:
`plugin/scripts/bulk-read` streams the file on stdin, and `worker.py --mode bulk-reader`
runs `number_file_lines` then `run_bulk_reader` (map-reduce included).

```bash
# CLI — same path as the published rows
SHUNT_MODEL=auto ./plugin/scripts/bulk-read --question "..." --paths <file>

# MCP — same reader, plus the workspace sandbox
SHUNT_ALLOWED_ROOTS="$HOME/src" python3 src/model_shunt/server.py
```

`benchmark.py` is a single-file timer around that same `run_bulk_reader` entry. Its citation
figure only counts whether a cited line is non-empty. It does not repeat the manual symbol
check behind T1, T2 and T4b. Token totals in both places use `len(text) // 4`.
