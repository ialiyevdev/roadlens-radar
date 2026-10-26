"""Check portable release source, versions and local Markdown links without Git."""

from __future__ import annotations

import argparse
import ast
import json
from pathlib import Path
import re
import tomllib
from urllib.parse import unquote, urlsplit


ROOT = Path(__file__).resolve().parents[1]
SOURCE_DIRECTORIES = ("backend", "frontend/src", "frontend/public", "scripts", "docs", "examples", "third_party", ".vscode", ".github")
EXCLUDED = {"__pycache__", ".pytest_cache", "node_modules", "dist", "dist-showcase"}
TEXT_SUFFIXES = {".py", ".ps1", ".md", ".json", ".toml", ".txt", ".lock", ".ts", ".tsx", ".mjs", ".yml", ".yaml", ".css", ".html", ".svg"}
SENSITIVE_PATTERNS = {
    "developer home path": re.compile(r"(?i)([a-z]:[\\/]Users[\\/]|[/]Users[/]|[/]home[/][a-z])"),
    "private key marker": re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    "possible credential assignment": re.compile(
        r'''(?im)(?:api[_-]?key|password|secret|access[_-]?token)\s*[=:]\s*["'][^"'\r\n]{12,}'''
    ),
}


def source_files(root: Path) -> list[Path]:
    files = {path for path in root.iterdir() if path.is_file() and
             (path.suffix in TEXT_SUFFIXES or path.name in {"LICENSE", ".gitignore", ".gitattributes"}) and
             not path.name.startswith(".env")}
    files.update(path for path in (root / "frontend").glob("*") if path.is_file() and
                 path.suffix in TEXT_SUFFIXES)
    for directory in SOURCE_DIRECTORIES:
        files.update(path for path in (root / directory).rglob("*") if path.is_file() and
                     not EXCLUDED.intersection(path.relative_to(root).parts))
    return sorted(files)


def markdown_errors(root: Path, files: list[Path]) -> list[str]:
    errors = []
    for path in files:
        if path.suffix != ".md":
            continue
        # Inline local file references; external URLs and anchors need separate review.
        for target in re.findall(r'!?\[[^\]]*\]\(([^)\s]+)(?:\s+"[^"]*")?\)', path.read_text(encoding="utf-8")):
            target = target.strip("<>")
            parsed = urlsplit(target)
            if parsed.scheme or target.startswith(("#", "//")):
                continue
            destination = (path.parent / unquote(parsed.path)).resolve()
            if not destination.is_relative_to(root.resolve()) or not destination.exists():
                errors.append(f"{path.relative_to(root).as_posix()}: missing or external local link ({target})")
    return errors


def source_errors(root: Path, files: list[Path]) -> list[str]:
    errors = []
    for path in files:
        if path.suffix not in TEXT_SUFFIXES and path.name not in {"LICENSE", ".gitignore", ".gitattributes"}:
            continue
        content = path.read_text(encoding="utf-8-sig")
        for description, pattern in SENSITIVE_PATTERNS.items():
            if pattern.search(content):
                # Report locations/categories only. Never echo a matching value.
                errors.append(f"{path.relative_to(root).as_posix()}: {description}")
    return errors


def version_errors(root: Path) -> list[str]:
    version = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))["project"]["version"]
    package = json.loads((root / "frontend/package.json").read_text(encoding="utf-8-sig"))
    lock = json.loads((root / "frontend/package-lock.json").read_text(encoding="utf-8-sig"))
    tree = ast.parse((root / "backend/roadlens/__init__.py").read_text(encoding="utf-8"))
    backend_version = next((ast.literal_eval(node.value) for node in tree.body if isinstance(node, ast.Assign)
                            and any(isinstance(target, ast.Name) and target.id == "__version__" for target in node.targets)), None)
    versions = [package["version"], lock["version"], lock["packages"][""]["version"], backend_version]
    return [] if all(value == version for value in versions) else ["Release versions differ between Python, frontend and npm lockfile."]


def check(root: Path = ROOT) -> tuple[list[Path], list[str]]:
    files = source_files(root)
    return files, markdown_errors(root, files) + source_errors(root, files) + version_errors(root)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    args = parser.parse_args()
    files, errors = check(args.root.resolve())
    for error in errors:
        print(error)
    print(f"Release source checks: {len(files)} files; {len(errors)} issue(s). "
          "Pattern scanning does not prove the absence of secrets; review staged files before publication.")
    return int(bool(errors))


if __name__ == "__main__":
    raise SystemExit(main())
