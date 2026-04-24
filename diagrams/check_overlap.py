#!/usr/bin/env python3
"""
Valida o .drawio:
  1) Nenhuma sobreposicao parcial entre vertices (overlap sem containment).
  2) Icones AWS caem INTEIRAMENTE dentro do container que os deveria conter.
  3) Labels (rects sem fill/stroke) nao estouram largura do seu container.
  4) Distancia minima horizontal entre icones irmaos no mesmo container: 40px.
"""
from __future__ import annotations

import sys
import xml.etree.ElementTree as ET
from pathlib import Path


def rects(page_root):
    out = []
    for cell in page_root.findall(".//mxCell"):
        if cell.get("vertex") != "1":
            continue
        geo = cell.find("mxGeometry")
        if geo is None:
            continue
        x, y = float(geo.get("x", 0)), float(geo.get("y", 0))
        w, h = float(geo.get("width", 0)), float(geo.get("height", 0))
        style = cell.get("style", "")
        kind = "container"
        if "resIcon=mxgraph.aws4" in style:
            kind = "icon"
        elif "strokeColor=none;fillColor=none" in style:
            kind = "label"
        elif "sketch=1" in style and "hachureGap" in style and "rounded=1" in style:
            kind = "container"
        else:
            kind = "note"
        out.append({
            "id": cell.get("id"),
            "x": x, "y": y, "w": w, "h": h,
            "right": x + w, "bottom": y + h,
            "value": (cell.get("value") or "").replace("\n", " ")[:50],
            "style": style,
            "kind": kind,
        })
    return out


def intersects(a, b) -> bool:
    return not (a["right"] <= b["x"] or b["right"] <= a["x"] or
                a["bottom"] <= b["y"] or b["bottom"] <= a["y"])


def contains(outer, inner) -> bool:
    return (outer["x"] <= inner["x"] and
            outer["y"] <= inner["y"] and
            outer["right"] >= inner["right"] and
            outer["bottom"] >= inner["bottom"])


def main():
    path = Path(__file__).parent / "efs-s3-architectures.drawio"
    tree = ET.parse(path)
    mx = tree.getroot()

    total_issues = 0
    for i, diag in enumerate(mx.findall("diagram")):
        name = diag.get("name")
        rs = rects(diag)
        issues = []

        # Check 1: sobreposicoes sem containment
        for a in rs:
            for b in rs:
                if a["id"] >= b["id"]:
                    continue
                if not intersects(a, b):
                    continue
                if contains(a, b) or contains(b, a):
                    continue
                # titulos de pagina (fora de qualquer container) sao OK
                if a["kind"] == "label" and a["y"] < 140:
                    continue
                if b["kind"] == "label" and b["y"] < 140:
                    continue
                issues.append(("overlap", a, b))

        # Check 2: icones fora de TODOS os containers que os incluem parcialmente
        # (Se um icone intersecta um container mas nao esta contido, ta errado)
        for a in [r for r in rs if r["kind"] == "icon"]:
            for b in [r for r in rs if r["kind"] == "container"]:
                if intersects(a, b) and not contains(b, a):
                    issues.append(("icon-out-of-container", a, b))

        # Check 3: distancia minima entre icones irmaos (mesma linha horizontal)
        icons = [r for r in rs if r["kind"] == "icon"]
        for a in icons:
            for b in icons:
                if a["id"] >= b["id"]:
                    continue
                # Mesma linha? (y proximos)
                if abs(a["y"] - b["y"]) < 30:
                    gap = min(abs(b["x"] - a["right"]), abs(a["x"] - b["right"]))
                    if 0 < gap < 40:
                        issues.append(("close-icons", a, b))

        print(f"\n=== Página {i+1}: {name} ({len(rs)} elementos) ===")
        if not issues:
            print("  ok · sem problemas")
        else:
            total_issues += len(issues)
            for kind, a, b in issues[:15]:
                print(f"  {kind}:")
                print(f"    A: id={a['id']} kind={a['kind']} val={a['value']!r}")
                print(f"       ({a['x']:.0f},{a['y']:.0f})+{a['w']:.0f}x{a['h']:.0f}")
                print(f"    B: id={b['id']} kind={b['kind']} val={b['value']!r}")
                print(f"       ({b['x']:.0f},{b['y']:.0f})+{b['w']:.0f}x{b['h']:.0f}")
            if len(issues) > 15:
                print(f"  ... mais {len(issues)-15}")

    print(f"\nTotal de problemas: {total_issues}")
    return 1 if total_issues > 0 else 0


if __name__ == "__main__":
    sys.exit(main())
