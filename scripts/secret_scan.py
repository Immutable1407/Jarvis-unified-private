#!/usr/bin/env python3
from __future__ import annotations
import re, sys
from pathlib import Path

ROOT = Path(sys.argv[1]) if len(sys.argv) > 1 else Path('.')
BAD_PATH_PARTS = {'data', 'reports', '__pycache__', '.pytest_cache', '.mypy_cache', '.git'}
BAD_SUFFIXES = {'.pyc', '.pem', '.key', '.db', '.sqlite', '.log', '.jsonl'}
SECRET_PATTERNS = [
    re.compile(r'(?i)(api[_-]?key|secret[_-]?key|passphrase|token|webhook|private[_-]?key)\s*=\s*["\'][^"\']{8,}["\']'),
    re.compile(r'-----BEGIN [A-Z ]*PRIVATE KEY-----'),
    re.compile(r'github_pat_[A-Za-z0-9_]+'),
    re.compile(r'sk-[A-Za-z0-9]{20,}'),
    re.compile(r'https://open\.feishu\.cn/open-apis/bot/v2/hook/[A-Za-z0-9-]+'),
]

path_findings: list[str] = []
content_findings: list[str] = []
for p in ROOT.rglob('*'):
    rel = p.relative_to(ROOT)
    if any(part in BAD_PATH_PARTS for part in rel.parts):
        if '.git' not in rel.parts:
            path_findings.append(str(rel))
        continue
    if p.is_file() and p.suffix in BAD_SUFFIXES:
        path_findings.append(str(rel))
        continue
    if not p.is_file():
        continue
    try:
        txt = p.read_text(errors='ignore')
    except Exception:
        continue
    for pat in SECRET_PATTERNS:
        for m in pat.finditer(txt):
            content_findings.append(f'{rel}: {m.group(0)[:120]}')

print(f'path_findings={len(path_findings)}')
for x in path_findings[:50]:
    print('PATH', x)
print(f'content_findings={len(content_findings)}')
for x in content_findings[:50]:
    print('CONTENT', x)
sys.exit(1 if path_findings or content_findings else 0)
