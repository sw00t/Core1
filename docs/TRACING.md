# Adding tracing later

Tracing is out of scope for the base, but the pieces are shaped for it:

1. Services already propagate W3C `traceparent` and log `trace_id`. To emit spans, add
   `opentelemetry-sdk`, `opentelemetry-instrumentation-fastapi`, `opentelemetry-instrumentation-httpx`
   and `opentelemetry-exporter-otlp-proto-http` to `services/app/requirements.txt`, and in
   `core1app/common.py` initialise a tracer when `OTEL_EXPORTER_OTLP_ENDPOINT` is set.
2. Add a Tempo deployment next to Loki (`observability/tempo/`), single binary, local storage.
3. In `observability/alloy/alloy.yaml` add an `otelcol.receiver.otlp` block forwarding to
   `otelcol.exporter.otlp` pointed at Tempo, and set `OTEL_EXPORTER_OTLP_ENDPOINT` in the config repo's
   `*.env` files to Alloy's OTLP port.
4. Add a Tempo datasource to Grafana in `kube-prometheus-stack-values.yaml` (`additionalDataSources`),
   with `derivedFields` on the Loki datasource so `trace_id` in logs links to the trace.
