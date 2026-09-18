from prometheus_client import Counter, Histogram

UPLOAD_COUNTER = Counter(
    "manual_onboarding_uploads_total",
    "Total document upload attempts partitioned by status, tenant, and format",
    ["status", "tenant", "format"],
)

UPLOAD_LATENCY_SECONDS = Histogram(
    "manual_onboarding_upload_duration_seconds",
    "Time taken to validate, hash, persist, and register document upload",
    buckets=[0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0],
)