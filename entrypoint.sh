#!/bin/sh
set -e

# Build an AWS config that chains:
#   IRSA (Account A, web identity) → Bedrock role (Account B, assume role)
# Claude Code CLI picks up CLAUDE_CODE_USE_BEDROCK=1 and uses AWS_PROFILE=bedrock.

if [ -z "$AWS_BEDROCK_ROLE_ARN" ]; then
  echo "[entrypoint] ERROR: AWS_BEDROCK_ROLE_ARN is not set"
  exit 1
fi

if [ -z "$AWS_ROLE_ARN" ] || [ -z "$AWS_WEB_IDENTITY_TOKEN_FILE" ]; then
  echo "[entrypoint] ERROR: IRSA env vars (AWS_ROLE_ARN, AWS_WEB_IDENTITY_TOKEN_FILE) are not set"
  exit 1
fi

mkdir -p /root/.aws
cat > /root/.aws/config <<EOF
[profile irsa]
role_arn = ${AWS_ROLE_ARN}
web_identity_token_file = ${AWS_WEB_IDENTITY_TOKEN_FILE}

[profile bedrock]
role_arn = ${AWS_BEDROCK_ROLE_ARN}
source_profile = irsa
EOF

# Hand off to the bedrock profile; unset IRSA env vars to avoid SDK ambiguity
unset AWS_ROLE_ARN AWS_WEB_IDENTITY_TOKEN_FILE
export AWS_PROFILE=bedrock
export AWS_DEFAULT_REGION="${AWS_BEDROCK_REGION:-us-east-1}"

exec python3 main.py
