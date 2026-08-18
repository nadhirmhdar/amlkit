FROM python:3.11-slim

# Install system dependencies + Google Cloud SDK (for gsutil to restore DB from GCS)
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl ca-certificates sqlite3 gnupg apt-transport-https \
    graphviz tesseract-ocr tesseract-ocr-eng tesseract-ocr-ara \
    && echo "deb [signed-by=/usr/share/keyrings/cloud.google.gpg] https://packages.cloud.google.com/apt cloud-sdk main" \
       | tee /etc/apt/sources.list.d/google-cloud-sdk.list \
    && curl -fsSL https://packages.cloud.google.com/apt/doc/apt-key.gpg \
       | gpg --dearmor -o /usr/share/keyrings/cloud.google.gpg \
    && apt-get update && apt-get install -y --no-install-recommends google-cloud-cli \
    && rm -rf /var/lib/apt/lists/*

# Litestream: continuous SQLite -> GCS replication. Previously this repo
# shipped a litestream.yml that nothing ever executed -- entrypoint.sh only
# restored a snapshot once at container startup, so every write made during
# a container's lifetime was lost the moment Cloud Run recycled the instance.
# entrypoint.sh now runs the app under `litestream replicate -exec`.
RUN curl -fsSL -o /tmp/litestream.deb \
      https://github.com/benbjohnson/litestream/releases/download/v0.5.16/litestream-0.5.16-linux-x86_64.deb \
    && dpkg -i /tmp/litestream.deb \
    && rm /tmp/litestream.deb

WORKDIR /app

# Install Python requirements
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application files
COPY amlkit ./amlkit
COPY scripts ./scripts
COPY litestream.yml ./litestream.yml

# Create data directory for database
RUN mkdir -p /app/data && chmod +x /app/scripts/entrypoint.sh

# Environment defaults
ENV PORT=8000
ENV AMLKIT_DB=/app/data/amlkit.db
ENV AMLKIT_BIND_HOST=0.0.0.0
ENV AMLKIT_BEHIND_PROXY=1

EXPOSE 8000

ENTRYPOINT ["/app/scripts/entrypoint.sh"]
