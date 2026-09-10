ARG base_image=ghcr.io/leolani/cltl-base:latest
FROM ${base_image}

WORKDIR /app

COPY requirements.txt ./
RUN pip install -r requirements.txt

COPY src/ ./src/
ENV PYTHONPATH=/app/src

COPY app.py ./

HEALTHCHECK --interval=10s --timeout=5s --start-period=30s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

CMD ["python", "app.py"]
