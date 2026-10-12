FROM python:3.12-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

COPY requirements.txt /app/requirements.txt

RUN pip install --no-cache-dir -r /app/requirements.txt \
    && useradd --system --uid 10001 --create-home appuser \
    && mkdir -p /data/inbox /data/outbox /data/jobs \
    && chown -R appuser:appuser /app /data

COPY --chown=appuser:appuser common.py web.py worker.py convert_one.py mcp_server.py /app/

USER 10001:10001

EXPOSE 8095 8096

CMD ["uvicorn", "web:app", "--host", "0.0.0.0", "--port", "8095"]