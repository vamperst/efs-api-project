"""
API FastAPI que le/escreve arquivos no storage montado em EFS_MOUNT_PATH.

O mesmo codigo roda no cluster 03 (EFS) e no cluster 06 (S3 via Mountpoint).
A variant e identificada por STORAGE_VARIANT (env) - usada em labels de
logs/metricas e no bucket path dos resultados.
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

from fastapi import BackgroundTasks, FastAPI, HTTPException, Query, Response, UploadFile
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel, Field

from app import bench
from app.telemetry import (
    VARIANT,
    init_logging,
    init_metrics,
    init_tracing,
    instrument_fastapi,
    log,
    timed,
    tracer_span,
)

EFS_ROOT = Path(os.environ.get("EFS_MOUNT_PATH", "/mnt/efs"))
DATASETS_DIR = EFS_ROOT / "datasets"
UPLOADS_DIR = EFS_ROOT / "uploads"

# Limites de upload e concorrencia (hardening)
MAX_UPLOAD_SIZE_MB = int(os.environ.get("MAX_UPLOAD_SIZE_MB", "100"))
ALLOWED_UPLOAD_TYPES = {
    "application/json", "application/octet-stream", "application/x-ndjson",
    "text/plain", "text/csv",
}
MAX_CONCURRENT_BENCHES = int(os.environ.get("MAX_CONCURRENT_BENCHES", "2"))

# Contador simples (thread-unsafe ok - roda em 1 event loop por worker)
_active_benches = 0


# ---------------------- telemetria: inicializa ANTES do app ------------------
init_logging()
init_metrics()
init_tracing()

app = FastAPI(
    title="EFS/S3 Data API",
    description="API storage-agnostica para benchmark EFS vs S3 (Mountpoint)",
    version=os.environ.get("API_VERSION", "1.1.0"),
)
instrument_fastapi(app)


# ---------- SQS consumer (1 thread por task, inicializa no startup) ---------
@app.on_event("startup")
def _spawn_sqs_consumer() -> None:
    from app.consumer import start_consumer
    start_consumer()


# ------------------------------- models --------------------------------------
class HealthOut(BaseModel):
    status: str
    variant: str
    efs_mounted: bool
    efs_path: str
    free_bytes: int | None = None
    total_bytes: int | None = None


class DatasetSummary(BaseModel):
    name: str
    records_files: int
    total_size_bytes: int
    has_manifest: bool


class Manifest(BaseModel):
    dataset: str
    generated_at: str
    total_records: int
    record_schema: dict[str, str]
    parts: list[dict[str, Any]]


class Record(BaseModel):
    id: str
    payload: dict[str, Any]


class WriteRecordIn(BaseModel):
    payload: dict[str, Any]


class BenchWriteIn(BaseModel):
    target_gb: float = Field(20.0, gt=0, le=500)
    min_mb: int = Field(10, ge=1, le=2048)
    max_mb: int = Field(500, ge=1, le=2048)
    subpath: str = Field("bench-write", description="subpasta dentro do mount")


class BenchReadIn(BaseModel):
    max_files: int | None = Field(None, ge=1)
    target_gb: float | None = Field(None, gt=0, le=500)
    subpath: str = Field("", description="subpasta para ler (vazio = raiz)")


class BenchAck(BaseModel):
    bench_id: str
    kind: str
    variant: str
    status: str = "running"


# ------------------------------- helpers -------------------------------------
def _ensure_in_efs(path: Path) -> Path:
    resolved = path.resolve()
    try:
        resolved.relative_to(EFS_ROOT.resolve())
    except ValueError:
        raise HTTPException(status_code=400, detail="caminho fora do EFS_ROOT")
    return resolved


def _dataset_dir(name: str) -> Path:
    if "/" in name or name in ("", ".", ".."):
        raise HTTPException(status_code=400, detail="nome de dataset invalido")
    return _ensure_in_efs(DATASETS_DIR / name)


def _iter_records_files(dataset: str) -> Iterator[Path]:
    d = _dataset_dir(dataset)
    records = d / "records"
    if not records.is_dir():
        return iter(())
    return sorted(records.glob("part-*.jsonl")).__iter__()


# ------------------------------- endpoints -----------------------------------
@app.get("/health", response_model=HealthOut)
def health() -> HealthOut:
    ok = EFS_ROOT.is_dir()
    free = total = None
    if ok:
        try:
            usage = shutil.disk_usage(EFS_ROOT)
            free, total = usage.free, usage.total
        except OSError:
            # S3 via Mountpoint nao suporta statvfs - nao e erro
            free = total = None
    return HealthOut(
        status="ok" if ok else "degraded",
        variant=VARIANT,
        efs_mounted=ok,
        efs_path=str(EFS_ROOT),
        free_bytes=free,
        total_bytes=total,
    )


@app.get("/datasets", response_model=list[DatasetSummary])
def list_datasets() -> list[DatasetSummary]:
    if not DATASETS_DIR.is_dir():
        return []
    out: list[DatasetSummary] = []
    for d in sorted(DATASETS_DIR.iterdir()):
        if not d.is_dir():
            continue
        records_dir = d / "records"
        files = list(records_dir.glob("part-*.jsonl")) if records_dir.is_dir() else []
        total = sum(f.stat().st_size for f in files)
        out.append(
            DatasetSummary(
                name=d.name,
                records_files=len(files),
                total_size_bytes=total,
                has_manifest=(d / "manifest.json").is_file(),
            )
        )
    return out


@app.get("/datasets/{name}/manifest", response_model=Manifest)
def get_manifest(name: str) -> Manifest:
    m = _dataset_dir(name) / "manifest.json"
    if not m.is_file():
        raise HTTPException(status_code=404, detail="manifest nao encontrado")
    with timed("read_manifest", dataset=name):
        return Manifest(**json.loads(m.read_text()))


@app.get("/datasets/{name}/records")
def list_records(
    name: str,
    limit: int = Query(100, ge=1, le=10_000),
    offset: int = Query(0, ge=0),
) -> list[Record]:
    seen = 0
    out: list[Record] = []
    with timed("list_records", dataset=name, limit=limit, offset=offset):
        for part in _iter_records_files(name):
            with part.open("r", encoding="utf-8") as fh:
                for line in fh:
                    line = line.strip()
                    if not line:
                        continue
                    if seen < offset:
                        seen += 1
                        continue
                    try:
                        obj = json.loads(line)
                        out.append(Record(id=obj["id"], payload=obj.get("payload", {})))
                    except Exception:
                        continue
                    if len(out) >= limit:
                        return out
                    seen += 1
    if not out and offset == 0:
        raise HTTPException(status_code=404, detail="dataset vazio ou inexistente")
    return out


@app.get("/datasets/{name}/records/{record_id}", response_model=Record)
def get_record(name: str, record_id: str) -> Record:
    with timed("get_record", dataset=name, record_id=record_id):
        for part in _iter_records_files(name):
            with part.open("r", encoding="utf-8") as fh:
                for line in fh:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        obj = json.loads(line)
                        if obj.get("id") == record_id:
                            return Record(id=obj["id"], payload=obj.get("payload", {}))
                    except Exception:
                        continue
    raise HTTPException(status_code=404, detail="record nao encontrado")


@app.get("/datasets/{name}/files/{filename}")
def download_file(name: str, filename: str) -> FileResponse:
    path = _ensure_in_efs(_dataset_dir(name) / "records" / filename)
    if not path.is_file():
        raise HTTPException(status_code=404, detail="arquivo nao encontrado")
    return FileResponse(path, filename=filename, media_type="application/x-ndjson")


@app.post("/datasets/{name}/records", status_code=201)
def append_record(name: str, body: WriteRecordIn) -> dict[str, str]:
    dataset = _dataset_dir(name)
    records = dataset / "records"
    records.mkdir(parents=True, exist_ok=True)
    part = records / "part-api.jsonl"

    rec_id = hashlib.sha256(
        f"{datetime.now(timezone.utc).isoformat()}-{json.dumps(body.payload, sort_keys=True)}".encode()
    ).hexdigest()[:16]

    line = json.dumps({"id": rec_id, "payload": body.payload}, ensure_ascii=False)
    with timed("append_record", dataset=name, record_id=rec_id):
        with part.open("a", encoding="utf-8") as fh:
            fh.write(line + "\n")

    return {"id": rec_id, "dataset": name, "file": str(part.relative_to(EFS_ROOT))}


@app.post("/uploads", status_code=201)
async def upload_file(file: UploadFile) -> JSONResponse:
    UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
    filename = os.path.basename(file.filename or "file")
    if not filename:
        raise HTTPException(status_code=400, detail="filename vazio")

    # content-type whitelist (opcional via env FORCE_UPLOAD_TYPE_CHECK=false)
    if os.environ.get("FORCE_UPLOAD_TYPE_CHECK", "true").lower() == "true":
        if file.content_type not in ALLOWED_UPLOAD_TYPES:
            raise HTTPException(
                status_code=400,
                detail=f"content-type '{file.content_type}' nao permitido",
            )

    dst = _ensure_in_efs(UPLOADS_DIR / filename)
    if dst.exists():
        raise HTTPException(status_code=409, detail="arquivo ja existe - use DELETE antes")

    max_bytes = MAX_UPLOAD_SIZE_MB * 1024 * 1024
    size = 0
    with timed("upload_file", filename=filename):
        try:
            with dst.open("wb") as fh:
                while chunk := await file.read(1024 * 1024):
                    size += len(chunk)
                    if size > max_bytes:
                        fh.close()
                        dst.unlink(missing_ok=True)
                        raise HTTPException(
                            status_code=413,
                            detail=f"arquivo excede {MAX_UPLOAD_SIZE_MB} MB",
                        )
                    fh.write(chunk)
        except HTTPException:
            raise
        except Exception:
            dst.unlink(missing_ok=True)
            raise
    return JSONResponse(
        status_code=201,
        content={"path": str(dst.relative_to(EFS_ROOT)), "size_bytes": size},
    )


@app.get("/uploads")
def list_uploads() -> list[dict[str, Any]]:
    if not UPLOADS_DIR.is_dir():
        return []
    return [{"name": p.name, "size_bytes": p.stat().st_size} for p in sorted(UPLOADS_DIR.iterdir()) if p.is_file()]


@app.get("/uploads/{filename}")
def download_upload(filename: str) -> FileResponse:
    path = _ensure_in_efs(UPLOADS_DIR / filename)
    if not path.is_file():
        raise HTTPException(status_code=404, detail="arquivo nao encontrado")
    return FileResponse(path, filename=filename)


@app.delete("/uploads/{filename}", status_code=204, response_class=Response)
def delete_upload(filename: str) -> Response:
    path = _ensure_in_efs(UPLOADS_DIR / filename)
    if not path.is_file():
        raise HTTPException(status_code=404, detail="arquivo nao encontrado")
    path.unlink()
    return Response(status_code=204)


# --------------------------- BENCHMARKS --------------------------------------
# Endpoints assincronos que disparam o bench em background e retornam imediato
# com um bench_id. Status por /bench/{id}.

@app.post("/bench/write", response_model=BenchAck, status_code=202)
def bench_write(body: BenchWriteIn, bg: BackgroundTasks) -> BenchAck:
    """Cria target_gb em arquivos de [min_mb, max_mb] dentro de /mnt/efs/<subpath>/<bench_id>.
    Retorna 202 com bench_id. Resultado em /bench/{bench_id} e no S3 results bucket.
    """
    global _active_benches
    from app.bench import run_bench_write
    import uuid as _uuid

    # DoS guard: N benchmarks ativos simultaneos
    if _active_benches >= MAX_CONCURRENT_BENCHES:
        raise HTTPException(
            status_code=429,
            detail=f"muitos benchmarks ativos (max={MAX_CONCURRENT_BENCHES})",
        )

    # Path traversal guard: valida subpath ANTES de qualquer criacao
    try:
        _ensure_in_efs(EFS_ROOT / body.subpath)
    except HTTPException:
        raise HTTPException(status_code=400, detail="subpath invalido")

    bench_id = _uuid.uuid4().hex[:12]
    bench._runs[bench_id] = bench.BenchResult(
        bench_id=bench_id, kind="write", variant=VARIANT,
        started_at=bench._now_iso(), target_gb=body.target_gb,
        file_size_mb_min=body.min_mb, file_size_mb_max=body.max_mb,
    )

    def _runner():
        global _active_benches
        _active_benches += 1
        from app import bench as b
        res = b._runs[bench_id]
        try:
            import random, time
            dest = EFS_ROOT / body.subpath / bench_id
            dest.mkdir(parents=True, exist_ok=True)
            # defense in depth: valida que o dir resolvido nao saiu do EFS
            _ensure_in_efs(dest)
            target_bytes = int(body.target_gb * (1024**3))
            min_b = body.min_mb * (1024**2)
            max_b = body.max_mb * (1024**2)

            from app.telemetry import Metrics, annotate, size_bucket
            # span pai do bench: bench_id/kind/variant viram annotations filtraveis no X-Ray
            with tracer_span("bench.write", bench_id=bench_id, kind="write", variant=VARIANT):
                t_start = time.perf_counter()
                while res.total_bytes < target_bytes:
                    remaining = target_bytes - res.total_bytes
                    size = random.randint(min_b, max_b)
                    if size > remaining:
                        size = max(min_b, remaining)
                    fn = dest / f"file-{res.files_processed:06d}.bin"
                    bucket = size_bucket(size)
                    t0 = time.perf_counter()
                    with tracer_span("file.write", bench_id=bench_id, size_bucket=bucket):
                        b._write_file(fn, size)
                    latency_ms = (time.perf_counter() - t0) * 1000
                    res.files_processed += 1
                    res.total_bytes += size
                    res.latencies_ms.append(latency_ms)
                    with Metrics(op="write", size_bucket=bucket) as m:
                        m.put("FileOpLatencyMs", latency_ms, "Milliseconds")
                        m.put("FileOpBytes", size, "Bytes")
                        m.prop("bench_id", bench_id)
                res.duration_s = round(time.perf_counter() - t_start, 3)
                res.throughput_mb_per_s = round((res.total_bytes / (1024**2)) / max(res.duration_s, 0.001), 2)
                res.status = "completed"
                res.finished_at = b._now_iso()
                with Metrics(op="write") as m:
                    m.put("BenchWriteThroughputMBps", res.throughput_mb_per_s, "Megabytes/Second")
                    m.put("BenchFiles", res.files_processed, "Count")
                    m.put("BenchBytes", res.total_bytes, "Bytes")
                    m.prop("bench_id", bench_id)
                    m.prop("duration_s", res.duration_s)
                log.info("bench.write.done", **res.summary())
        except Exception as e:
            res.status = "failed"
            res.error = str(e)
            res.finished_at = b._now_iso()
            log.exception("bench.write.failed", bench_id=bench_id, error=str(e))
        finally:
            _active_benches -= 1
            b._upload_result(res)

    bg.add_task(_runner)
    log.info("bench.write.queued", bench_id=bench_id, target_gb=body.target_gb)
    return BenchAck(bench_id=bench_id, kind="write", variant=VARIANT)


@app.post("/bench/read", response_model=BenchAck, status_code=202)
def bench_read(body: BenchReadIn, bg: BackgroundTasks) -> BenchAck:
    global _active_benches
    from app import bench as b
    import uuid as _uuid

    # DoS guard
    if _active_benches >= MAX_CONCURRENT_BENCHES:
        raise HTTPException(
            status_code=429,
            detail=f"muitos benchmarks ativos (max={MAX_CONCURRENT_BENCHES})",
        )

    # Path traversal guard: valida subpath ANTES de iniciar
    if body.subpath:
        try:
            _ensure_in_efs(EFS_ROOT / body.subpath)
        except HTTPException:
            raise HTTPException(status_code=400, detail="subpath invalido")

    bench_id = _uuid.uuid4().hex[:12]
    b._runs[bench_id] = b.BenchResult(
        bench_id=bench_id, kind="read", variant=VARIANT,
        started_at=b._now_iso(),
        target_gb=body.target_gb or 0.0,
    )

    def _runner():
        global _active_benches
        _active_benches += 1
        res = b._runs[bench_id]
        try:
            import time
            from app.telemetry import Metrics, size_bucket
            root = EFS_ROOT / body.subpath if body.subpath else EFS_ROOT
            # defense in depth
            _ensure_in_efs(root)
            if not root.is_dir():
                raise FileNotFoundError(f"path nao existe: {root}")
            target_bytes = int((body.target_gb or 0) * (1024**3))

            with tracer_span("bench.read", bench_id=bench_id, kind="read", variant=VARIANT):
                t_start = time.perf_counter()
                for path in b._walk(root):
                    # size_bucket soh eh conhecido depois do stat; para o span
                    # cobrir a leitura, usamos size do stat antes de ler.
                    try:
                        stat_size = path.stat().st_size
                    except OSError:
                        continue
                    bucket = size_bucket(stat_size)
                    t0 = time.perf_counter()
                    with tracer_span("file.read", bench_id=bench_id, size_bucket=bucket):
                        size = b._read_file(path)
                    latency_ms = (time.perf_counter() - t0) * 1000
                    res.files_processed += 1
                    res.total_bytes += size
                    res.latencies_ms.append(latency_ms)
                    with Metrics(op="read", size_bucket=bucket) as m:
                        m.put("FileOpLatencyMs", latency_ms, "Milliseconds")
                        m.put("FileOpBytes", size, "Bytes")
                        m.prop("bench_id", bench_id)
                    if body.max_files and res.files_processed >= body.max_files:
                        break
                    if target_bytes and res.total_bytes >= target_bytes:
                        break
                res.duration_s = round(time.perf_counter() - t_start, 3)
                res.throughput_mb_per_s = round((res.total_bytes / (1024**2)) / max(res.duration_s, 0.001), 2)
                res.status = "completed"
                res.finished_at = b._now_iso()
                with Metrics(op="read") as m:
                    m.put("BenchReadThroughputMBps", res.throughput_mb_per_s, "Megabytes/Second")
                    m.put("BenchFiles", res.files_processed, "Count")
                    m.put("BenchBytes", res.total_bytes, "Bytes")
                    m.prop("bench_id", bench_id)
                    m.prop("duration_s", res.duration_s)
                log.info("bench.read.done", **res.summary())
        except Exception as e:
            res.status = "failed"
            res.error = str(e)
            res.finished_at = b._now_iso()
            log.exception("bench.read.failed", bench_id=bench_id, error=str(e))
        finally:
            _active_benches -= 1
            b._upload_result(res)

    bg.add_task(_runner)
    log.info("bench.read.queued", bench_id=bench_id, **body.model_dump())
    return BenchAck(bench_id=bench_id, kind="read", variant=VARIANT)


class BenchDispatchIn(BaseModel):
    kind: str = Field(..., description="write ou read")
    prefixes: list[str] = Field(..., min_length=1, max_length=1000,
                                description="subpaths (cada um vira um job)")
    target_gb: float = Field(..., gt=0, le=500)
    min_mb: int = Field(50, ge=1, le=2048)
    max_mb: int = Field(100, ge=1, le=2048)


class BenchDispatchOut(BaseModel):
    dispatched: int
    bench_ids: list[str]
    queue_url: str


@app.post("/bench/dispatch", response_model=BenchDispatchOut)
def bench_dispatch(body: BenchDispatchIn) -> BenchDispatchOut:
    """Enfileira N jobs na SQS. Cada task Fargate consome 1 job por vez,
    garantindo paralelismo real (= N tasks running)."""
    queue_url = os.environ.get("BENCH_QUEUE_URL")
    if not queue_url:
        raise HTTPException(status_code=500, detail="BENCH_QUEUE_URL nao configurada")
    if body.kind not in ("write", "read"):
        raise HTTPException(status_code=400, detail="kind deve ser write ou read")

    from app.consumer import dispatch_batch
    jobs = []
    for prefix in body.prefixes:
        jobs.append({
            "kind": body.kind,
            "subpath": prefix,
            "target_gb": body.target_gb,
            "min_mb": body.min_mb,
            "max_mb": body.max_mb,
        })
    # Span parent do dispatch - BotocoreInstrumentor + AwsXRayPropagator
    # injetam AWSTraceHeader em cada SendMessage. Isso conecta este trace
    # com os traces dos consumers via X-Ray.
    with tracer_span(
        "bench.dispatch",
        kind=body.kind,
        variant=VARIANT,
        prefixes=len(body.prefixes),
        target_gb=body.target_gb,
    ):
        bench_ids = dispatch_batch(queue_url, jobs)
    log.info("bench.dispatch", count=len(bench_ids), kind=body.kind,
             prefixes=len(body.prefixes), queue=queue_url)
    return BenchDispatchOut(dispatched=len(bench_ids), bench_ids=bench_ids, queue_url=queue_url)


@app.get("/bench")
def list_benchmarks() -> list[dict[str, Any]]:
    return bench.list_runs()


@app.get("/bench/{bench_id}")
def get_benchmark(bench_id: str) -> dict[str, Any]:
    r = bench.get_run(bench_id)
    if not r:
        raise HTTPException(status_code=404, detail="bench_id nao encontrado")
    return r.summary()
