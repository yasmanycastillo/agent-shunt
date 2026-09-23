---
name: code-writer
description: Generate repetitive boilerplate code, unit tests, mock suites, or config files based on an existing reference file.
---

# Code Writer Skill

Use this skill when:
- You need to generate a new test file, config, or mock suite that follows the exact same pattern as an existing file in the project.
- You want to write code directly to disk without burning expensive frontier output tokens.

## Usage
Run via Bash:
```bash
# Generate unit tests matching an existing test suite and write directly to disk:
code-write --spec "Write comprehensive unit tests for PaymentService covering charge, refund, and timeout errors" --reference tests/UserService.test.ts --target tests/PaymentService.test.ts

# Generate to stdout:
code-write --spec "Create docker-compose service configuration for redis" --reference docker-compose.yml
```
