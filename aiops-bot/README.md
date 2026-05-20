# AIOps Bot Helm Chart

Standalone Helm chart for the Bookgate AIOps monitoring bot.

## Prerequisites

1. Terraform has created the EKS cluster, OIDC provider, and `aiops_bot_role_arn`.
2. External Secrets Operator is installed.
3. `ClusterSecretStore/aws-secretsmanager` exists.
4. AWS Secrets Manager contains `bookgate/dev/aiops-bot-secrets`.

## Installation

### 1. Get the IAM Role ARN from Terraform

```bash
cd ~/repo/CanhNQ-DATN-2026/terraform-infra
terraform apply
terraform output aiops_bot_role_arn
```

### 2. Create Secrets in AWS Secrets Manager

```bash
aws secretsmanager create-secret \
  --name bookgate/dev/aiops-bot-secrets \
  --description "AIOps bot credentials" \
  --secret-string '{
    "telegram_bot_token": "YOUR_TELEGRAM_TOKEN",
    "telegram_alert_bot_token": "YOUR_ALERT_TELEGRAM_TOKEN",
    "telegram_chat_id": "YOUR_CHAT_ID"
  }' \
  --region us-east-1
```

The chart creates an `ExternalSecret` when `externalSecrets.enabled: true`.

### 3. Update values.yaml

```yaml
serviceAccount:
  roleArn: "arn:aws:iam::392423995152:role/bookgate-eks-aiops-bot-role"

image:
  tag: "9796a2f"  # usually bumped by GitHub Actions

externalSecrets:
  enabled: true
  remoteSecretName: "bookgate/dev/aiops-bot-secrets"

telegram:
  allowlist:
    enabled: true
    userIds:
      - "6855542290"
```

`userIds` are Telegram users allowed to use the bot in private chats and groups. The bot is fail-closed if the allowlist is enabled but empty.

### 4. Install the Chart

```bash
cd ~/repo/CanhNQ-DATN-2026/helm-repo

helm install aiops-bot ./aiops-bot \
  -n bookgate \
  --create-namespace \
  -f aiops-bot/values.yaml

helm upgrade aiops-bot ./aiops-bot \
  -n bookgate \
  -f aiops-bot/values.yaml
```

## Verification

```bash
# Check deployment
kubectl get deploy aiops-bot -n bookgate

# Check pods
kubectl get pods -n bookgate -l app.kubernetes.io/name=aiops-bot

# Check logs
kubectl logs -n bookgate -l app.kubernetes.io/name=aiops-bot

# Check ServiceAccount IRSA annotation
kubectl get sa aiops-bot -n bookgate -o yaml | grep role-arn

# Check RBAC
kubectl get clusterrole aiops-bot-reader
kubectl get clusterrolebinding aiops-bot-reader

# Check External Secret (if enabled)
kubectl get externalsecret aiops-bot-secret -n bookgate
kubectl describe externalsecret aiops-bot-secret -n bookgate

# Verify the K8s secret was created by ESO
kubectl get secret aiops-bot-secret -n bookgate
```

## Configuration

### Values

| Parameter | Description | Default |
|-----------|-------------|---------|
| `ecr.registry` | ECR registry URL | `ACCOUNT_ID.dkr.ecr.REGION.amazonaws.com` |
| `image.repository` | Image repository | `bookgate/aiops-bot` |
| `image.tag` | Image tag | `latest` |
| `image.pullPolicy` | Image pull policy | `Always` |
| `replicas` | Number of replicas | `1` |
| `port` | Container port | `8080` |
| `serviceAccount.name` | ServiceAccount name | `aiops-bot` |
| `serviceAccount.roleArn` | IRSA role ARN | `""` |
| `claude.models.default` | Default Claude Code Bedrock model ID | `us.anthropic.claude-haiku-4-5-20251001-v1:0` |
| `claude.models.health` | Model for health/status requests | `us.anthropic.claude-haiku-4-5-20251001-v1:0` |
| `claude.models.troubleshoot` | Model for troubleshooting requests | `us.anthropic.claude-haiku-4-5-20251001-v1:0` |
| `claude.models.change` | Model for change/provisioning requests | `us.anthropic.claude-haiku-4-5-20251001-v1:0` |
| `claude.models.explain` | Model for explanation requests | `us.anthropic.claude-haiku-4-5-20251001-v1:0` |
| `claude.models.unknown` | Model for unknown/ambiguous requests | `us.anthropic.claude-haiku-4-5-20251001-v1:0` |
| `claude.outputTokenLimit` | Target output token budget | `1200` |
| `resources.requests.cpu` | CPU request | `100m` |
| `resources.requests.memory` | Memory request | `256Mi` |
| `resources.limits.cpu` | CPU limit | `500m` |
| `resources.limits.memory` | Memory limit | `512Mi` |
| `externalSecrets.enabled` | Enable External Secrets Operator | `true` |
| `externalSecrets.clusterSecretStoreName` | ClusterSecretStore name | `aws-secretsmanager` |
| `externalSecrets.remoteSecretName` | AWS Secrets Manager secret name | `bookgate/dev/aiops-bot-secrets` |
| `externalSecrets.refreshInterval` | ESO refresh interval | `1h` |
| `telegram.allowlist.enabled` | Mount Telegram allowlist ConfigMap | `true` |
| `telegram.allowlist.userIds` | Allowed Telegram user IDs | `["6855542290"]` |
| `existingSecret` | Secret name for credentials | `aiops-bot-secret` |
| `namespace` | Target namespace | `bookgate` |

## Components

- **Deployment**: Single replica bot deployment
- **Service**: ClusterIP service on port 8080
- **ServiceAccount**: With IRSA annotation for AWS access
- **ConfigMap**: Telegram user allowlist
- **ClusterRole**: Read-only access to pods, events, deployments, ArgoCD apps
- **ClusterRoleBinding**: Binds ServiceAccount to ClusterRole
- **ExternalSecret** (optional): Syncs secrets from AWS Secrets Manager

## AWS Permissions (via IRSA)

The bot has the following AWS permissions:
- `rds:DescribeDBInstances`
- `rds:DescribeEvents`
- `cloudwatch:GetMetricStatistics`
- `cloudwatch:ListMetrics`
- `sts:AssumeRole` to the configured Bedrock role

The ServiceAccount also currently has `AdministratorAccess` attached in Terraform for lab/demo operations. Narrow this before production use.

## Uninstall

```bash
helm uninstall aiops-bot -n bookgate
```
