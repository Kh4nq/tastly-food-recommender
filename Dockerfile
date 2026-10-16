FROM python:3.11-slim-bookworm

WORKDIR /app

ENV PYTHONUNBUFFERED=1
ENV PIP_NO_CACHE_DIR=1

RUN apt-get update && apt-get install -y --no-install-recommends libgomp1 && rm -rf /var/lib/apt/lists/*

COPY . .

RUN python -m pip install torch --index-url https://download.pytorch.org/whl/cpu && \
    python -m pip install -e ".[ai1,ai3,db,backend]" && \
    python -c "import uvicorn, fastapi, torch; print('Backend dependencies OK')"

EXPOSE 8080

CMD ["sh", "-c", "exec python -m uvicorn backend.main:create_production_app --factory --host 0.0.0.0 --port ${PORT:-8080}"]
