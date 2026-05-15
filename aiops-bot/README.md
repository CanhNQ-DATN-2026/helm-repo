# AIOps Bot Helm Chart

Standalone Helm chart for the Bookgate AIOps monitoring bot.

## Prerequisites

1. **Terraform IRSA Role**: Apply the aiops-bot IAM role from `terraform-infra/irsa.tf`
2. **Secrets**: Choose between manual K8s Secret or External Secrets Operator
3. **Cluster**: EKS cluster with OIDC provider configured
4. **External Secrets Operator** (optional): If using ESO, ensure ClusterSecretStore is configured

## Installation

### 1. Get the IAM Role ARN from Terraform

```bash
cd ~/repo/CanhNQ-DATN-2026/terraform-infra
terraform apply
terraform output aiops_bot_role_arn
```

### 2. Create Secrets in AWS Secrets Manager (Recommended)

```bash
# Create the secret in AWS Secrets Manager
aws secretsmanager create-secret \
  --name bookgate/dev/aiops-bot-secrets \
  --description "AIOps bot credentials" \
  --secret-string '{
    "anthropic_api_key": "YOUR_ANTHROPIC_KEY",
    "telegram_bot_token": "YOUR_TELEGRAM_TOKEN",
    "telegram_chat_id": "YOUR_CHAT_ID"
  }' \
  --region us-east-1
```

The Helm chart will automatically create an ExternalSecret resource when `externalSecrets.enabled: true`.

**Alternative: Manual K8s Secret**

If you prefer not to use External Secrets Operator:

```bash
kubectl create secret generic aiops-bot-secret \
  --from-literal=anthropic_api_key=YOUR_ANTHROPIC_KEY \
  --from-literal=telegram_bot_token=YOUR_TELEGRAM_TOKEN \
  --from-literal=telegram_chat_id=YOUR_CHAT_ID \
  -n bookgate
```

Then disable External Secrets in your values:
```yaml
externalSecrets:
  enabled: false
```

### 3. Update values.yaml

```yaml
serviceAccount:
  roleArn: "arn:aws:iam::392423995152:role/bookgate-eks-aiops-bot-role"

image:
  tag: "latest"  # or specific commit SHA

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

# Install
helm install aiops-bot ./aiops-bot \
  -n bookgate \
  -f aiops-bot/values.yaml

# Upgrade
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
| `resources.requests.cpu` | CPU request | `100m` |
| `resources.requests.memory` | Memory request | `256Mi` |
| `resources.limits.cpu` | CPU limit | `500m` |
| `resources.limits.memory` | Memory limit | `512Mi` |
| `externalSecrets.enabled` | Enable External Secrets Operator | `false` |
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

## Uninstall

```bash
helm uninstall aiops-bot -n bookgate
```
