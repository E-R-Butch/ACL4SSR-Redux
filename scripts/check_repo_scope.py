"""Prevent deployment-specific code and obvious secrets from entering this public repository."""

import pathlib
import re
import sys


REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
CODE_ROOTS = ("Config", "Legacy", "scripts", "tests", ".github")
ROOT_TEXT_FILES = ("README.md", "Help.md", "ROADMAP.md", "requirements-dev.txt")
TEXT_SUFFIXES = {".ini", ".md", ".py", ".sh", ".txt", ".yaml", ".yml"}
DEPLOYMENT_PATTERNS = {
    "external control-plane reference": re.compile("mar" + "zban", re.IGNORECASE),
    "forbidden deployment alias": re.compile("jp" + "pro", re.IGNORECASE),
    "panel deployment hostname": re.compile(r"panel\.[a-z0-9.-]+", re.IGNORECASE),
    "direct SSH deployment command": re.compile(r"\bssh\s+(?:-[^\s]+\s+)*[^\s]+@", re.IGNORECASE),
}
SECRET_PATTERNS = {
    "private key": re.compile("BEGIN " + "PRIVATE KEY"),
    "assigned password": re.compile(r"(?i)\bpassword\s*=\s*['\"][^'\"]+['\"]"),
    "assigned token": re.compile(r"(?i)\b(?:access_?token|api_?token)\s*=\s*['\"][^'\"]+['\"]"),
}


def iter_text_files(roots):
    for filename in ROOT_TEXT_FILES:
        path = REPO_ROOT / filename
        if path.is_file():
            yield path
    for root_name in roots:
        root = REPO_ROOT / root_name
        if not root.exists():
            continue
        for path in root.rglob("*"):
            if path.is_file() and path.suffix.lower() in TEXT_SUFFIXES and path.name != pathlib.Path(__file__).name:
                yield path


def scan_file(path, patterns):
    findings = []
    for lineno, line in enumerate(path.read_text(encoding="utf-8", errors="replace").splitlines(), start=1):
        for label, pattern in patterns.items():
            if pattern.search(line):
                findings.append(f"{path.relative_to(REPO_ROOT)}:{lineno}: {label}")
    return findings


def main():
    findings = []
    for path in iter_text_files(CODE_ROOTS):
        findings.extend(scan_file(path, DEPLOYMENT_PATTERNS))
        findings.extend(scan_file(path, SECRET_PATTERNS))

    if findings:
        for finding in findings:
            print(f"[!] {finding}")
        print(f"[!] Repository scope check failed with {len(findings)} finding(s)")
        sys.exit(1)
    print("[*] Repository scope check completed successfully!")


if __name__ == "__main__":
    main()
