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

if [ -r /opt/agent/.validation-id ]; then
    exec python /opt/agent/validation_main.py
fi

exec python /opt/agent/arena_main.py
