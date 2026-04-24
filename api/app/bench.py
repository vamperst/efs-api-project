"""
Benchmark write/read no storage montado em /mnt/efs (que pode ser EFS real
ou S3 via Mountpoint, dependendo de STORAGE_VARIANT).

O mesmo codigo roda nos dois clusters - a unica coisa que muda e o que esta
de fato montado em /mnt/efs e o label `variant` nos logs/metricas.

Cada run gera um JSON em s3://<BENCH_RESULTS_BUCKET>/results/api/<variant>/<bench_id>.json
que o report_generator.py baixa e agrega.
"""
from __future__ import annotations

import json
import os
import random
import statistics
import time
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Literal

import boto3

from app.telemetry import Metrics, VARIANT, log, new_run_id, timed, tracer

BENCH_RESULTS_BUCKET = os.environ.get("BENCH_RESULTS_BUCKET", "")
AWS_REGION = os.environ.get("AWS_REGION", "us-east-1")

# Status compartilhado (simples, em memoria - suficiente para 1 worker por task)
# Se escalar, use DynamoDB ou S3 para status.
_runs: dict[str, "BenchResult"] = {}


@dataclass
class BenchResult:
    bench_id: str
    kind: Literal["write", "read"]
    variant: str
    status: Literal["running", "completed", "failed"] = "running"
    started_at: str = ""
    finished_at: str | None = None
    duration_s: float = 0.0
    target_gb: float = 0.0
    file_size_mb_min: int = 10
    file_size_mb_max: int = 500
    files_processed: int = 0
    total_bytes: int = 0
    latencies_ms: list[float] = field(default_factory=list)
    throughput_mb_per_s: float = 0.0
    error: str | None = None
    extras: dict[str, Any] = field(default_factory=dict)

    def summary(self) -> dict[str, Any]:
        d = asdict(self)
        if self.latencies_ms:
            d["lat_p50_ms"] = round(statistics.median(self.latencies_ms), 2)
            d["lat_p95_ms"] = round(_percentile(self.latencies_ms, 95), 2)
            d["lat_p99_ms"] = round(_percentile(self.latencies_ms, 99), 2)
            d["lat_max_ms"] = round(max(self.latencies_ms), 2)
        # evita dump gigante - so agregado
        d.pop("latencies_ms", None)
        return d


def _percentile(xs: list[float], p: float) -> float:
    if not xs:
        return 0.0
    s = sorted(xs)
    k = (len(s) - 1) * p / 100
    lo = int(k)
    hi = min(lo + 1, len(s) - 1)
    return s[lo] + (s[hi] - s[lo]) * (k - lo)


def get_run(bench_id: str) -> BenchResult | None:
    return _runs.get(bench_id)


def list_runs() -> list[dict[str, Any]]:
    return [r.summary() for r in sorted(_runs.values(), key=lambda x: x.started_at)]


# ------------------------------- write --------------------------------------
def run_bench_write(
    efs_root: Path,
    target_gb: float,
    min_mb: int,
    max_mb: int,
    subpath: str = "bench-write",
) -> str:
    """Inicia um benchmark de write. Retorna bench_id. Executa sincrono aqui -
    o endpoint HTTP dispara via BackgroundTasks."""
    bench_id = new_run_id()
    res = BenchResult(
        bench_id=bench_id,
        kind="write",
        variant=VARIANT,
        started_at=_now_iso(),
        target_gb=target_gb,
        file_size_mb_min=min_mb,
        file_size_mb_max=max_mb,
    )
    _runs[bench_id] = res

    dest = efs_root / subpath / bench_id
    dest.mkdir(parents=True, exist_ok=True)

    target_bytes = int(target_gb * (1024**3))
    min_bytes = min_mb * (1024**2)
    max_bytes = max_mb * (1024**2)

    log.info("bench.write.start", bench_id=bench_id, target_bytes=target_bytes, dest=str(dest))

    t_start = time.perf_counter()
    try:
        with tracer().start_as_current_span("bench.write", attributes={"bench_id": bench_id, "target_gb": target_gb}):
            while res.total_bytes < target_bytes:
                remaining = target_bytes - res.total_bytes
                size = random.randint(min_bytes, max_bytes)
                if size > remaining:
                    size = max(min_bytes, remaining)

                fn = dest / f"file-{res.files_processed:06d}.bin"
                t0 = time.perf_counter()
                _write_file(fn, size)
                latency_ms = (time.perf_counter() - t0) * 1000

                res.files_processed += 1
                res.total_bytes += size
                res.latencies_ms.append(latency_ms)

                # Metrica EMF por arquivo (granular)
                with Metrics(op="write") as m:
                    m.put("FileOpLatencyMs", latency_ms, "Milliseconds")
                    m.put("FileOpBytes", size, "Bytes")
                    m.prop("bench_id", bench_id)

                if res.files_processed % 20 == 0:
                    elapsed = time.perf_counter() - t_start
                    mbps = (res.total_bytes / (1024**2)) / max(elapsed, 0.001)
                    log.info(
                        "bench.write.progress",
                        bench_id=bench_id,
                        files=res.files_processed,
                        mb_written=round(res.total_bytes / (1024**2), 1),
                        mb_per_s=round(mbps, 1),
                    )

        res.duration_s = round(time.perf_counter() - t_start, 3)
        res.throughput_mb_per_s = round((res.total_bytes / (1024**2)) / max(res.duration_s, 0.001), 2)
        res.status = "completed"
        res.finished_at = _now_iso()

        # Metrica agregada de throughput
        with Metrics(op="write") as m:
            m.put("BenchWriteThroughputMBps", res.throughput_mb_per_s, "Megabytes/Second")
            m.put("BenchFiles", res.files_processed, "Count")
            m.put("BenchBytes", res.total_bytes, "Bytes")
            m.prop("bench_id", bench_id)
            m.prop("duration_s", res.duration_s)

        log.info("bench.write.done", **res.summary())
        _upload_result(res)
        return bench_id
    except Exception as e:
        res.status = "failed"
        res.error = str(e)
        res.finished_at = _now_iso()
        res.duration_s = round(time.perf_counter() - t_start, 3)
        log.exception("bench.write.failed", bench_id=bench_id, error=str(e))
        _upload_result(res)
        raise


# -------------------------------- read --------------------------------------
def run_bench_read(
    efs_root: Path,
    max_files: int | None = None,
    target_gb: float | None = None,
    subpath: str = "",
) -> str:
    """Le arquivos recursivamente ate atingir max_files ou target_gb."""
    bench_id = new_run_id()
    res = BenchResult(
        bench_id=bench_id,
        kind="read",
        variant=VARIANT,
        started_at=_now_iso(),
        target_gb=target_gb or 0.0,
    )
    _runs[bench_id] = res

    root = efs_root / subpath if subpath else efs_root
    if not root.is_dir():
        res.status = "failed"
        res.error = f"path nao existe: {root}"
        _upload_result(res)
        raise FileNotFoundError(res.error)

    log.info("bench.read.start", bench_id=bench_id, root=str(root), max_files=max_files, target_gb=target_gb)

    target_bytes = int((target_gb or 0) * (1024**3))
    t_start = time.perf_counter()

    try:
        with tracer().start_as_current_span("bench.read", attributes={"bench_id": bench_id}):
            for path in _walk(root):
                t0 = time.perf_counter()
                size = _read_file(path)
                latency_ms = (time.perf_counter() - t0) * 1000

                res.files_processed += 1
                res.total_bytes += size
                res.latencies_ms.append(latency_ms)

                with Metrics(op="read") as m:
                    m.put("FileOpLatencyMs", latency_ms, "Milliseconds")
                    m.put("FileOpBytes", size, "Bytes")
                    m.prop("bench_id", bench_id)

                if res.files_processed % 50 == 0:
                    elapsed = time.perf_counter() - t_start
                    mbps = (res.total_bytes / (1024**2)) / max(elapsed, 0.001)
                    log.info(
                        "bench.read.progress",
                        bench_id=bench_id,
                        files=res.files_processed,
                        mb_read=round(res.total_bytes / (1024**2), 1),
                        mb_per_s=round(mbps, 1),
                    )

                if max_files and res.files_processed >= max_files:
                    break
                if target_bytes and res.total_bytes >= target_bytes:
                    break

        res.duration_s = round(time.perf_counter() - t_start, 3)
        res.throughput_mb_per_s = round((res.total_bytes / (1024**2)) / max(res.duration_s, 0.001), 2)
        res.status = "completed"
        res.finished_at = _now_iso()

        with Metrics(op="read") as m:
            m.put("BenchReadThroughputMBps", res.throughput_mb_per_s, "Megabytes/Second")
            m.put("BenchFiles", res.files_processed, "Count")
            m.put("BenchBytes", res.total_bytes, "Bytes")
            m.prop("bench_id", bench_id)
            m.prop("duration_s", res.duration_s)

        log.info("bench.read.done", **res.summary())
        _upload_result(res)
        return bench_id
    except Exception as e:
        res.status = "failed"
        res.error = str(e)
        res.finished_at = _now_iso()
        res.duration_s = round(time.perf_counter() - t_start, 3)
        log.exception("bench.read.failed", bench_id=bench_id, error=str(e))
        _upload_result(res)
        raise


# ---------------------------- io primitives ---------------------------------
_CHUNK = 4 * 1024 * 1024  # 4 MiB


def _write_file(path: Path, size_bytes: int) -> None:
    """Escreve payload pseudo-aleatorio em blocos de 4 MiB.
    Usa os.urandom somente no primeiro chunk (evita custo de RNG puro
    e ainda garante que nao e um arquivo de zeros - o que poderia enviesar
    S3 client-side compression).
    """
    seed = os.urandom(_CHUNK)
    remaining = size_bytes
    with path.open("wb", buffering=0) as fh:
        while remaining > 0:
            chunk_size = min(_CHUNK, remaining)
            fh.write(seed[:chunk_size] if chunk_size <= len(seed) else seed)
            remaining -= chunk_size
        fh.flush()


def _read_file(path: Path) -> int:
    total = 0
    with path.open("rb", buffering=0) as fh:
        while True:
            b = fh.read(_CHUNK)
            if not b:
                break
            total += len(b)
    return total


def _walk(root: Path):
    """Gera apenas arquivos regulares (nao dirs)."""
    for p in root.rglob("*"):
        if p.is_file():
            yield p


# ---------------------------- result publishing -----------------------------
def _now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _upload_result(res: BenchResult) -> None:
    if not BENCH_RESULTS_BUCKET:
        log.warning("bench.result.skip_upload", reason="BENCH_RESULTS_BUCKET vazio")
        return

    key = f"results/api/{res.variant}/{res.bench_id}.json"
    body = json.dumps(res.summary(), indent=2).encode()
    try:
        with timed("s3.put_result", bucket=BENCH_RESULTS_BUCKET, key=key):
            boto3.client("s3", region_name=AWS_REGION).put_object(
                Bucket=BENCH_RESULTS_BUCKET,
                Key=key,
                Body=body,
                ContentType="application/json",
            )
        log.info("bench.result.uploaded", bucket=BENCH_RESULTS_BUCKET, key=key, bytes=len(body))
    except Exception as e:
        log.exception("bench.result.upload_failed", error=str(e))
