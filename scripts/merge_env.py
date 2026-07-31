#!/usr/bin/env python3
"""Merge two .env-style files, with the second file's values overriding the first.

Usage:
    python3 scripts/merge_env.py .env.example envs/ollama-local.env.example > .env

The merge is key-based: any variable defined in the second file REPLACES the
value from the first file (in place, preserving the original line position
where possible). Blank lines and comments are preserved.

Rules:
- The first occurrence of a key is kept in its original position.
- If a key is redefined in the second file, the new value replaces the old
  one at the original position.
- Trailing duplicate keys are dropped.
- Inline comments after `=` (e.g. `KEY=value  # comment`) are preserved.
"""

import re
import sys


def parse_env(text: str) -> list[tuple[str, str, str]]:
    """Parse env file text into (kind, key, line) tuples.

    kind is one of: 'blank', 'comment', 'kv'.
    """
    parsed: list[tuple[str, str, str]] = []
    for raw in text.splitlines(keepends=True):
        line = raw.rstrip("\n")
        stripped = line.strip()
        if not stripped:
            parsed.append(("blank", "", raw))
            continue
        if stripped.startswith("#"):
            parsed.append(("comment", "", raw))
            continue
        m = re.match(r"^([A-Z_][A-Z0-9_]*)\s*=", line)
        if m:
            parsed.append(("kv", m.group(1), raw))
        else:
            # Non-key line (e.g. an export, or something unusual) — keep as-is
            parsed.append(("other", "", raw))
    return parsed


def merge(base: str, override: str) -> str:
    base_lines = parse_env(base)
    override_keys: dict[str, str] = {}
    for kind, key, line in base_lines + parse_env(override):
        if kind == "kv" and key:
            # Later occurrences win
            override_keys[key] = line

    # Walk base and substitute any keys that are overridden
    result: list[str] = []
    seen: set[str] = set()
    for kind, key, line in base_lines:
        if kind == "kv" and key in override_keys:
            result.append(override_keys[key])
            seen.add(key)
        else:
            result.append(line)

    # Append any new keys from the override that weren't in base
    new_keys = [
        line
        for kind, key, line in parse_env(override)
        if kind == "kv" and key and key not in seen
    ]
    if new_keys:
        result.append("\n# Additional keys from override file\n")
        result.extend(new_keys)

    return "".join(result)


def main() -> int:
    if len(sys.argv) != 3:
        print(
            "Usage: merge_env.py BASE OVERRIDE\n"
            "  Reads BASE, applies OVERRIDE on top, writes to stdout.",
            file=sys.stderr,
        )
        return 2

    base_path, override_path = sys.argv[1], sys.argv[2]

    with open(base_path, encoding="utf-8") as f:
        base_text = f.read()
    with open(override_path, encoding="utf-8") as f:
        override_text = f.read()

    sys.stdout.write(merge(base_text, override_text))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
