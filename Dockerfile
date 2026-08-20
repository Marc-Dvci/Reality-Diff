FROM python:3.12-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    REALITYDIFF_ENV=demo \
    REALITYDIFF_ROOT=/app \
    REALITYDIFF_STATE_PATH=/tmp/reality-diff-state.json \
    REALITYDIFF_UPLOADS_ROOT=/tmp/reality-diff-uploads

WORKDIR /app

RUN addgroup --system realitydiff && adduser --system --ingroup realitydiff realitydiff

COPY pyproject.toml README.md ./
COPY src ./src
COPY web ./web
COPY var/.gitkeep ./var/.gitkeep

RUN python -m pip install --upgrade pip && python -m pip install ".[google]"

USER realitydiff
EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8080/ready', timeout=2)"

CMD ["uvicorn", "realitydiff.api:app", "--host", "0.0.0.0", "--port", "8080", "--proxy-headers"]
