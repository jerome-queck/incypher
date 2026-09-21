#!/bin/sh
set -eu

if [ -r /opt/agent/.day1-llm.env ]; then
    set -a
    . /opt/agent/.day1-llm.env
    set +a
fi

if [ -r /opt/agent/.validation-id ]; then
    exec python /opt/agent/validation_main.py
fi

exec python /opt/agent/main.py
