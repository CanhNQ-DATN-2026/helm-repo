# AIOps Bot Deployment

The AIOps bot is deployed via a standalone Helm chart in the `helm-repo` repository.

## Repository Structure

- **terraform-infra**: IAM role (IRSA) for AWS access
- **helm-repo/aiops-bot**: Helm chart for Kubernetes deployment
- **aiops-bot**: Bot application code

## Deployment Guide

See the full deployment guide in the Helm chart:
```
~/repo/CanhNQ-DATN-2026/helm-repo/aiops-bot/README.md
```

## Quick Start

### 1. Apply Terraform (IRSA Role)

```bash
cd ~/repo/CanhNQ-DATN-2026/terraform-infra
terraform apply
terraform output aiops_bot_role_arn
```

### 2. Create Secret

```bash
kubectl create secret generic aiops-bot-secret \
  --from-literal=anthropic_api_key=YOUR_KEY \
  --from-literal=telegram_bot_token=YOUR_TOKEN \
  --from-literal=telegram_chat_id=YOUR_CHAT_ID \
  -n bookgate
```

### 3. Deploy via Helm

```bash
cd ~/repo/CanhNQ-DATN-2026/helm-repo
helm install aiops-bot ./aiops-bot \
  -n bookgate \
  -f aiops-bot/values.yaml \
  -f aiops-bot/values-dev.yaml
```

## Verification

```bash
kubectl get pods -n bookgate -l app.kubernetes.io/name=aiops-bot
kubectl logs -n bookgate -l app.kubernetes.io/name=aiops-bot
```
