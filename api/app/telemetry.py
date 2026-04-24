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


def init_logging() -> None:
    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=os.environ.get("LOG_LEVEL", "INFO").upper(),
    )
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
    # OTLP gRPC -> sidecar ADOT em :4317 (insecure porque e localhost)
    provider.add_span_processor(
        BatchSpanProcessor(
            OTLPSpanExporter(endpoint=OTEL_ENDPOINT, insecure=True)
        )
    )
    trace.set_tracer_provider(provider)
    _tracer_provider = provider

    LoggingInstrumentor().instrument(set_logging_format=False)


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
    Uso:
        with timed("write_file", path=p) as t:
            ...
        t["duration_ms"]  # disponivel depois
    """
    t0 = time.perf_counter()
    ctx: dict[str, Any] = {"op": op, **extra}
    span = tracer().start_span(op, attributes={"variant": VARIANT, **{k: str(v) for k, v in extra.items()}})
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
