# syntax = docker/dockerfile:1.2

FROM python:3.10-alpine AS build

WORKDIR /app

RUN apk add --no-cache git

COPY requirements.txt ./

# Build and install Python deps to a temp prefix
RUN pip install --upgrade pip \
 && pip install --no-cache-dir --prefix=/install -r requirements.txt


FROM python:3.10-alpine AS runtime

WORKDIR /app

# Install runtime libraries
RUN apk add --no-cache \
    openblas \
    lapack \
    libstdc++

# Copy prebuilt Python environment
COPY --from=build /install /usr/local

# Copy app
COPY . ./

ENV PYTHONPATH=/app/src

CMD ["python", "app.py"]
