---
name: bulk-reader
description: Read large or multiple files using an economical worker model (e.g. Gemini Flash) to extract concise answers without flooding agent context.
---

# Bulk Reader Skill

Use this skill when:
- You need to analyze code across one or more files totaling over 350 lines.
- You need to understand relationships, implementations, or answer questions without loading entire files into your context.
- The `Read` tool was blocked by `check-file-size` hook.

## Usage
Run via Bash:
```bash
bulk-read --question "How are authentication tokens refreshed and where are they stored?" --paths src/auth.ts src/token-manager.ts
```

The tool will return structured bullet points with exact line numbers and symbol names.
