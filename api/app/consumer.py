"""
Consumer SQS para benchmarks em fan-out.

Cada task Fargate roda 1 consumer em background thread que faz long-poll na
fila apropriada (BENCH_QUEUE_URL, setado via env). Quando pega uma mensagem,
executa o bench *localmente* (ocupa a ENI daquela task) e deleta.

Isso garante paralelismo real de N tasks = N consumers = N ENIs dedicadas,
ao contrario do dispatch via ALB que joga muitos jobs num mesmo task.

Observabilidade (para traces detalhados no X-Ray):
- 1 span por job `sqs.bench.{write,read}` com annotations: bench_id, kind,
  variant, size_bucket, prefix, task_host.
- 1 span por arquivo `file.{write,read}` com bytes, latency, throughput.
- 1 span `s3.put_result` (auto-instrumented boto3) com o put do JSON.
- `flush_traces()` no final garante que nada seja perdido em rolling deploy.
"""
from __future__ import annotations

import json
import os
import random
import socket
import threading
import time
from pathlib import Path
from typing import Any

import boto3
from opentelemetry import trace, context as otel_context
from opentelemetry.propagate import extract

from app import bench as b
from app.telemetry import VARIANT, Metrics, flush_traces, log, size_bucket, tracer_span


BENCH_QUEUE_URL = os.environ.get("BENCH_QUEUE_URL", "")
CONSUMER_ENABLED = os.environ.get("BENCH_CONSUMER_ENABLED", "true").lower() == "true"
EFS_ROOT = Path(os.environ.get("EFS_MOUNT_PATH", "/mnt/efs"))
AWS_REGION = os.environ.get("AWS_REGION", "us-east-1")
TASK_HOST = socket.gethostname()[:12]


def _sqs():
    return boto3.client("sqs", region_name=AWS_REGION)


def _process_write(res: "b.BenchResult", subpath: str, min_mb: int, max_mb: int,
                   target_gb: float) -> None:
    dest = EFS_ROOT / subpath / res.bench_id
    dest.mkdir(parents=True, exist_ok=True)
    target_bytes = int(target_gb * (1024**3))
    min_bytes = min_mb * (1024**2)
    max_bytes = max_mb * (1024**2)

    while res.total_bytes < target_bytes:
        remaining = target_bytes - res.total_bytes
        size = random.randint(min_bytes, max_bytes)
        if size > remaining:
            size = max(min_bytes, remaining)
        fn = dest / f"file-{res.files_processed:06d}.bin"
        bucket = size_bucket(size)

        # Span por arquivo - annotations indexaveis permitem filtrar no X-Ray
        with tracer_span(
            "file.write",
            bench_id=res.bench_id,
            kind="write",
            variant=VARIANT,
            size_bucket=bucket,
            prefix=subpath,
            file_index=res.files_processed,
            file_size_bytes=size,
        ):
            t0 = time.perf_counter()
            b._write_file(fn, size)
            lat_ms = (time.perf_counter() - t0) * 1000

        mbps = (size / (1024**2)) / max(lat_ms / 1000, 0.001)
        res.files_processed += 1
        res.total_bytes += size
        res.latencies_ms.append(lat_ms)

        # Metricas EMF: dimensao size_bucket + variant + op ja vem de Metrics()
        with Metrics(op="write", size_bucket=bucket) as m:
            m.put("FileOpLatencyMs", lat_ms, "Milliseconds")
            m.put("FileOpBytes", size, "Bytes")
            m.put("FileOpThroughputMBps", mbps, "Megabytes/Second")
            m.prop("bench_id", res.bench_id)
            m.prop("prefix", subpath)
            m.prop("file_index", res.files_processed)


def _process_read(res: "b.BenchResult", subpath: str, target_gb: float) -> None:
    root = EFS_ROOT / subpath
    if not root.is_dir():
        raise FileNotFoundError(f"path nao existe: {root}")
    target_bytes = int(target_gb * (1024**3))

    for path in b._walk(root):
        try:
            stat_size = path.stat().st_size
        except OSError:
            continue
        bucket = size_bucket(stat_size)

        with tracer_span(
            "file.read",
            bench_id=res.bench_id,
            kind="read",
            variant=VARIANT,
            size_bucket=bucket,
            prefix=subpath,
            file_index=res.files_processed,
            file_size_bytes=stat_size,
        ):
            t0 = time.perf_counter()
            size = b._read_file(path)
            lat_ms = (time.perf_counter() - t0) * 1000

        mbps = (size / (1024**2)) / max(lat_ms / 1000, 0.001)
        res.files_processed += 1
        res.total_bytes += size
        res.latencies_ms.append(lat_ms)

        with Metrics(op="read", size_bucket=bucket) as m:
            m.put("FileOpLatencyMs", lat_ms, "Milliseconds")
            m.put("FileOpBytes", size, "Bytes")
            m.put("FileOpThroughputMBps", mbps, "Megabytes/Second")
            m.prop("bench_id", res.bench_id)
            m.prop("prefix", subpath)
            m.prop("file_index", res.files_processed)

        if target_bytes and res.total_bytes >= target_bytes:
            break


def _extract_trace_context(msg: dict):
    """Le MessageAttributes/SystemAttributes em busca do trace context para
    que o span do consumer vire continuacao do trace do dispatcher."""
    carrier = {}
    # AWSTraceHeader: SQS propaga nativo quando trace ja estava ativo no
    # SendMessage (via BotocoreInstrumentor + AwsXRayPropagator).
    sys_attrs = msg.get("Attributes") or {}
    if "AWSTraceHeader" in sys_attrs:
        carrier["X-Amzn-Trace-Id"] = sys_attrs["AWSTraceHeader"]
    # MessageAttributes (se alguem injetou `traceparent` manualmente)
    msg_attrs = msg.get("MessageAttributes") or {}
    for k in ("traceparent", "tracestate", "X-Amzn-Trace-Id"):
        if k in msg_attrs and msg_attrs[k].get("StringValue"):
            carrier[k.lower() if k != "X-Amzn-Trace-Id" else k] = msg_attrs[k]["StringValue"]
    return extract(carrier) if carrier else None


def _process_message(msg: dict) -> bool:
    """Processa 1 mensagem. Retorna True se sucesso (deletar), False se falha."""
    body = json.loads(msg["Body"])
    bench_id = body.get("bench_id") or "no-id"
    kind = body.get("kind")
    subpath = body.get("subpath") or "bench-sqs"
    target_gb = float(body.get("target_gb", 0))
    min_mb = int(body.get("min_mb", 50))
    max_mb = int(body.get("max_mb", 100))

    res = b.BenchResult(
        bench_id=bench_id, kind=kind, variant=VARIANT,
        started_at=b._now_iso(), target_gb=target_gb,
        file_size_mb_min=min_mb, file_size_mb_max=max_mb,
    )
    b._runs[bench_id] = res
    res.extras = {"prefix": subpath, "task_host": TASK_HOST}

    log.info("sqs.bench.start",
             bench_id=bench_id, kind=kind, subpath=subpath, variant=VARIANT,
             task_host=TASK_HOST, target_gb=target_gb)

    # Extrai trace context da mensagem para continuar o mesmo trace do dispatcher
    parent_ctx = _extract_trace_context(msg)
    ctx_token = otel_context.attach(parent_ctx) if parent_ctx else None

    t_start = time.perf_counter()
    try:
        # Span parent englobando o bench inteiro. Todos os file.* viram filhos.
        # Como o context foi attached, esse span e filho do trace do dispatcher.
        with tracer_span(
            f"sqs.bench.{kind}",
            bench_id=bench_id,
            kind=kind,
            variant=VARIANT,
            prefix=subpath,
            target_gb=target_gb,
            task_host=TASK_HOST,
        ):
            if kind == "write":
                _process_write(res, subpath, min_mb, max_mb, target_gb)
            elif kind == "read":
                _process_read(res, subpath, target_gb)
            else:
                raise ValueError(f"kind invalido: {kind}")

            res.duration_s = round(time.perf_counter() - t_start, 3)
            res.throughput_mb_per_s = round(
                (res.total_bytes / (1024**2)) / max(res.duration_s, 0.001), 2)
            res.status = "completed"
            res.finished_at = b._now_iso()

            # Metricas agregadas do bench inteiro
            metric_name = "BenchWriteThroughputMBps" if kind == "write" else "BenchReadThroughputMBps"
            with Metrics(op=kind) as m:
                m.put(metric_name, res.throughput_mb_per_s, "Megabytes/Second")
                m.put("BenchFiles", res.files_processed, "Count")
                m.put("BenchBytes", res.total_bytes, "Bytes")
                m.prop("bench_id", bench_id)
                m.prop("prefix", subpath)
                m.prop("task_host", TASK_HOST)
                m.prop("duration_s", res.duration_s)

            log.info("sqs.bench.done", **res.summary())
            b._upload_result(res)
            return True
    except Exception as e:
        res.status = "failed"
        res.error = str(e)
        res.duration_s = round(time.perf_counter() - t_start, 3)
        res.finished_at = b._now_iso()
        log.exception("sqs.bench.failed", bench_id=bench_id, error=str(e))
        b._upload_result(res)
        return False
    finally:
        # GARANTIR exportacao de spans antes do consumer pegar proxima mensagem.
        # Sem isso, um rolling deploy perde todos os traces do bench atual.
        flush_traces()
        if ctx_token is not None:
            otel_context.detach(ctx_token)


def _consumer_loop(stop_event: threading.Event) -> None:
    if not BENCH_QUEUE_URL:
        log.warning("sqs.consumer.disabled", reason="BENCH_QUEUE_URL vazio")
        return
    log.info("sqs.consumer.start",
             queue=BENCH_QUEUE_URL, variant=VARIANT, task_host=TASK_HOST)
    sqs = _sqs()
    while not stop_event.is_set():
        try:
            resp = sqs.receive_message(
                QueueUrl=BENCH_QUEUE_URL,
                MaxNumberOfMessages=1,  # 1 por task = paralelismo real por N tasks
                WaitTimeSeconds=20,     # long-poll
                VisibilityTimeout=3600, # 1h
                AttributeNames=["AWSTraceHeader"],   # X-Ray trace context
                MessageAttributeNames=["All"],       # inclui traceparent custom
            )
            msgs = resp.get("Messages", [])
            for msg in msgs:
                ok = _process_message(msg)
                if ok:
                    sqs.delete_message(
                        QueueUrl=BENCH_QUEUE_URL,
                        ReceiptHandle=msg["ReceiptHandle"],
                    )
                else:
                    log.warning("sqs.message.not_deleted_for_retry",
                                msg_id=msg.get("MessageId"))
        except Exception as e:
            log.exception("sqs.consumer.loop_error", error=str(e))
            time.sleep(5)


_consumer_thread: threading.Thread | None = None
_stop_event = threading.Event()


def start_consumer() -> None:
    global _consumer_thread
    if not CONSUMER_ENABLED:
        log.info("sqs.consumer.skipped", reason="BENCH_CONSUMER_ENABLED=false")
        return
    if _consumer_thread and _consumer_thread.is_alive():
        return
    _consumer_thread = threading.Thread(
        target=_consumer_loop, args=(_stop_event,), daemon=True,
        name="bench-sqs-consumer",
    )
    _consumer_thread.start()


# ---------- dispatcher (usado por POST /bench/dispatch) ----------
def dispatch_batch(queue_url: str, jobs: list[dict[str, Any]]) -> list[str]:
    """Enfileira N jobs em batches de 10 (limite SQS). Retorna bench_ids."""
    import uuid as _uuid
    sqs = _sqs()
    bench_ids = []
    for job in jobs:
        bid = job.get("bench_id") or _uuid.uuid4().hex[:12]
        job["bench_id"] = bid
        bench_ids.append(bid)

    for i in range(0, len(jobs), 10):
        batch = jobs[i:i+10]
        entries = [
            {"Id": str(idx), "MessageBody": json.dumps(j)}
            for idx, j in enumerate(batch)
        ]
        sqs.send_message_batch(QueueUrl=queue_url, Entries=entries)
    return bench_ids
