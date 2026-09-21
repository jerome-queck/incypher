#!/bin/sh
set -eu

day1_llm_env_file=${DAY1_LLM_ENV_FILE:-/opt/agent/.day1-llm.env}

# The organiser's complete runtime configuration always wins. A partial runtime
# configuration is left untouched so the Brain reports it instead of mixing providers.
if [ -r "$day1_llm_env_file" ] && \
   [ -z "${LLM_BASE_URL+x}" ] && \
   [ -z "${LLM_MODEL+x}" ] && \
   [ -z "${LLM_API_KEY+x}" ]; then
    set -a
    . "$day1_llm_env_file"
    set +a
fi
unset day1_llm_env_file

# Day 2 injects only endpoint and key. Supply the image's model policy without
# mixing it into any partial/explicit three-variable configuration.
if [ -z "${LLM_MODEL+x}" ] && \
   [ -n "${LLM_BASE_URL-}" ] && \
   [ -n "${LLM_API_KEY-}" ] && \
   [ -n "${ARENA_DEFAULT_LLM_MODEL-}" ]; then
    LLM_MODEL=$ARENA_DEFAULT_LLM_MODEL
    LLM_MODEL_AUTO_DISCOVER=1
    export LLM_MODEL LLM_MODEL_AUTO_DISCOVER
fi
unset ARENA_DEFAULT_LLM_MODEL

if [ -r /opt/agent/.validation-id ]; then
    exec python /opt/agent/validation_main.py
fi

exec python /opt/agent/arena_main.py
