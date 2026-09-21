#!/bin/sh
set -eu

image=${1:?usage: scripts/check_image.sh <image>}

docker run --rm --platform linux/amd64 --entrypoint python3 "$image" -c '
import agent_ext.contracts
import agent_ext.controller
import agent_ext.memory
import agent_ext.resources
import agent_ext.results
import agent_ext.retry_policy
import agent_ext.scheduler
import agent_ext.strategy_bridge
import agent_ext.submission_state
import agent_ext.tools.executor
import agent_ext.tools.inspection
import agent_ext.verification
import brain
import arena_main
import validation_main
assert brain.Brain.__module__ == "brain"
print("PASS: Brain and all merged agent_ext modules import from image")
'
