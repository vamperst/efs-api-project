#!/usr/bin/env python3
"""
Popula o EFS com dados UTEIS para a API ler.

Estrutura gerada em <efs_root>/datasets/<dataset_name>/:
    manifest.json               - metadados: total_records, parts, schema
    records/
        part-00000.jsonl        - records JSONL (1 record por linha)
        ...

Observabilidade:
- Logs estruturados em JSON para stdout + /var/log/populator/populate.jsonl
  (o CloudWatch Agent faz tail desse arquivo para /bench/populator).
- Ao final, escreve o resultado agregado em:
    s3://$BENCH_RESULTS_BUCKET/results/populator/<run_id>.json
  (se a env estiver setada).
- Metricas EMF em stdout (namespace EfsS3Bench).

Uso na EC2 populator (ja com EFS montado em /mnt/efs):
    sudo dnf install -y python3 python3-pip
    pip3 install Faker boto3
    python3 populate_efs.py --target-gb 100 --dataset fiap-data
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import random
import sys
import time
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

try:
    from faker import Faker
except ImportError:
    print("instale Faker: pip3 install Faker", file=sys.stderr)
    sys.exit(1)

try:
    import boto3
except ImportError:
    boto3 = None  # upload de resultado e opcional

fake = Faker()
Faker.seed(42)
random.seed(42)

KINDS = ("user", "transaction", "event", "product")
RUN_ID = uuid.uuid4().hex[:12]
METRIC_NAMESPACE = os.environ.get("METRIC_NAMESPACE", "EfsS3Bench")
BENCH_RESULTS_BUCKET = os.environ.get("BENCH_RESULTS_BUCKET", "")
AWS_REGION = os.environ.get("AWS_REGION", "us-east-1")


# ------------------------------- logging ------------------------------------
class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(record.created)),
            "level": record.levelname,
            "service": "populator",
            "run_id": RUN_ID,
            "msg": record.getMessage(),
        }
        if hasattr(record, "extra_fields"):
            payload.update(record.extra_fields)  # type: ignore[attr-defined]
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False)


def _setup_logging() -> logging.Logger:
    root = logging.getLogger("populator")
    root.setLevel(os.environ.get("LOG_LEVEL", "INFO").upper())
    root.propagate = False
    # stdout
    sh = logging.StreamHandler(sys.stdout)
    sh.setFormatter(JsonFormatter())
    root.addHandler(sh)
    # arquivo (CloudWatch Agent consome)
    try:
        os.makedirs("/var/log/populator", exist_ok=True)
        fh = logging.FileHandler("/var/log/populator/populate.jsonl")
        fh.setFormatter(JsonFormatter())
        root.addHandler(fh)
    except PermissionError:
        pass
    return root


def log_event(logger: logging.Logger, level: int, msg: str, **fields: Any) -> None:
    extra = logging.LogRecord("", 0, "", 0, "", None, None)
    record = logger.makeRecord("populator", level, "", 0, msg, (), None)
    record.extra_fields = fields  # type: ignore[attr-defined]
    logger.handle(record)


log = _setup_logging()


# ------------------------------- EMF metric ---------------------------------
def emf(metric_name: str, value: float, unit: str, **dimensions: str) -> None:
    """Emite uma metrica EMF em stdout. O CloudWatch Logs agent do container
    ou o CWAgent lendo stdout do servico converte isso em metrica real."""
    dim_set = list(dimensions.keys())
    payload = {
        "_aws": {
            "Timestamp": int(time.time() * 1000),
            "CloudWatchMetrics": [{
                "Namespace": METRIC_NAMESPACE,
                "Dimensions": [dim_set],
                "Metrics": [{"Name": metric_name, "Unit": unit}],
            }],
        },
        metric_name: value,
        "run_id": RUN_ID,
        "service": "populator",
        **dimensions,
    }
    print(json.dumps(payload), flush=True)


# ------------------------------- generators ---------------------------------
def gen_user() -> dict[str, Any]:
    return {
        "kind": "user",
        "name": fake.name(),
        "email": fake.email(),
        "phone": fake.phone_number(),
        "address": {
            "street": fake.street_address(),
            "city": fake.city(),
            "state": fake.state_abbr(),
            "zip": fake.postcode(),
            "country": fake.country(),
        },
        "company": fake.company(),
        "job": fake.job(),
        "birthdate": fake.date_of_birth(minimum_age=18, maximum_age=90).isoformat(),
        "bio": fake.paragraph(nb_sentences=5),
    }


def gen_transaction() -> dict[str, Any]:
    return {
        "kind": "transaction",
        "account_from": fake.iban(),
        "account_to": fake.iban(),
        "amount": round(random.uniform(1.0, 50_000.0), 2),
        "currency": random.choice(("USD", "BRL", "EUR", "GBP", "JPY")),
        "timestamp": fake.iso8601(),
        "description": fake.sentence(nb_words=8),
        "merchant": fake.company(),
        "category": random.choice(
            ("groceries", "rent", "salary", "transport", "leisure", "utilities")
        ),
        "status": random.choice(("pending", "completed", "failed", "reversed")),
    }


def gen_event() -> dict[str, Any]:
    return {
        "kind": "event",
        "type": random.choice(("page_view", "click", "purchase", "login", "logout", "signup")),
        "user_id": fake.uuid4(),
        "session_id": fake.uuid4(),
        "timestamp": fake.iso8601(),
        "ip": fake.ipv4_public(),
        "user_agent": fake.user_agent(),
        "url": fake.url(),
        "referrer": fake.url(),
        "properties": {
            "country": fake.country_code(),
            "device": random.choice(("mobile", "desktop", "tablet")),
            "browser": random.choice(("chrome", "firefox", "safari", "edge")),
            "duration_ms": random.randint(0, 300_000),
        },
    }


def gen_product() -> dict[str, Any]:
    return {
        "kind": "product",
        "sku": fake.bothify("???-########").upper(),
        "name": fake.catch_phrase(),
        "description": fake.paragraph(nb_sentences=3),
        "price": round(random.uniform(1.0, 5_000.0), 2),
        "currency": "USD",
        "stock": random.randint(0, 10_000),
        "tags": random.sample(["new", "sale", "featured", "eco", "limited", "premium"], k=2),
        "supplier": fake.company(),
        "weight_kg": round(random.uniform(0.1, 30.0), 2),
    }


GENERATORS = {"user": gen_user, "transaction": gen_transaction, "event": gen_event, "product": gen_product}


def gen_record() -> dict[str, Any]:
    kind = random.choices(KINDS, weights=[1, 3, 4, 2])[0]
    return {"id": uuid.uuid4().hex, "payload": GENERATORS[kind]()}


# ------------------------------- writer --------------------------------------
@dataclass
class PartInfo:
    file: str
    records: int
    size_bytes: int
    duration_s: float


def write_part(path: Path, target_size_bytes: int, flush_every: int = 500) -> PartInfo:
    written = 0
    records = 0
    tmp = path.with_suffix(path.suffix + ".tmp")
    t0 = time.perf_counter()
    with tmp.open("w", encoding="utf-8", buffering=1 << 20) as fh:
        while written < target_size_bytes:
            rec = gen_record()
            line = json.dumps(rec, ensure_ascii=False)
            fh.write(line)
            fh.write("\n")
            written += len(line.encode("utf-8")) + 1
            records += 1
            if records % flush_every == 0:
                fh.flush()
        fh.flush()
        os.fsync(fh.fileno())
    tmp.rename(path)
    return PartInfo(
        file=path.name,
        records=records,
        size_bytes=path.stat().st_size,
        duration_s=time.perf_counter() - t0,
    )


def human(n: float) -> str:
    for u in ("B", "KB", "MB", "GB", "TB"):
        if abs(n) < 1024:
            return f"{n:.1f}{u}"
        n /= 1024
    return f"{n:.1f}PB"


# --------------------------- result upload ----------------------------------
@dataclass
class RunResult:
    run_id: str
    started_at: str
    finished_at: str
    dataset: str
    efs_root: str
    target_gb: float
    total_bytes: int
    total_records: int
    num_parts: int
    duration_s: float
    throughput_mb_per_s: float
    status: str = "completed"
    error: str | None = None
    parts: list[dict[str, Any]] = field(default_factory=list)


def upload_result(res: RunResult) -> None:
    if not BENCH_RESULTS_BUCKET or boto3 is None:
        log_event(log, logging.INFO, "result.upload.skip",
                  reason="sem BENCH_RESULTS_BUCKET ou boto3")
        return
    key = f"results/populator/{res.run_id}.json"
    body = json.dumps(asdict(res), indent=2).encode()
    try:
        boto3.client("s3", region_name=AWS_REGION).put_object(
            Bucket=BENCH_RESULTS_BUCKET,
            Key=key,
            Body=body,
            ContentType="application/json",
        )
        log_event(log, logging.INFO, "result.uploaded",
                  bucket=BENCH_RESULTS_BUCKET, key=key, bytes=len(body))
    except Exception as e:
        log_event(log, logging.ERROR, "result.upload.failed", error=str(e))


# ------------------------------- main ---------------------------------------
def main() -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    p.add_argument("--efs-root", default="/mnt/efs")
    p.add_argument("--dataset", default="fiap-data")
    p.add_argument("--target-gb", type=float, default=100.0)
    p.add_argument("--min-mb", type=int, default=10)
    p.add_argument("--max-mb", type=int, default=500)
    p.add_argument("--resume", action="store_true")
    args = p.parse_args()

    started_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    log_event(log, logging.INFO, "populate.start",
              dataset=args.dataset, target_gb=args.target_gb,
              min_mb=args.min_mb, max_mb=args.max_mb,
              efs_root=args.efs_root)

    efs_root = Path(args.efs_root)
    if not efs_root.is_dir():
        log_event(log, logging.ERROR, "populate.efs_missing", efs_root=str(efs_root))
        return 2

    dataset_dir = efs_root / "datasets" / args.dataset
    records_dir = dataset_dir / "records"
    records_dir.mkdir(parents=True, exist_ok=True)

    target_bytes = int(args.target_gb * (1024**3))
    min_bytes = args.min_mb * (1024**2)
    max_bytes = args.max_mb * (1024**2)

    existing_parts = sorted(records_dir.glob("part-*.jsonl"))
    existing_bytes = sum(f.stat().st_size for f in existing_parts)
    part_idx = len(existing_parts)

    if existing_parts and not args.resume:
        log_event(log, logging.ERROR, "populate.dataset_exists",
                  parts=len(existing_parts), bytes=existing_bytes,
                  hint="use --resume ou apague antes")
        return 3

    parts_meta: list[PartInfo] = []
    total = existing_bytes
    t_start = time.perf_counter()

    try:
        while total < target_bytes:
            remaining = target_bytes - total
            size = random.randint(min_bytes, max_bytes)
            if size > remaining:
                size = max(min_bytes, remaining)

            fn = records_dir / f"part-{part_idx:05d}.jsonl"
            info = write_part(fn, size)
            parts_meta.append(info)
            total += info.size_bytes
            part_idx += 1

            mb_per_s = info.size_bytes / (1024**2) / max(info.duration_s, 0.001)
            log_event(log, logging.INFO, "populate.part_done",
                      part=info.file, bytes=info.size_bytes,
                      records=info.records, duration_s=round(info.duration_s, 3),
                      mb_per_s=round(mb_per_s, 1),
                      total_bytes=total, total_gb=round(total / (1024**3), 2))

            # metrica por part
            emf("PopulatorPartLatencyMs", info.duration_s * 1000, "Milliseconds", role="populator")
            emf("PopulatorPartBytes", info.size_bytes, "Bytes", role="populator")
    except KeyboardInterrupt:
        log_event(log, logging.WARNING, "populate.interrupted",
                  hint="use --resume para continuar")
        return 130

    elapsed = time.perf_counter() - t_start
    mb_per_s = (total - existing_bytes) / (1024**2) / max(elapsed, 0.001)

    # Manifest agregado
    all_parts = sorted(records_dir.glob("part-*.jsonl"))
    parts_list: list[dict[str, Any]] = []
    all_records = 0
    for f in all_parts:
        match = next((pi for pi in parts_meta if pi.file == f.name), None)
        if match:
            rec = match.records
        else:
            rec = sum(1 for _ in f.open("rb"))
        all_records += rec
        parts_list.append({"file": f.name, "records": rec, "size_bytes": f.stat().st_size})

    manifest = {
        "dataset": args.dataset,
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "total_records": all_records,
        "total_bytes": total,
        "record_schema": {
            "id": "string",
            "payload.kind": "enum(user,transaction,event,product)",
            "payload.*": "campos especificos por kind",
        },
        "parts": parts_list,
    }
    (dataset_dir / "manifest.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False))

    # Metrica agregada (aparece no dashboard)
    emf("PopulatorThroughputMBps", mb_per_s, "Megabytes/Second", role="populator")
    emf("PopulatorTotalBytes", total, "Bytes", role="populator")
    emf("PopulatorDurationSeconds", elapsed, "Seconds", role="populator")

    res = RunResult(
        run_id=RUN_ID,
        started_at=started_at,
        finished_at=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        dataset=args.dataset,
        efs_root=str(efs_root),
        target_gb=args.target_gb,
        total_bytes=total,
        total_records=all_records,
        num_parts=len(all_parts),
        duration_s=round(elapsed, 2),
        throughput_mb_per_s=round(mb_per_s, 2),
        parts=parts_list[:100],  # nao embarca TODAS as 500 parts na resposta
    )
    upload_result(res)

    log_event(log, logging.INFO, "populate.done",
              parts=len(all_parts), records=all_records,
              total_gb=round(total / (1024**3), 2),
              duration_s=round(elapsed, 2), mb_per_s=round(mb_per_s, 2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
