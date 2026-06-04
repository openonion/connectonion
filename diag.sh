#!/bin/bash
# Chain: local -> Lightsail (oo-api) -> GCE VM.
# 1) find the current co-ai-test container, 2) run the agent directly
# (bypassing xvfb-run) so the real startup error is visible.
LSKEY=/Users/yfshuu/coding/key/openonion-key.pem
GKEY=/home/ubuntu/.ssh/gce_deploy_key
GHOST="changxing@35.247.187.240"

CID=$(ssh -i $LSKEY ubuntu@3.24.102.245 "ssh -i $GKEY -o StrictHostKeyChecking=no $GHOST 'docker ps -q -f name=co-ai-test | head -1'" | tr -d '[:space:]')
echo "container: [$CID]"
if [ -z "$CID" ]; then echo "no co-ai-test container running yet — wait for the build to finish, then rerun"; exit 0; fi

echo "=== running: python agent.py (25s) ==="
ssh -i $LSKEY ubuntu@3.24.102.245 "ssh -i $GKEY -o StrictHostKeyChecking=no $GHOST 'docker exec $CID timeout 25 python agent.py'"
