FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    MPLCONFIGDIR=/home/app/.matplotlib

RUN useradd --create-home --uid 10001 app
WORKDIR /app

COPY pyproject.toml ./
COPY app ./app
RUN pip install .

USER app
# Build matplotlib's font cache now so the container can run with a read-only filesystem.
RUN python -c "import matplotlib.font_manager"

EXPOSE 8080
CMD ["sh", "-c", "exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8080}"]
