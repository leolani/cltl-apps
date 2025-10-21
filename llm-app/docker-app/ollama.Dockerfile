#syntax = docker/dockerfile:1.4

FROM ollama/ollama:latest

RUN apt-get update \
    && apt-get -y install curl \
    && apt-get clean