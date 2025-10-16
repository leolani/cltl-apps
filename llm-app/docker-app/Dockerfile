# syntax = docker/dockerfile:1.2

FROM python:3.10 as base

SHELL ["/bin/bash", "-c"]

RUN apt-get update && apt-get install -y --no-install-recommends \
        less \
        vim \
        gcc \
        build-essential \
        zlib1g-dev \
        wget \
        unzip \
        cmake \
        gfortran \
        libblas-dev \
        liblapack-dev \
        libopenblas-dev \
        libasound-dev \
        libportaudio2 \
        libportaudiocpp0 \
        portaudio19-dev \
        ffmpeg \
        libsm6 \
        libxext6 \
    && apt-get clean


FROM base as build

SHELL ["/bin/bash", "-c"]

WORKDIR /app
COPY . ./

RUN python -m venv venv
RUN source /app/venv/bin/activate && pip install -r requirements.txt


# To build a specfic stage only use the --target option, e.g.:
# docker build --target build --tag build:0.0.1 .
FROM base as app

COPY --from=build /app /app/

ENV PYTHONPATH="/app/src:${PYTHONPATH}"

WORKDIR /app
CMD ["/bin/bash", "-c", "source /app/venv/bin/activate && python app.py"]
