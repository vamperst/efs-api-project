#!/usr/bin/env python3
"""
Validador estatico das stacks Terraform.

Checa:
  1) local.X, var.X, data.<t>.<n> referenciados existem.
  2) Contrato SSM: data "aws_ssm_parameter" tem producer "aws_ssm_parameter".
     Resolve interpolacoes `${local.X}` dentro dos nomes SSM antes de comparar.

Exit 0 = ok, 1 = erros.
"""
from __future__ import annotations

import re
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / "terraform"

RE_LOCAL_REF = re.compile(r'\blocal\.([a-zA-Z_][a-zA-Z0-9_]*)')
RE_VAR_REF = re.compile(r'\bvar\.([a-zA-Z_][a-zA-Z0-9_]*)')
RE_DATA_REF = re.compile(r'\bdata\.([a-zA-Z_][a-zA-Z0-9_]*)\.([a-zA-Z_][a-zA-Z0-9_]*)')


def strip_comments(s: str) -> str:
    out = []
    i = 0
    in_str = False
    while i < len(s):
        c = s[i]
        if c == '"' and (i == 0 or s[i-1] != "\\"):
            in_str = not in_str
            out.append(c); i += 1; continue
        if not in_str:
            if s[i:i+2] == "//" or c == "#":
                while i < len(s) and s[i] != "\n":
                    i += 1
                continue
            if s[i:i+2] == "/*":
                j = s.find("*/", i+2)
                i = (j + 2) if j != -1 else len(s)
                continue
        out.append(c); i += 1
    return "".join(out)


def iter_top_blocks(text: str):
    """Gera (header, body) para cada `<header> { body }` top-level."""
    text = strip_comments(text)
    i, n = 0, len(text)
    while i < n:
        while i < n and text[i] in " \t\r\n":
            i += 1
        if i >= n:
            break
        start = i
        in_str = False
        while i < n:
            c = text[i]
            if c == '"' and text[i-1] != "\\":
                in_str = not in_str
            if not in_str and c == "{":
                header = text[start:i].strip()
                body_start = i + 1
                depth = 1
                i += 1
                while i < n and depth > 0:
                    c2 = text[i]
                    if c2 == '"' and text[i-1] != "\\":
                        in_str = not in_str
                    if not in_str:
                        if c2 == "{": depth += 1
                        elif c2 == "}": depth -= 1
                    i += 1
                yield header, text[body_start:i-1]
                break
            i += 1


def parse_top_keys(body: str) -> list[tuple[str, str]]:
    """Retorna (key, value) top-level (depth==0) no body.
    Valores multi-line (objetos) sao captados ate o seguinte `\\n` com depth voltando a 0."""
    out = []
    lines = body.split("\n")
    depth_start = 0  # depth no inicio da linha
    current_key = None
    current_val_lines: list[str] = []

    for line in lines:
        if current_key is None:
            if depth_start == 0:
                m = re.match(r'^\s*([a-zA-Z_][a-zA-Z0-9_]*)\s*=\s*(.*)$', line)
                if m:
                    current_key = m.group(1)
                    current_val_lines = [m.group(2)]
                    # ve se terminou nessa linha
                    open_b = line.count("{") - line.count("}")
                    open_s = line.count("[") - line.count("]")
                    if open_b == 0 and open_s == 0:
                        out.append((current_key, "\n".join(current_val_lines).strip()))
                        current_key = None
                        current_val_lines = []
        else:
            current_val_lines.append(line)
            # computa depth de toda a expressao acumulada
            full = "\n".join(current_val_lines)
            open_b = full.count("{") - full.count("}")
            open_s = full.count("[") - full.count("]")
            if open_b == 0 and open_s == 0:
                out.append((current_key, full.strip()))
                current_key = None
                current_val_lines = []
        depth_start += line.count("{") - line.count("}")

    return out


def collect_stack(stack_dir: Path) -> dict:
    variables = set()
    locals_: dict[str, str] = {}  # name -> value (string)
    data_sources = set()
    ssm_producers_raw: set[str] = set()   # "name" expr literal (pode ter ${...})
    ssm_consumers_raw: set[str] = set()
    full_text = ""

    for tf in sorted(stack_dir.glob("*.tf")):
        txt = strip_comments(tf.read_text())
        full_text += "\n" + txt

        for header, body in iter_top_blocks(txt):
            toks = header.split()
            if not toks:
                continue
            kind = toks[0]

            if kind == "variable" and len(toks) >= 2:
                variables.add(toks[1].strip('"'))

            elif kind == "locals":
                for k, v in parse_top_keys(body):
                    locals_[k] = v

            elif kind == "data" and len(toks) >= 3:
                t = toks[1].strip('"')
                n = toks[2].strip('"')
                data_sources.add(f"{t}.{n}")
                if t == "aws_ssm_parameter":
                    for k, v in parse_top_keys(body):
                        if k == "name":
                            ssm_consumers_raw.add(_unquote(v))

            elif kind == "resource" and len(toks) >= 3:
                t = toks[1].strip('"')
                if t == "aws_ssm_parameter":
                    for k, v in parse_top_keys(body):
                        if k == "name":
                            ssm_producers_raw.add(_unquote(v))

    return {
        "name": stack_dir.name,
        "variables": variables,
        "locals": locals_,
        "data_sources": data_sources,
        "ssm_producers_raw": ssm_producers_raw,
        "ssm_consumers_raw": ssm_consumers_raw,
        "text": full_text,
    }


def _unquote(s: str) -> str:
    s = s.strip()
    if s.startswith('"') and s.endswith('"'):
        return s[1:-1]
    return s


def _resolve_locals(raw: str, locals_: dict[str, str]) -> str:
    """Expande ${local.X} usando o valor coletado. Max 3 passadas."""
    for _ in range(3):
        new = raw
        for name, val in locals_.items():
            # val eh a expressao string (ainda com aspas). Extrai literal:
            v = _unquote(val)
            new = new.replace("${local." + name + "}", v)
        if new == raw:
            break
        raw = new
    return raw


def norm_ssm(key: str) -> str:
    return key.replace("${var.project}", "<P>").replace("${var.env}", "<E>")


def check_stack(s: dict) -> list[str]:
    errs = []
    txt = s["text"]
    name = s["name"]

    decl_locals = set(s["locals"].keys())
    for ref in set(RE_LOCAL_REF.findall(txt)):
        if ref not in decl_locals:
            errs.append(f"{name}: local.{ref} nao declarado")

    for ref in set(RE_VAR_REF.findall(txt)):
        if ref not in s["variables"]:
            errs.append(f"{name}: var.{ref} nao declarado")

    for t, n in set(RE_DATA_REF.findall(txt)):
        if f"{t}.{n}" not in s["data_sources"]:
            errs.append(f"{name}: data.{t}.{n} nao declarado")

    return errs


def main() -> int:
    stacks = {}
    for d in sorted(ROOT.iterdir()):
        if d.is_dir():
            stacks[d.name] = collect_stack(d)

    # Per-stack
    all_errors = []
    for name, s in stacks.items():
        all_errors.extend(check_stack(s))

    # Contrato SSM: resolve ${local.X} em cada producer/consumer usando locals
    # DA STACK QUE DECLAROU, depois normaliza ${var.project}/${var.env}.
    produced = set()
    for s in stacks.values():
        for raw in s["ssm_producers_raw"]:
            resolved = _resolve_locals(raw, s["locals"])
            produced.add(norm_ssm(resolved))

    total_consumed = 0
    for name, s in stacks.items():
        for raw in s["ssm_consumers_raw"]:
            total_consumed += 1
            resolved = _resolve_locals(raw, s["locals"])
            nk = norm_ssm(resolved)
            if nk.startswith("/aws/"):
                continue
            if nk not in produced:
                all_errors.append(f"{name}: SSM '{raw}' (resolvido='{nk}') sem producer")

    print(f"==> {len(stacks)} stacks | {len(produced)} SSM produzidos | {total_consumed} consumos")

    if all_errors:
        print()
        print(f"ERROS ({len(all_errors)}):")
        for e in all_errors:
            print(f"  - {e}")
        return 1

    print()
    print("ok - sem referencias quebradas")
    return 0


if __name__ == "__main__":
    sys.exit(main())
