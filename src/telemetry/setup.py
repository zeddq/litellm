import logging
import os
from typing import Optional

from fastapi import FastAPI
from opentelemetry import trace
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter

from opentelemetry._logs import set_logger_provider
from opentelemetry.sdk._logs import LoggerProvider, LoggingHandler
from opentelemetry.sdk._logs.export import BatchLogRecordProcessor, ConsoleLogExporter
from opentelemetry.exporter.otlp.proto.http._log_exporter import OTLPLogExporter
from opentelemetry.instrumentation.logging import LoggingInstrumentor
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor

def _append_trace_path(endpoint: str) -> str:
    if endpoint.endswith("/"):
        return endpoint + "v1/traces"
    return endpoint + "/v1/traces"

def setup_telemetry(service_name: str, app: Optional[FastAPI] = None, otlp_endpoint: Optional[str] = None):
    """
    Sets up OpenTelemetry logging and tracing instrumentation.
    
    Args:
        service_name: The name of the service (e.g. 'litellm-interceptor')
        app: Optional FastAPI app to instrument.
        otlp_endpoint: Optional OTLP endpoint URL. If None, will check OTEL_EXPORTER_OTLP_ENDPOINT env var.
    """
    # 1. Resource Configuration
    resource = Resource.create({"service.name": service_name})
    endpoint = otlp_endpoint or os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT")
    
    # Append /v1/traces to endpoint if using HTTP exporter
    # The OTLP HTTP exporter typically requires the full path
    trace_endpoint = _append_trace_path(endpoint) if endpoint else None

    # 2. Tracing Setup
    tracer_provider = TracerProvider(resource=resource)
    if endpoint:
        span_exporter = OTLPSpanExporter(endpoint=trace_endpoint)
        span_processor = BatchSpanProcessor(span_exporter)
        tracer_provider.add_span_processor(span_processor)
    
    trace.set_tracer_provider(tracer_provider)

    # Instrument FastAPI if app is provided
    if app:
        def request_hook(span, scope):
            """
            Capture specific headers as span attributes.
            """
            if span and span.is_recording():
                headers = scope.get("headers", [])
                # Headers are a list of [key, value] byte tuples in ASGI scope
                for key, value in headers:
                    key_str = key.decode("utf-8").lower()
                    if key_str in ["content-length", "content-type", "user-agent", "x-memory-user-id"]:
                        span.set_attribute(f"http.header.{key_str}", value.decode("utf-8"))
                        
        def client_hook(span, scope, message):
            request_hook(span, scope)
            
        FastAPIInstrumentor.instrument_app(
            app, 
            tracer_provider=tracer_provider,
            http_capture_headers_server_request=["content-length", "content-type", "user-agent", "x-memory-user-id"],
            http_capture_headers_server_response=["content-length", "content-type", "user-agent", "x-memory-user-id"]
            # server_request_hook=request_hook,
            # client_request_hook=client_hook
        )

    # 3. Logging Setup
    logger_provider = LoggerProvider(resource=resource)
    set_logger_provider(logger_provider)

    # Only export logs if explicitly enabled, as we might only want trace correlation in console logs
    export_logs = os.environ.get("OTEL_EXPORT_LOGS", "false").lower() == "true"

    if endpoint and export_logs:
        # Use standard OTLP/HTTP logs endpoint
        logs_endpoint = endpoint + "/v1/logs" if not endpoint.endswith("/") else endpoint + "v1/logs"
        log_exporter = OTLPLogExporter(endpoint=logs_endpoint)
        log_processor = BatchLogRecordProcessor(log_exporter)
        logger_provider.add_log_record_processor(log_processor)
    else:
        # Fallback to console if no endpoint provided or logs export disabled
        # This ensures we still see logs (with trace IDs) in the container output
        logger_provider.add_log_record_processor(
            BatchLogRecordProcessor(ConsoleLogExporter())
        )

    # 4. Attach OTel Handler to Root Logger
    handler = LoggingHandler(level=logging.NOTSET, logger_provider=logger_provider)
    logging.getLogger().addHandler(handler)
    
    # 5. Instrument Logging
    # Define a format that includes trace_id and span_id
    logging_format = "%(asctime)s - %(name)s - %(levelname)s - [trace_id=%(otelTraceID)s span_id=%(otelSpanID)s] - %(message)s"
    LoggingInstrumentor().instrument(set_logging_format=True, logging_format=logging_format)

