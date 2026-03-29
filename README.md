# Bookgate — Helm Repo

Helm chart repo for deploying Bookgate application workloads to EKS.

This repo deploys only:
- `api-service`
- `chat-service`
- `frontend`

It does not provision infrastructure. AWS infra is owned by the Terraform repo.

## Chart layout

```text
helm-charts/
└── bookgate/
    ├── Chart.yaml
    ├── values.yaml
    └── templates/
        ├── _helpers.tpl
        ├── serviceaccount.yaml
        ├── external-secret.yaml
        ├── api-service-deployment.yaml
        ├── api-service-service.yaml
        ├── chat-service-deployment.yaml
        ├── chat-service-service.yaml
        ├── frontend-deployment.yaml
        ├── frontend-service.yaml
        └── ingress.yaml
```

## Secret contract

### Source of truth
- AWS Secrets Manager secret: `bookgate/<env>/app-secrets`
- K8s Secret created by ESO: `bookgate-secret`

Expected properties inside AWS Secrets Manager:
- `DATABASE_URL`
- `SECRET_KEY`
- `ADMIN_PASSWORD`
- `OPENAI_API_KEY`

### How it works
```text
Terraform
  -> creates app secret shell in AWS Secrets Manager
Operator
  -> populates the 4 required properties
ESO
  -> reads ExternalSecret from this chart
  -> creates/updates K8s Secret: bookgate-secret
Pods
  -> read values with secretKeyRef
```

### DATABASE_URL
`DATABASE_URL` is not generated automatically by the chart.

It must be constructed once by the operator from:
- Terraform output `rds_endpoint`
- Terraform output `db_credentials_secret_arn` (RDS-managed password secret)

Then stored into:
- `bookgate/<env>/app-secrets`

## IRSA

The chart creates `backend-sa` and annotates it with:
- `apiService.serviceAccount.roleArn`

`api-service` uses this ServiceAccount for S3 access.

Expected permissions on the backend IRSA role:
- `s3:PutObject`
- `s3:GetObject`
- `s3:DeleteObject`
- `s3:ListBucket`

App pods do not need Secrets Manager permissions.

## Values that must be set per environment

Minimum important overrides:

| Key | Meaning |
|---|---|
| `ecr.registry` | Terraform output `ecr_registry_url` |
| `apiService.image.tag` | image tag for api-service |
| `chatService.image.tag` | image tag for chat-service |
| `frontend.image.tag` | image tag for frontend |
| `apiService.serviceAccount.roleArn` | Terraform output `backend_role_arn` |
| `apiService.env.s3BucketName` | Terraform output `s3_bucket_name` |
| `ingress.host` | public hostname |
| `ingress.certificateArn` | ACM cert ARN if using HTTPS |
| `externalSecrets.remoteSecretName` | e.g. `bookgate/dev/app-secrets` or `bookgate/prod/app-secrets` |

## Operational flow

### First install
1. Run `terraform apply`
2. Populate AWS Secrets Manager app secret
3. Install ESO and create `ClusterSecretStore`
4. Run `helm upgrade --install`
5. Wait until `ExternalSecret` is synced and `bookgate-secret` exists
6. Run DB migration explicitly

### Upgrade
1. Update image tags
2. Run `helm upgrade`
3. If schema changed, run DB migration explicitly

Migration is not a Helm hook in the current design.

## Example deploy command

```bash
helm upgrade --install bookgate ./bookgate \
  --namespace bookgate \
  --create-namespace \
  --set ecr.registry="$ECR_REGISTRY" \
  --set apiService.image.tag="$IMAGE_TAG" \
  --set chatService.image.tag="$IMAGE_TAG" \
  --set frontend.image.tag="$IMAGE_TAG" \
  --set apiService.serviceAccount.roleArn="$BACKEND_ROLE_ARN" \
  --set apiService.env.s3BucketName="$S3_BUCKET_NAME" \
  --set externalSecrets.remoteSecretName="$REMOTE_SECRET_NAME" \
  --set ingress.host="$INGRESS_HOST" \
  --set ingress.certificateArn="$CERTIFICATE_ARN"
```

## CI/CD

Pipeline file: `.gitlab-ci.yml`

Stages:
- `lint`
- `deploy`

Behavior:
- `lint`: `helm lint bookgate/`
- `deploy`: GitLab OIDC -> assume AWS role -> `aws eks update-kubeconfig` -> `helm upgrade --install`

Current trigger behavior:
- push to helm repo default branch -> manual deploy job
- pipeline trigger -> auto deploy job

Required GitLab CI variables:
- `AWS_ROLE_ARN`
- `AWS_REGION`
- `ECR_REGISTRY`
- `EKS_CLUSTER_NAME`
- `BACKEND_ROLE_ARN`
- `CERTIFICATE_ARN`

Recommended additional variables:
- `REMOTE_SECRET_NAME`
- `INGRESS_HOST`

## EKS auth for Helm CI

The Helm CI role needs:
- AWS IAM: at least `eks:DescribeCluster`
- EKS auth mapping into the cluster
- Kubernetes RBAC suitable for deploying into namespace `bookgate`

Prefer least-privilege RBAC over broad `system:masters`.

## Validation

```bash
helm lint bookgate/

helm template bookgate bookgate/ \
  --set ecr.registry=123456789.dkr.ecr.us-east-1.amazonaws.com \
  --set apiService.image.tag=abc1234 \
  --set chatService.image.tag=abc1234 \
  --set frontend.image.tag=abc1234 \
  --set apiService.serviceAccount.roleArn=arn:aws:iam::123456789012:role/bookgate-eks-backend-role \
  --set apiService.env.s3BucketName=bookgate-dev-books-123456789012 \
  --set externalSecrets.remoteSecretName=bookgate/dev/app-secrets \
  --set ingress.host=bookgate.example.com
```
