#!/usr/bin/env node
/**
 * model-shunt MCP launcher (npm/npx shim).
 *
 * The server itself is pure Python (stdlib only, no pip install needed).
 * This shim locates a Python 3 interpreter and runs the bundled server with
 * stdio inherited so MCP clients can talk to it directly, e.g.:
 *
 *   npx -y model-shunt
 */

"use strict";

const { spawn } = require("child_process");
const path = require("path");

const SERVER = path.join(__dirname, "..", "src", "model_shunt", "server.py");
const CANDIDATES = ["python3", "python", "/usr/bin/python3", "/usr/local/bin/python3"];

function fail(msg) {
  process.stderr.write(`[model-shunt] ${msg}\n`);
  process.exit(1);
}

function findPython(onFound) {
  let i = 0;
  const next = () => {
    if (i >= CANDIDATES.length) {
      fail(
        "No Python 3 interpreter found. model-shunt's MCP server is pure Python " +
          "(stdlib only, no pip install required). Install Python 3.9+ and retry."
      );
      return;
    }
    const candidate = CANDIDATES[i++];
    const probe = spawn(candidate, ["-c", "import sys; sys.exit(0 if sys.version_info >= (3, 9) else 1)"], {
      stdio: ["ignore", "ignore", "ignore"],
    });
    probe.on("error", next);
    probe.on("exit", (code) => (code === 0 ? onFound(candidate) : next()));
  };
  next();
}

findPython((python) => {
  const child = spawn(python, [SERVER], { stdio: "inherit" });
  child.on("error", (err) => fail(`Failed to launch server: ${err.message}`));
  child.on("exit", (code, signal) => {
    if (signal) process.kill(process.pid, signal);
    else process.exit(code === null ? 1 : code);
  });
});
