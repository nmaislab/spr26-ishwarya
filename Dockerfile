FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONPATH=/app \
    STREAMLIT_SERVER_ADDRESS=0.0.0.0 \
    STREAMLIT_SERVER_PORT=8501 \
    MAOF_RUNTIME_CACHE_DIR=/tmp/maof_runtime_cache

WORKDIR /app

COPY requirements.txt .
RUN python -m pip install --no-cache-dir --upgrade pip \
    && python -m pip install --no-cache-dir -r requirements.txt

COPY . .

RUN useradd --create-home --shell /bin/bash appuser \
    && mkdir -p /app/results/logs /tmp/maof_runtime_cache \
    && chown -R appuser:appuser /app /tmp/maof_runtime_cache

USER appuser

EXPOSE 8501

CMD ["sh", "-c", "python -m streamlit run src/ui/ranking_eval_app.py --server.address=${STREAMLIT_SERVER_ADDRESS:-0.0.0.0} --server.port=${STREAMLIT_SERVER_PORT:-8501} --server.headless=true --browser.gatherUsageStats=false"]
