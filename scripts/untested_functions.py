"""
List the functions of app/ that no test runs (not a single line executed).

    pytest --cov=app --cov-report=json:coverage.json
    python scripts/untested_functions.py coverage.json      # exit code 1 when some are left

Functions reached only from outside the test process (e.g. the gunicorn entry point) go in SKIP.
"""
import ast
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SKIP: set[str] = set()


def untested(report: dict) -> list[str]:
    missing = []
    for name, data in report["files"].items():
        path = Path(name) if Path(name).is_absolute() else ROOT / name
        executed = set(data["executed_lines"])
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            body = {line for stmt in node.body for line in range(stmt.lineno, (stmt.end_lineno or stmt.lineno) + 1)}
            label = f"{path.relative_to(ROOT)}:{node.lineno} {node.name}"
            if not body & executed and f"{path.relative_to(ROOT)}::{node.name}" not in SKIP:
                missing.append(label)
    return sorted(missing)


def main() -> int:
    report = json.loads(Path(sys.argv[1] if len(sys.argv) > 1 else "coverage.json").read_text())
    missing = untested(report)
    for label in missing:
        print(label)
    print(f"{len(missing)} functions never run by the tests", file=sys.stderr)
    return 1 if missing else 0


if __name__ == "__main__":
    sys.exit(main())
