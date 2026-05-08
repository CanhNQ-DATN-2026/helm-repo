#!/bin/sh
set -e

# ANTHROPIC_API_KEY must be set at runtime (docker run -e or k8s secret).
# Claude Code CLI picks it up automatically from the environment.
if [ -z "$ANTHROPIC_API_KEY" ]; then
  echo "[entrypoint] WARNING: ANTHROPIC_API_KEY is not set — Claude calls will fail"
fi

exec python3 main.py
