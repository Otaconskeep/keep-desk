FROM python:3.11-slim-bookworm

RUN apt-get update && apt-get install -y --no-install-recommends \
      bash curl git ca-certificates python3-pip \
    && rm -rf /var/lib/apt/lists/* \
    && pip install --no-cache-dir pytest

WORKDIR /app
COPY api/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

COPY api/ /app/

ENV DESK_ROOT=/desk
ENV STATE_DIR=/desk/state
ENV PYTHONUNBUFFERED=1
ENV LOCAL_OLLAMA_URL=http://host.docker.internal:11434/v1
ENV LOCAL_MODEL=gpt-oss:20b

RUN mkdir -p /desk/home /desk/workspace /desk/skills /desk/routines \
             /desk/memory /desk/inbox /desk/outbox /desk/state \
             /desk/browser-profile /desk/workspace/screenshots /desk/workspace/projects

WORKDIR /app
