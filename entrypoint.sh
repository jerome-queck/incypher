#!/bin/sh
set -eu

if [ -r /opt/agent/.day1-llm.env ]; then
    set -a
    . /opt/agent/.day1-llm.env
    set +a
fi

exec python /opt/agent/main.py
