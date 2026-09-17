from prometheus_client import Counter, Histogram

UPLOAD_COUNT = Counter(
    "pdf_uploads_total",
    "Total count of PDF upload attempts",
    ["tenant_id", "status"]
)

UPLOAD_LATENCY = Histogram(
    "pdf_upload_duration_seconds",
    "Time taken to process and store PDF uploads",
    buckets=[0.1, 0.5, 1.0, 2.0, 5.0, 10.0]
)