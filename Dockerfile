FROM registry.in-cypher.com:5001/base/agent-base:latest

COPY agent_ext /opt/agent/agent_ext
COPY brain.py /opt/agent/brain.py
