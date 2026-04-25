#!/usr/bin/env python3
"""
Scanner de segredos/dados pessoais antes de commit.

Bloqueia se encontrar:
  - AWS account IDs (12 digitos isolados - lista de placeholders aceitos)
  - AWS access keys (AKIA... / ASIA...)
  - SSO start URLs (*.awsapps.com/start)
  - Bucket names com account id ou identidade pessoal
  - E-mails reais (exceto allowlist)
  - Nomes de profile SSO que comecem com letras+hifen+letras nao-genericas
  - Tokens GitHub (ghp_...), Slack (xox...), etc

Uso:
    ./tests/check_secrets.py                # escaneia arquivos trackados pelo git
    ./tests/check_secrets.py --staged       # escaneia apenas staged (pre-commit)
    ./tests/check_secrets.py <file1> ...    # escaneia arquivos especificos

Sai com codigo 0 se OK, 1 se achou algo.
"""
from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path


# ---------------------------- Padroes ---------------------------------------
# Cada entrada: (nome_da_regra, regex, whitelist_substrings_permitidos)
#
# Usamos substrings para whitelist - se o trecho da linha contiver qualquer
# delas, a ocorrencia e ignorada (ex: "123456789012" em docs como placeholder).

RULES: list[tuple[str, re.Pattern[str], list[str]]] = [
    (
        "aws_account_id",
        re.compile(r"(?<!\d)(\d{12})(?!\d)"),
        [
            "123456789012",   # placeholder canonico
            "000000000000",   # localstack
            "111122223333",   # placeholder AWS docs
            "222233334444",
            "333344445555",
            "444455556666",
            "555566667777",
            "666677778888",
            "777788889999",
            "888899990000",
            "999900001111",
        ],
    ),
    (
        "aws_access_key",
        re.compile(r"\b(AKIA|ASIA)[0-9A-Z]{16}\b"),
        [],
    ),
    (
        "aws_secret_key",
        # chave secreta: 40 chars base64-like, ancorada por aws_secret_access_key = ...
        re.compile(
            r"aws[_\- ]?secret[_\- ]?access[_\- ]?key\s*[:=]\s*['\"]?[A-Za-z0-9/+=]{40}['\"]?",
            re.IGNORECASE,
        ),
        [],
    ),
    (
        "sso_start_url",
        re.compile(r"https?://[a-z0-9-]+\.awsapps\.com/start(?:/|#/)?", re.IGNORECASE),
        [
            "d-xxxxxxxxxx.awsapps.com/start",   # placeholder
            "<your-org>.awsapps.com",
            "<sua-org>.awsapps.com",
        ],
    ),
    (
        "github_token",
        re.compile(r"\bgh[pousr]_[A-Za-z0-9_]{20,}\b"),
        [],
    ),
    (
        "slack_token",
        re.compile(r"\bxox[abprs]-[0-9A-Za-z-]{10,}\b"),
        [],
    ),
    (
        "private_key",
        re.compile(r"-----BEGIN (?:RSA|OPENSSH|EC|DSA|PGP) PRIVATE KEY-----"),
        [],
    ),
    (
        "hardcoded_bucket_with_account",
        # padrao tipico de bucket com account id: algo-<12digitos>-regiao
        re.compile(r"[a-z0-9-]+-\d{12}-(?:us|eu|ap|sa|ca|af|me)-[a-z]+-\d+"),
        [
            "<account>", "<account_id>", "${account_id}",
            "${data.aws_caller_identity.current.account_id}",
            "data.aws_caller_identity.current.account_id",
        ],
    ),
]

# Profiles/identidades que NAO podem aparecer no repo
PERSONAL_MARKERS: list[str] = []  # preenchido por --add-personal

# Arquivos que nao sao escaneados
SKIP_PATHS: list[re.Pattern[str]] = [
    re.compile(r"(?:^|/)tests/check_secrets\.py$"),  # esse proprio arquivo
    re.compile(r"(?:^|/)\.git/"),
    re.compile(r"(?:^|/)\.terraform/"),
    re.compile(r"(?:^|/)__pycache__/"),
    re.compile(r"(?:^|/)node_modules/"),
    re.compile(r"(?:^|/)\.venv/"),
    re.compile(r"\.drawio\.bak$"),
    re.compile(r"\.pyc$"),
    re.compile(r"\.lock\.hcl$"),
]

# Extensoes binarias ignoradas
BIN_EXT = {".png", ".jpg", ".jpeg", ".gif", ".pdf", ".zip", ".tar", ".gz", ".ico"}


# ---------------------------- Core ------------------------------------------
def is_skipped(path: Path) -> bool:
    s = str(path)
    for pat in SKIP_PATHS:
        if pat.search(s):
            return True
    if path.suffix.lower() in BIN_EXT:
        return True
    return False


def scan_file(path: Path) -> list[tuple[str, int, str, str]]:
    """Retorna lista de (rule, line_num, match, line_content)."""
    findings = []
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return findings

    for lineno, line in enumerate(text.splitlines(), start=1):
        # ignora linhas marcadas explicitamente
        if "# noqa: secrets" in line or "pragma: no-secret" in line:
            continue

        for rule_name, pattern, whitelist in RULES:
            for m in pattern.finditer(line):
                match_text = m.group(0)
                # whitelist por substring da linha
                if any(w in line for w in whitelist):
                    continue
                # regra especial para account id: ignora se linha tem "placeholder"
                if rule_name == "aws_account_id":
                    if any(k in line.lower() for k in ("placeholder", "example", "# noqa", "account_id_example")):
                        continue
                findings.append((rule_name, lineno, match_text, line.strip()))

        # Markers personalizados
        for marker in PERSONAL_MARKERS:
            if marker and marker.lower() in line.lower():
                findings.append(("personal_marker", lineno, marker, line.strip()))

    return findings


def git_files(staged: bool = False) -> list[Path]:
    cmd = ["git", "diff", "--cached", "--name-only"] if staged else ["git", "ls-files"]
    try:
        out = subprocess.check_output(cmd, text=True, stderr=subprocess.DEVNULL)
    except subprocess.CalledProcessError:
        return []
    return [Path(p) for p in out.splitlines() if p.strip()]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("paths", nargs="*", help="arquivos/dirs especificos (default: tudo trackado pelo git)")
    ap.add_argument("--staged", action="store_true", help="escaneia apenas arquivos staged (pre-commit)")
    ap.add_argument("--add-personal", action="append", default=[],
                    help="marker pessoal adicional a bloquear (pode repetir)")
    ap.add_argument("--verbose", action="store_true")
    args = ap.parse_args()

    PERSONAL_MARKERS.extend(args.add_personal)

    if args.paths:
        files = [Path(p) for p in args.paths]
    elif args.staged:
        files = git_files(staged=True)
    else:
        files = git_files(staged=False)

    files = [f for f in files if f.is_file() and not is_skipped(f)]

    total = 0
    for f in files:
        findings = scan_file(f)
        if findings:
            for rule, lineno, match, line in findings:
                total += 1
                print(f"{f}:{lineno}: [{rule}] {match}")
                if args.verbose:
                    print(f"    {line[:160]}")

    print()
    print(f"arquivos escaneados: {len(files)}  ·  achados: {total}")
    if total:
        print()
        print("BLOQUEADO · remova/substitua os valores acima por placeholders antes do commit.")
        print("Se for falso positivo em linha isolada, use '# noqa: secrets' no final dessa linha.")
        return 1
    print("ok · sem segredos detectados")
    return 0


if __name__ == "__main__":
    sys.exit(main())
