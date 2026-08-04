# Optional custom Airflow image for RegGraph AI v2.
# docker-compose uses the official image with _PIP_ADDITIONAL_REQUIREMENTS instead.
# Build with: docker build -t reggraph-airflow:2.8.4 -f docker/airflow/Dockerfile .

FROM apache/airflow:2.8.4-python3.11

USER root
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

USER airflow
RUN pip install --no-cache-dir pyyaml httpx redis chromadb
