FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

RUN apt-get update \
    && apt-get install -y --no-install-recommends libglib2.0-0 libgl1 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY pyproject.toml README.md ./
COPY src ./src
COPY scripts ./scripts
COPY models/motion_samples.json ./models/motion_samples.json

RUN pip install --no-cache-dir .
RUN python scripts/download_models.py --output-dir /app/models

CMD ["gesture-recognition"]
