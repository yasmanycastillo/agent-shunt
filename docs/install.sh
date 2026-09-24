#!/usr/bin/env bash
# Model-Shunt universal installer
# One command for every machine: detects uv / pip / npm, installs the
# `model-shunt` MCP server command, and registers it with Claude Code if found.
#
#   curl -fsSL https://yasmanycastillo.github.io/model-shunt/install.sh | bash
#
# Flags (env vars):
#   SKIP_REGISTER=1   install the command but do not touch any MCP client
set -euo pipefail

CYAN='\033[0;36m'; GREEN='\033[0;32m'; YELLOW='\033[0;33m'; RED='\033[0;31m'; OFF='\033[0m'
say()  { printf "${CYAN}[model-shunt]${OFF} %s\n" "$1"; }
ok()   { printf "${GREEN}[model-shunt]${OFF} %s\n" "$1"; }
warn() { printf "${YELLOW}[model-shunt]${OFF} %s\n" "$1"; }
fail() { printf "${RED}[model-shunt]${OFF} %s\n" "$1" >&2; exit 1; }

command -v python3 >/dev/null 2>&1 || fail "Python 3.9+ is required (not found as python3)."

# 1. Install the `model-shunt` command with whatever package tool is available
if command -v uv >/dev/null 2>&1; then
  say "uv detected — installing with 'uv tool install'..."
  uv tool install model-shunt
elif command -v pipx >/dev/null 2>&1; then
  say "pipx detected — installing with pipx..."
  pipx install model-shunt
elif python3 -m pip --version >/dev/null 2>&1; then
  say "pip detected — installing with 'pip install --user'..."
  python3 -m pip install --user model-shunt
  # Ensure the user bin dir is on PATH for this session's later checks
  case ":$PATH:" in
    *":$HOME/.local/bin:"*) ;;
    *) export PATH="$HOME/.local/bin:$PATH" ;;
  esac
elif command -v npm >/dev/null 2>&1; then
  say "npm detected (no pip) — installing the npm launcher..."
  npm install -g model-shunt
else
  fail "No uv, pip, pipx or npm found. Install Python 3.9+ with pip, or uv, and retry."
fi

command -v model-shunt >/dev/null 2>&1 \
  || fail "Installation finished but 'model-shunt' is not on PATH. Reopen your shell and run 'model-shunt' to verify."
ok "Installed: $(command -v model-shunt)"

# 2. Register with Claude Code when present (skip with SKIP_REGISTER=1)
if [ "${SKIP_REGISTER:-0}" = "1" ]; then
  say "SKIP_REGISTER set — leaving MCP client configuration to you."
elif command -v claude >/dev/null 2>&1; then
  say "Claude Code detected — registering MCP server..."
  claude mcp add model-shunt -- model-shunt \
    && ok "Registered with Claude Code (restart Claude Code to load it)." \
    || warn "claude mcp add failed — register manually: claude mcp add model-shunt -- model-shunt"
else
  :
fi

# 3. Generic config for any other MCP client
cat <<EOF

$(printf ${GREEN}Done.${OFF}) The server command is: model-shunt

For any MCP client, use:

  {
    "mcpServers": {
      "model-shunt": { "command": "model-shunt" }
    }
  }

Environment (optional): SHUNT_PROVIDER, GEMINI_API_KEY / GROQ_API_KEY, SHUNT_MODEL=auto
Docs: https://github.com/yasmanycastillo/model-shunt
EOF
