#!/usr/bin/env python3
"""
Gera um HTML de relatorio comparando EFS vs S3.

Baixa os JSONs de:
    s3://<bucket>/results/api/efs/*.json
    s3://<bucket>/results/api/s3/*.json
    s3://<bucket>/results/populator/*.json
    s3://<bucket>/results/migrator/*.json

Agrega, compara, e escreve:
    ./report-<timestamp>.html         (autocontido, graficos Chart.js via CDN)
    ./report-<timestamp>.raw.json     (dump bruto p/ auditoria)

Uso:
    # descobrir o bucket a partir do Terraform
    BUCKET=$(cd ../terraform/08-observability && terraform output -raw results_bucket_name)
    python3 generate_report.py --bucket $BUCKET --region us-east-1

    # ou baixar incremental (ja tem 03 no disco, quer adicionar 06)
    python3 generate_report.py --bucket $BUCKET --variant s3
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from collections import defaultdict
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

import boto3
from jinja2 import Template


def fetch_all(bucket: str, region: str, prefix: str) -> list[dict[str, Any]]:
    """Baixa e parseia todos os JSONs sob `prefix`."""
    s3 = boto3.client("s3", region_name=region)
    paginator = s3.get_paginator("list_objects_v2")
    items = []
    for page in paginator.paginate(Bucket=bucket, Prefix=prefix):
        for obj in page.get("Contents") or []:
            key = obj["Key"]
            if not key.endswith(".json"):
                continue
            body = s3.get_object(Bucket=bucket, Key=key)["Body"].read()
            try:
                items.append(json.loads(body))
            except json.JSONDecodeError:
                print(f"[WARN] JSON invalido: {key}", file=sys.stderr)
    return items


def stats(values: list[float]) -> dict[str, float]:
    if not values:
        return {"count": 0}
    s = sorted(values)
    return {
        "count": len(s),
        "min": round(min(s), 3),
        "max": round(max(s), 3),
        "avg": round(sum(s) / len(s), 3),
        "median": round(s[len(s) // 2], 3),
        "p95": round(s[int(len(s) * 0.95) - 1] if len(s) > 1 else s[0], 3),
        "p99": round(s[int(len(s) * 0.99) - 1] if len(s) > 1 else s[0], 3),
    }


def summarize_api(runs: list[dict[str, Any]]) -> dict[str, dict[str, dict[str, float]]]:
    """Agrega por variant x kind (write/read)."""
    buckets: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for r in runs:
        if r.get("status") != "completed":
            continue
        buckets[(r.get("variant", "?"), r.get("kind", "?"))].append(r)

    summary: dict[str, dict[str, dict[str, float]]] = {}
    for (variant, kind), rs in buckets.items():
        durations = [r["duration_s"] for r in rs]
        mbps = [r["throughput_mb_per_s"] for r in rs]
        files = [r["files_processed"] for r in rs]
        bytes_total = [r["total_bytes"] for r in rs]
        p50 = [r.get("lat_p50_ms", 0) for r in rs]
        p99 = [r.get("lat_p99_ms", 0) for r in rs]

        summary.setdefault(variant, {})[kind] = {
            "runs": len(rs),
            "duration_s": stats(durations),
            "throughput_mb_per_s": stats(mbps),
            "files_processed": stats(files),
            "total_bytes": stats(bytes_total),
            "lat_p50_ms": stats(p50),
            "lat_p99_ms": stats(p99),
            "raw": rs,
        }
    return summary


TEMPLATE = """<!DOCTYPE html>
<html lang="pt-BR">
<head>
<meta charset="UTF-8">
<title>Relatorio EFS vs S3 - {{ generated_at }}</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.4/dist/chart.umd.min.js"></script>
<style>
  body { font-family: -apple-system, "Segoe UI", Helvetica, Arial, sans-serif;
         max-width: 1200px; margin: 2em auto; padding: 0 1em; color: #222; }
  h1, h2, h3 { border-bottom: 1px solid #ccc; padding-bottom: 0.3em; }
  .grid { display: grid; grid-template-columns: 1fr 1fr; gap: 2em; }
  .card { padding: 1em; border: 1px solid #ddd; border-radius: 8px; background: #fafafa; }
  table { border-collapse: collapse; width: 100%; margin: 1em 0; font-size: 0.9em; }
  th, td { border: 1px solid #ddd; padding: 0.4em 0.7em; text-align: right; }
  th { background: #eef; text-align: center; }
  td:first-child { text-align: left; font-weight: 600; }
  .winner { background: #dfd; }
  .loser  { background: #fdd; }
  canvas { background: #fff; border: 1px solid #eee; padding: 0.5em; border-radius: 4px; }
  .meta { color: #666; font-size: 0.85em; }
  .kpi { font-size: 1.4em; font-weight: 600; }
  .kpi.up { color: #0a0; } .kpi.down { color: #a00; }
</style>
</head>
<body>

<h1>EFS vs S3 — Relatorio de Benchmark</h1>
<p class="meta">Gerado em {{ generated_at }} | runs: API={{ total_api_runs }}, Populator={{ total_populator_runs }}, Migrator={{ total_migrator_runs }}</p>

<h2>1. Resumo executivo</h2>
<div class="grid">
  {% for kind in ["write", "read"] %}
  <div class="card">
    <h3>{{ kind | upper }} — throughput medio (MB/s)</h3>
    {% set e = api.get("efs", {}).get(kind, {}).get("throughput_mb_per_s", {}).get("avg", 0) %}
    {% set s = api.get("s3",  {}).get(kind, {}).get("throughput_mb_per_s", {}).get("avg", 0) %}
    <p>EFS: <span class="kpi">{{ "%.1f"|format(e) }}</span> MB/s<br>
       S3:&nbsp; <span class="kpi">{{ "%.1f"|format(s) }}</span> MB/s</p>
    {% if e and s %}
    <p>Variacao S3 vs EFS:
      {% set delta = (s - e) / e * 100 %}
      <span class="kpi {{ 'up' if delta > 0 else 'down' }}">{{ "%+.1f"|format(delta) }}%</span>
    </p>
    {% endif %}
  </div>
  {% endfor %}
</div>

<h2>2. Throughput por operacao</h2>
<div class="grid">
  <canvas id="chart-write" height="220"></canvas>
  <canvas id="chart-read" height="220"></canvas>
</div>

<h2>3. Latencia por arquivo (p50/p99, ms)</h2>
<canvas id="chart-lat" height="220"></canvas>

<h2>4. Tabela detalhada</h2>
<table>
  <thead>
    <tr>
      <th>Variant</th><th>Op</th><th>Runs</th>
      <th>Dur media (s)</th>
      <th>Throughput medio (MB/s)</th>
      <th>Throughput p99 (MB/s)</th>
      <th>Lat p50 (ms)</th>
      <th>Lat p99 (ms)</th>
      <th>Files processados</th>
      <th>Total (GB)</th>
    </tr>
  </thead>
  <tbody>
    {% for variant, kinds in api.items() %}
      {% for kind, s in kinds.items() %}
      <tr>
        <td>{{ variant }}</td>
        <td>{{ kind }}</td>
        <td>{{ s.runs }}</td>
        <td>{{ "%.2f"|format(s.duration_s.avg) }}</td>
        <td>{{ "%.2f"|format(s.throughput_mb_per_s.avg) }}</td>
        <td>{{ "%.2f"|format(s.throughput_mb_per_s.p99) }}</td>
        <td>{{ "%.2f"|format(s.lat_p50_ms.avg) }}</td>
        <td>{{ "%.2f"|format(s.lat_p99_ms.avg) }}</td>
        <td>{{ "%.0f"|format(s.files_processed.avg) }}</td>
        <td>{{ "%.2f"|format(s.total_bytes.avg / 1073741824) }}</td>
      </tr>
      {% endfor %}
    {% endfor %}
  </tbody>
</table>

<h2>5. Migracao EFS -> S3</h2>
{% if migrator_runs %}
<table>
  <thead>
    <tr><th>run_id</th><th>source</th><th>destination</th><th>Duracao (s)</th>
    <th>Total (GB)</th><th>Throughput (MB/s)</th><th>Status</th></tr>
  </thead>
  <tbody>
    {% for r in migrator_runs %}
    <tr>
      <td>{{ r.run_id[:8] }}</td>
      <td>{{ r.source }}</td>
      <td>{{ r.destination }}</td>
      <td>{{ "%.1f"|format(r.duration_s) }}</td>
      <td>{{ "%.2f"|format((r.total_bytes or 0) / 1073741824) }}</td>
      <td>{{ "%.1f"|format(r.throughput_mb_per_s or 0) }}</td>
      <td>{{ r.status }}</td>
    </tr>
    {% endfor %}
  </tbody>
</table>
{% else %}
<p class="meta">Nenhuma migracao registrada.</p>
{% endif %}

<h2>6. Populador (fonte de dados)</h2>
{% if populator_runs %}
<table>
  <thead>
    <tr><th>run_id</th><th>dataset</th><th>Target (GB)</th><th>Total records</th>
    <th>Parts</th><th>Duracao (s)</th><th>Throughput (MB/s)</th></tr>
  </thead>
  <tbody>
    {% for r in populator_runs %}
    <tr>
      <td>{{ r.run_id[:8] }}</td>
      <td>{{ r.dataset }}</td>
      <td>{{ "%.1f"|format(r.target_gb) }}</td>
      <td>{{ r.total_records }}</td>
      <td>{{ r.num_parts }}</td>
      <td>{{ "%.1f"|format(r.duration_s) }}</td>
      <td>{{ "%.1f"|format(r.throughput_mb_per_s) }}</td>
    </tr>
    {% endfor %}
  </tbody>
</table>
{% else %}
<p class="meta">Nenhum run de populador.</p>
{% endif %}

<h2>7. Runs individuais (API)</h2>
<details><summary>Clique para ver o JSON bruto das {{ total_api_runs }} runs</summary>
<pre style="max-height: 400px; overflow: auto; background: #f4f4f4; padding: 1em;">{{ all_api_runs_json }}</pre>
</details>

<script>
const chartOpts = { scales: { y: { beginAtZero: true, title: { display: true } } },
                    plugins: { legend: { position: 'bottom' } } };

new Chart(document.getElementById('chart-write'), {
  type: 'bar',
  data: {
    labels: ['avg', 'p50', 'p95', 'p99'],
    datasets: [
      { label: 'EFS', data: {{ write_efs_series }}, backgroundColor: 'rgba(70,130,180,0.7)' },
      { label: 'S3',  data: {{ write_s3_series  }}, backgroundColor: 'rgba(255,140,0,0.7)' },
    ]
  },
  options: { ...chartOpts, plugins: { ...chartOpts.plugins, title: { display: true, text: 'Write throughput (MB/s)' } } }
});

new Chart(document.getElementById('chart-read'), {
  type: 'bar',
  data: {
    labels: ['avg', 'p50', 'p95', 'p99'],
    datasets: [
      { label: 'EFS', data: {{ read_efs_series }}, backgroundColor: 'rgba(70,130,180,0.7)' },
      { label: 'S3',  data: {{ read_s3_series  }}, backgroundColor: 'rgba(255,140,0,0.7)' },
    ]
  },
  options: { ...chartOpts, plugins: { ...chartOpts.plugins, title: { display: true, text: 'Read throughput (MB/s)' } } }
});

new Chart(document.getElementById('chart-lat'), {
  type: 'bar',
  data: {
    labels: ['write p50', 'write p99', 'read p50', 'read p99'],
    datasets: [
      { label: 'EFS', data: {{ lat_efs_series }}, backgroundColor: 'rgba(70,130,180,0.7)' },
      { label: 'S3',  data: {{ lat_s3_series  }}, backgroundColor: 'rgba(255,140,0,0.7)' },
    ]
  },
  options: { ...chartOpts, plugins: { ...chartOpts.plugins, title: { display: true, text: 'Latencia por arquivo (ms, menor e melhor)' } } }
});
</script>
</body>
</html>
"""


def get_series(api: dict, variant: str, kind: str, metric: str, stats_keys: list[str]) -> list[float]:
    s = api.get(variant, {}).get(kind, {}).get(metric, {})
    return [s.get(k, 0) for k in stats_keys]


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    p.add_argument("--bucket", required=True, help="bucket de results (output da stack 08)")
    p.add_argument("--region", default=os.environ.get("AWS_REGION", "us-east-1"))
    p.add_argument("--out", default=None, help="path do HTML (default: report-<ts>.html)")
    p.add_argument("--variant", default=None, help="baixar so essa variant (efs|s3|all)")
    args = p.parse_args()

    ts = time.strftime("%Y%m%d-%H%M%S", time.gmtime())
    out = args.out or f"report-{ts}.html"

    variants = [args.variant] if args.variant and args.variant != "all" else ["efs", "s3"]

    print(f"==> baixando de s3://{args.bucket}/results/ ...")
    api_runs: list[dict[str, Any]] = []
    for v in variants:
        api_runs.extend(fetch_all(args.bucket, args.region, f"results/api/{v}/"))
    populator_runs = fetch_all(args.bucket, args.region, "results/populator/")
    migrator_runs = fetch_all(args.bucket, args.region, "results/migrator/")

    print(f"    api runs: {len(api_runs)}")
    print(f"    populator runs: {len(populator_runs)}")
    print(f"    migrator runs: {len(migrator_runs)}")

    api_summary = summarize_api(api_runs)

    stat_cols = ["avg", "median", "p95", "p99"]
    write_efs = get_series(api_summary, "efs", "write", "throughput_mb_per_s", stat_cols)
    write_s3  = get_series(api_summary, "s3",  "write", "throughput_mb_per_s", stat_cols)
    read_efs  = get_series(api_summary, "efs", "read",  "throughput_mb_per_s", stat_cols)
    read_s3   = get_series(api_summary, "s3",  "read",  "throughput_mb_per_s", stat_cols)

    lat_efs = [
        api_summary.get("efs", {}).get("write", {}).get("lat_p50_ms", {}).get("avg", 0),
        api_summary.get("efs", {}).get("write", {}).get("lat_p99_ms", {}).get("avg", 0),
        api_summary.get("efs", {}).get("read",  {}).get("lat_p50_ms", {}).get("avg", 0),
        api_summary.get("efs", {}).get("read",  {}).get("lat_p99_ms", {}).get("avg", 0),
    ]
    lat_s3 = [
        api_summary.get("s3", {}).get("write", {}).get("lat_p50_ms", {}).get("avg", 0),
        api_summary.get("s3", {}).get("write", {}).get("lat_p99_ms", {}).get("avg", 0),
        api_summary.get("s3", {}).get("read",  {}).get("lat_p50_ms", {}).get("avg", 0),
        api_summary.get("s3", {}).get("read",  {}).get("lat_p99_ms", {}).get("avg", 0),
    ]

    rendered = Template(TEMPLATE).render(
        generated_at=time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime()),
        api={v: {k: {kk: vv for kk, vv in s.items() if kk != "raw"} for k, s in kinds.items()}
             for v, kinds in api_summary.items()},
        total_api_runs=len(api_runs),
        total_populator_runs=len(populator_runs),
        total_migrator_runs=len(migrator_runs),
        populator_runs=populator_runs,
        migrator_runs=migrator_runs,
        write_efs_series=json.dumps(write_efs),
        write_s3_series=json.dumps(write_s3),
        read_efs_series=json.dumps(read_efs),
        read_s3_series=json.dumps(read_s3),
        lat_efs_series=json.dumps(lat_efs),
        lat_s3_series=json.dumps(lat_s3),
        all_api_runs_json=json.dumps(api_runs, indent=2),
    )

    Path(out).write_text(rendered, encoding="utf-8")
    raw_path = out.replace(".html", ".raw.json")
    Path(raw_path).write_text(json.dumps({
        "api_runs": api_runs,
        "populator_runs": populator_runs,
        "migrator_runs": migrator_runs,
        "api_summary": {v: {k: {kk: vv for kk, vv in s.items() if kk != "raw"}
                            for k, s in kinds.items()}
                        for v, kinds in api_summary.items()},
    }, indent=2))

    print(f"==> relatorio: {out}")
    print(f"==> raw:       {raw_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
