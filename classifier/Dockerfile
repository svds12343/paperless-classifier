FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

RUN groupadd --system classifier && useradd --system --gid classifier --home /app classifier
WORKDIR /app
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY classifier.py taxonomy.yaml ./
RUN mkdir -p /state && chown -R classifier:classifier /app /state
USER classifier

HEALTHCHECK --interval=60s --timeout=10s --start-period=20s --retries=3 \
  CMD ["python", "/app/classifier.py", "health"]

CMD ["python", "/app/classifier.py", "daemon"]
