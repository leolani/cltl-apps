#syntax = docker/dockerfile:1.4

FROM ollama/ollama:latest AS ollama

RUN apt-get update \
    && apt-get -y install curl \
    && apt-get clean