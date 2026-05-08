# AIOps Bot Helm Chart

Standalone Helm chart for the Bookgate AIOps monitoring bot.

## Prerequisites

1. **Terraform IRSA Role**: Apply the aiops-bot IAM role from `terraform-infra/irsa.tf`
2. **Secrets**: Create `aiops-bot-secret` in the target namespace
3. **Cluster**: EKS cluster with OIDC provider configured

## Installation

### 1. Get the IAM Role ARN from Terraform

```bash
cd ~/repo/CanhNQ-DATN-2026/terraform-infra
terraform output aiops_bot_role_arn
```

### 2. Create the Secret

```bash
kubectl create secret generic aiops-bot-secret \
  --from-literal=anthropic_api_key=YOUR_ANTHROPIC_KEY \
  --from-literal=telegram_bot_token=YOUR_TELEGRAM_TOKEN \
  --from-literal=telegram_chat_id=YOUR_CHAT_ID \
  -n bookgate
```

Or use External Secrets Operator:

```yaml
apiVersion: external-secrets.io/v1beta1
kind: ExternalSecret
metadata:
  name: aiops-bot-secret
  namespace: bookgate
spec:
  refreshInterval: 1h
  secretStoreRef:
    name: aws-secretsmanager
    kind: ClusterSecretStore
  target:
    name: aiops-bot-secret
    creationPolicy: Owner
  data:
    - secretKey: anthropic_api_key
      remoteRef:
        key: bookgate/dev/aiops-bot-secrets
        property: anthropic_api_key
    - secretKey: telegram_bot_token
      remoteRef:
        key: bookgate/dev/aiops-bot-secrets
        property: telegram_bot_token
    - secretKey: telegram_chat_id
      remoteRef:
        key: bookgate/dev/aiops-bot-secrets
        property: telegram_chat_id
```

### 3. Update values-dev.yaml

```yaml
serviceAccount:
  roleArn: "arn:aws:iam::392423995152:role/bookgate-eks-aiops-bot-role"

image:
  tag: "latest"  # or specific commit SHA
```

### 4. Install the Chart

```bash
cd ~/repo/CanhNQ-DATN-2026/helm-repo

# Install
helm install aiops-bot ./aiops-bot \
  -n bookgate \
  -f aiops-bot/values.yaml \
  -f aiops-bot/values-dev.yaml

# Upgrade
helm upgrade aiops-bot ./aiops-bot \
  -n bookgate \
  -f aiops-bot/values.yaml \
  -f aiops-bot/values-dev.yaml
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
| `existingSecret` | Secret name for credentials | `aiops-bot-secret` |
| `namespace` | Target namespace | `bookgate` |

## Components

- **Deployment**: Single replica bot deployment
- **Service**: ClusterIP service on port 8080
- **ServiceAccount**: With IRSA annotation for AWS access
- **ClusterRole**: Read-only access to pods, events, deployments, ArgoCD apps
- **ClusterRoleBinding**: Binds ServiceAccount to ClusterRole

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
