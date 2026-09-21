FROM registry.in-cypher.com:5001/base/agent-base:latest

COPY agent_ext /opt/agent/agent_ext
COPY brain.py /opt/agent/brain.py
COPY entrypoint.sh /opt/agent/entrypoint.sh
COPY validation_main.py /opt/agent/validation_main.py
COPY arena_main.py /opt/agent/arena_main.py

# Keep each challenge slice bounded so the persistent queue reaches all work.
# The arena may still override these ordinary runtime controls.
ENV MAX_STEPS=24 \
    MAX_TOOL_CALLS=28 \
    MAX_SUBMISSIONS=3 \
    ARENA_DEFAULT_LLM_MODEL=openai/gpt-5.6-luna

ARG INCLUDE_DAY1_LLM=0
RUN --mount=type=secret,id=day1_llm \
    if [ "$INCLUDE_DAY1_LLM" = "1" ]; then \
        test -r /run/secrets/day1_llm && \
        cp /run/secrets/day1_llm /opt/agent/.day1-llm.env && \
        chmod 0400 /opt/agent/.day1-llm.env; \
    fi

ARG VALIDATION_CHALLENGE_ID=""
RUN if [ -n "$VALIDATION_CHALLENGE_ID" ]; then \
        printf '%s\n' "$VALIDATION_CHALLENGE_ID" > /opt/agent/.validation-id && \
        chmod 0444 /opt/agent/.validation-id; \
    fi

ENTRYPOINT ["/opt/agent/entrypoint.sh"]
