FROM registry.in-cypher.com:5001/base/agent-base:latest

COPY agent_ext /opt/agent/agent_ext
COPY brain.py /opt/agent/brain.py
COPY entrypoint.sh /opt/agent/entrypoint.sh

ARG INCLUDE_DAY1_LLM=0
RUN --mount=type=secret,id=day1_llm \
    if [ "$INCLUDE_DAY1_LLM" = "1" ]; then \
        test -r /run/secrets/day1_llm && \
        cp /run/secrets/day1_llm /opt/agent/.day1-llm.env && \
        chmod 0400 /opt/agent/.day1-llm.env; \
    fi

ENTRYPOINT ["/opt/agent/entrypoint.sh"]
