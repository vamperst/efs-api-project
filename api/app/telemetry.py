"""
Observabilidade da API - os tres pilares:

1) LOGS estruturados (structlog + JSON envelope). Cada log carrega:
   - run_id (bench_id quando aplicavel)
   - variant (efs | s3) - vem da env STORAGE_VARIANT
   - service, env, trace_id (se houver span ativo)

2) METRICAS via CloudWatch EMF. Namespace: EfsS3Bench.
   Dimensoes: [variant, service, env]. Metricas:
   - HttpRequestDurationMs                (op, route, status)
   - FileOpLatencyMs                      (op, variant)
   - BenchWriteThroughputMBps             (variant)
   - BenchReadThroughputMBps              (variant)
   - BenchFiles                           (variant, op)
   - BenchBytes                           (variant, op)

3) TRACES via OpenTelemetry -> OTLP gRPC para um sidecar ADOT collector
   (endpoint local http://localhost:4317). O collector encaminha para X-Ray.

Todo o envio para AWS e feito pelo collector sidecar - a aplicacao so fala
OTLP local + envia EMF via JSON em stdout (CloudWatch Logs agent/awslogs
pega e transforma em metrica pelo log_group subscrito).
"""
from __future__ import annotations

import logging
import os
import sys
import time
import uuid
from contextlib import contextmanager
from typing import Any, Iterator

import structlog
from aws_embedded_metrics.config import get_config
from aws_embedded_metrics.logger.metrics_logger_factory import create_metrics_logger
from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.logging import LoggingInstrumentor
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

SERVICE = "efs-api-lab-api"
VARIANT = os.environ.get("STORAGE_VARIANT", "efs")  # "efs" | "s3"
ENV = os.environ.get("ENV", "dev")
OTEL_ENDPOINT = os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT", "http://localhost:4317")
METRIC_NAMESPACE = os.environ.get("METRIC_NAMESPACE", "EfsS3Bench")


# --------------------------- logging (structlog) ----------------------------
def _add_trace_context(_logger: Any, _method: str, event_dict: dict) -> dict:
    span = trace.get_current_span()
    ctx = span.get_span_context() if span else None
    if ctx and ctx.is_valid:
        event_dict["trace_id"] = format(ctx.trace_id, "032x")
        event_dict["span_id"] = format(ctx.span_id, "016x")
    return event_dict


def _add_common(_logger: Any, _method: str, event_dict: dict) -> dict:
    event_dict.setdefault("service", SERVICE)
    event_dict.setdefault("variant", VARIANT)
    event_dict.setdefault("env", ENV)
    return event_dict


class _HealthCheckFilter(logging.Filter):
    """Suprime linhas de access log do uvicorn para /health.

    A ALB bate /health a cada 15s. Em regime 24/7 sao ~5800 linhas/dia/task
    que so geram barulho em CW Logs sem valor diagnostico (o /health em si
    tem metrica dedicada e aparece no target group do ALB).
    """
    def filter(self, record: logging.LogRecord) -> bool:
        msg = record.getMessage()
        return "/health" not in msg


def init_logging() -> None:
    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=os.environ.get("LOG_LEVEL", "INFO").upper(),
    )
    # Filtrar /health apenas no access log; logs de erro do uvicorn continuam
    logging.getLogger("uvicorn.access").addFilter(_HealthCheckFilter())

    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            _add_common,
            _add_trace_context,
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.JSONRenderer(sort_keys=True),
        ],
        wrapper_class=structlog.stdlib.BoundLogger,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )


log = structlog.get_logger()


# --------------------------- tracing (OTel) ---------------------------------
_tracer_provider: TracerProvider | None = None


def init_tracing() -> None:
    global _tracer_provider
    if _tracer_provider is not None:
        return

    resource = Resource.create({
        "service.name": SERVICE,
        "service.version": os.environ.get("API_VERSION", "dev"),
        "deployment.environment": ENV,
        "efs_s3_bench.variant": VARIANT,
    })

    provider = TracerProvider(resource=resource)
    # OTLP gRPC -> sidecar ADOT em :4317 (insecure porque e localhost).
    # BatchSpanProcessor com parametros agressivos: queue grande + flush rapido,
    # porque cada bench gera dezenas de spans (file.read/write individuais) e
    # nao podemos perder nada no rolling deploy.
    provider.add_span_processor(
        BatchSpanProcessor(
            OTLPSpanExporter(endpoint=OTEL_ENDPOINT, insecure=True),
            max_queue_size=8192,
            max_export_batch_size=512,
            schedule_delay_millis=1000,
            export_timeout_millis=10000,
        )
    )
    trace.set_tracer_provider(provider)
    _tracer_provider = provider

    LoggingInstrumentor().instrument(set_logging_format=False)
    # auto-instrument botocore (boto3) -> spans automaticos para SQS, S3, etc.
    # Com context propagation: ao SendMessage o trace_id atual eh injetado
    # em MessageAttributes (AWSTraceHeader); no ReceiveMessage o consumer
    # extrai e continua o mesmo trace. Isso conecta ALB -> API -> SQS
    # -> Consumer -> S3 num so trace end-to-end.
    try:
        from opentelemetry.instrumentation.botocore import BotocoreInstrumentor
        BotocoreInstrumentor().instrument()
    except ImportError:
        log.warning("otel.botocore.not_installed")

    # Use X-Ray propagator para o trace context viajar via AWSTraceHeader
    # (formato que SQS/X-Ray entendem nativamente).
    try:
        from opentelemetry.propagate import set_global_textmap
        from opentelemetry.propagators.aws import AwsXRayPropagator
        set_global_textmap(AwsXRayPropagator())
    except ImportError:
        log.warning("otel.xray_propagator.not_installed")

    # IdGenerator X-Ray: OTel usa trace IDs de 16 bytes por default; X-Ray
    # precisa do formato especifico (1-timestamp-random). Sem isso, os
    # trace IDs gerados pela app nao aparecem no console do X-Ray.
    try:
        from opentelemetry.sdk.extension.aws.trace import AwsXRayIdGenerator
        # recriar o provider com o id_generator correto
        provider_xray = TracerProvider(
            resource=resource,
            id_generator=AwsXRayIdGenerator(),
        )
        provider_xray.add_span_processor(
            BatchSpanProcessor(
                OTLPSpanExporter(endpoint=OTEL_ENDPOINT, insecure=True),
                max_queue_size=8192,
                max_export_batch_size=512,
                schedule_delay_millis=1000,
                export_timeout_millis=10000,
            )
        )
        trace.set_tracer_provider(provider_xray)
        _tracer_provider = provider_xray
    except ImportError:
        log.warning("otel.xray_id_generator.not_installed")


def flush_traces() -> None:
    """Forca flush dos spans pendentes. Chamar ao final do bench para garantir
    que nada se perca se a task for reciclada logo em seguida."""
    global _tracer_provider
    if _tracer_provider is not None:
        _tracer_provider.force_flush(timeout_millis=10000)


# ------------------------- X-Ray annotations --------------------------------
# OTel -> X-Ray (via ADOT collector). Para um span.attribute virar uma
# Annotation indexavel no X-Ray (filtravel no console, service map, queries),
# o awsxray exporter do collector precisa ter o nome do attribute em
# `indexed_attributes`. A config customizada do sidecar (AOT_CONFIG_CONTENT)
# indexa: variant, bench_id, kind, op, size_bucket.
#
# Attributes fora dessa lista viram Metadata (visiveis no trace mas nao
# filtraveis via console).
INDEXED_KEYS = ("variant", "bench_id", "kind", "op", "size_bucket")


def annotate(**kv: Any) -> None:
    """Seta attributes no span corrente. Os listados em INDEXED_KEYS viram
    X-Ray Annotations (filtraveis); os demais viram Metadata."""
    span = trace.get_current_span()
    if span is None or not span.is_recording():
        return
    for k, v in kv.items():
        if v is None:
            continue
        span.set_attribute(k, str(v))


@contextmanager
def tracer_span(name: str, **attrs: Any) -> Iterator[Any]:
    """Cria um span com attributes que viram annotations indexaveis no X-Ray
    quando batem com INDEXED_KEYS. Ja injeta `variant` automaticamente."""
    full = {"variant": VARIANT}
    full.update({k: str(v) for k, v in attrs.items() if v is not None})
    span = tracer().start_span(name, attributes=full)
    try:
        with trace.use_span(span, end_on_exit=False):
            yield span
    except Exception as e:
        span.record_exception(e)
        span.set_status(trace.Status(trace.StatusCode.ERROR, str(e)))
        raise
    finally:
        span.end()


# ------------------------- size bucketing -----------------------------------
# Dimensao de metrica usada para separar workloads por tamanho de arquivo.
# Buckets fixos (nao muda com dados) para que as series sejam comparaveis
# entre corridas: small (<= 5 MB), medium (<=100 MB), large (> 100 MB).
def size_bucket(size_bytes: int) -> str:
    mb = size_bytes / (1024 * 1024)
    if mb <= 5:
        return "small"
    if mb <= 100:
        return "medium"
    return "large"


def instrument_fastapi(app: Any) -> None:
    FastAPIInstrumentor.instrument_app(app, excluded_urls="health")


def tracer() -> trace.Tracer:
    return trace.get_tracer(SERVICE)


# --------------------------- metrics (EMF) ----------------------------------
# aws-embedded-metrics gera um JSON no stdout que o CloudWatch Logs interpreta
# como metrica (Embedded Metric Format). Nao precisa de PutMetricData API.
def init_metrics() -> None:
    cfg = get_config()
    cfg.namespace = METRIC_NAMESPACE
    cfg.service_name = SERVICE
    cfg.service_type = "ECS"
    cfg.log_group_name = "/bench/api"
    # agent_sink nao: sem CWAgent dentro do container. stdout sink:
    cfg.disable_metric_extraction = False


class Metrics:
    """
    Context manager que publica metricas EMF ao sair do `with`.
    Uso:
        with Metrics(op="write", variant="efs") as m:
            m.put("FileOpLatencyMs", 12.3, "Milliseconds")
    """
    def __init__(self, **dimensions: str) -> None:
        self._logger = create_metrics_logger()
        # dimensoes comuns sempre
        self._logger.set_dimensions({
            "service": SERVICE,
            "env": ENV,
            "variant": VARIANT,
            **{k: v for k, v in dimensions.items() if v is not None},
        })

    def put(self, name: str, value: float, unit: str = "None") -> None:
        self._logger.put_metric(name, value, unit)

    def prop(self, key: str, value: Any) -> None:
        """Propriedade estruturada (nao agregada, mas fica no log)."""
        self._logger.set_property(key, value)

    def __enter__(self) -> "Metrics":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        import asyncio
        try:
            asyncio.get_event_loop().run_until_complete(self._logger.flush())
        except RuntimeError:
            # fora de event loop (worker)
            asyncio.run(self._logger.flush())


# --------------------------- timing helper ----------------------------------
@contextmanager
def timed(op: str, **extra: Any) -> Iterator[dict[str, Any]]:
    """
    Mede duracao, loga start/finish estruturado e cria span OTel.
    Os attributes em INDEXED_KEYS viram X-Ray Annotations filtraveis.

    Uso:
        with timed("write_file", path=p, size_bucket="large") as t:
            ...
        t["duration_ms"]
    """
    t0 = time.perf_counter()
    ctx: dict[str, Any] = {"op": op, **extra}
    attrs = {"variant": VARIANT, "op": op}
    attrs.update({k: str(v) for k, v in extra.items() if v is not None})
    span = tracer().start_span(op, attributes=attrs)
    log.info("op.start", **ctx)
    try:
        with trace.use_span(span, end_on_exit=False):
            yield ctx
    except Exception as e:
        span.record_exception(e)
        span.set_status(trace.Status(trace.StatusCode.ERROR, str(e)))
        ctx["error"] = str(e)
        log.exception("op.error", **ctx)
        raise
    finally:
        duration_ms = (time.perf_counter() - t0) * 1000
        ctx["duration_ms"] = round(duration_ms, 3)
        span.set_attribute("duration_ms", duration_ms)
        span.end()
        log.info("op.finish", **ctx)


def new_run_id() -> str:
    return uuid.uuid4().hex[:12]
