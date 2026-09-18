FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY schema/ ./schema/
COPY src/ ./src/
COPY mock_data/ ./mock_data/
COPY tests/ ./tests/

CMD ["python", "src/ingest.py", "mock_data/sample_entities.json"]
