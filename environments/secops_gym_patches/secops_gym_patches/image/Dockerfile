# One box per rollout: the task's FastAPI service, a local Postgres on 5433, and the
# in-box scorer. The agent works as the unprivileged `agent` user in /app; /opt/gym
# (scorer + hidden tests at grading time) is root-only.
FROM python:3.13-alpine

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONHASHSEED=0 \
    TZ=UTC \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

RUN apk add --no-cache postgresql17 bash patch procps

COPY requirements.txt /tmp/requirements.txt
RUN pip install -r /tmp/requirements.txt && rm /tmp/requirements.txt

RUN mkdir -p /var/lib/gympg /run/postgresql && chown postgres:postgres /var/lib/gympg /run/postgresql \
    && su postgres -s /bin/sh -c "initdb -D /var/lib/gympg --auth-local=peer --auth-host=scram-sha-256 -E UTF8 --locale=C.UTF-8" \
    && printf "port = 5433\nlisten_addresses = '127.0.0.1'\nfsync = off\nsynchronous_commit = off\n" >> /var/lib/gympg/postgresql.conf \
    && su postgres -s /bin/sh -c "pg_ctl -D /var/lib/gympg -w start" \
    && su postgres -s /bin/sh -c "psql -p 5433 -c \"CREATE ROLE gym LOGIN PASSWORD 'gym'\" -c 'CREATE DATABASE gym OWNER gym'" \
    && su postgres -s /bin/sh -c "pg_ctl -D /var/lib/gympg -w stop"

RUN adduser -D agent && mkdir -p /app && chown agent:agent /app

COPY start_db.sh score_box.py /opt/gym/
RUN chmod 700 /opt/gym && chmod 700 /opt/gym/start_db.sh /opt/gym/score_box.py

WORKDIR /app
