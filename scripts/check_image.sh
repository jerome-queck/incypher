#!/bin/sh
set -eu

image=${1:?usage: scripts/check_image.sh <image>}

docker run --rm --platform linux/amd64 --entrypoint python3 "$image" -c '
import agent_ext.contracts
import brain
assert brain.Brain.__module__ == "brain"
print("PASS: custom Brain and agent_ext contracts import from image")
'
