# Bookgate — Helm Repo

Helm chart for deploying Bookgate to AWS EKS.

---

## Chart layout

```
helm-charts/
└── bookgate/
    ├── Chart.yaml
    ├── values.yaml
    └── templates/
        ├── _helpers.tpl
        ├── migrate-job.yaml          # Helm pre-install/pre-upgrade Job
        ├── api-service-deployment.yaml
        ├── api-service-service.yaml
        ├── chat-service-deployment.yaml
        ├── chat-service-service.yaml
        ├── frontend-deployment.yaml
        ├── frontend-service.yaml
        └── ingress.yaml              # ALB Ingress
```

---

## Required inputs before deploying

### 1. Kubernetes Secret

The chart reads from a pre-existing Secret named `bookgate-secret`
(configurable via `existingSecret`). Required keys:
`DATABASE_URL`, `SECRET_KEY`, `ADMIN_PASSWORD`, `OPENAI_API_KEY`.

**Primary path — External Secrets Operator (production)**

In production the secret is synced automatically from AWS Secrets Manager
by [External Secrets Operator](https://external-secrets.io/). The Terraform
repo creates the Secrets Manager entry; ESO keeps the K8s Secret in sync.
No manual `kubectl` step is needed on upgrades.

**Fallback — manual bootstrap (first-time or non-ESO environments)**

If ESO is not yet set up, create the secret once before the first `helm install`:

```bash
kubectl create secret generic bookgate-secret \
  --namespace bookgate \
  --from-literal=DATABASE_URL="postgresql://user:pass@rds-endpoint:5432/bookgate" \
  --from-literal=SECRET_KEY="<32+ char random string>" \
  --from-literal=ADMIN_PASSWORD="<admin password>" \
  --from-literal=OPENAI_API_KEY="sk-..."
```

This is a bootstrap fallback only. In steady-state production the secret
should be managed by ESO, not by hand.

### 2. Mandatory values.yaml overrides

| Key | Description |
|---|---|
| `ecr.registry` | ECR registry URL from Terraform output `ecr_registry_url` |
| `apiService.image.tag` | Image tag built by app repo CI |
| `chatService.image.tag` | Image tag built by app repo CI |
| `frontend.image.tag` | Image tag built by app repo CI |
| `migrate.image.tag` | Must match `apiService.image.tag` |
| `apiService.env.s3BucketName` | S3 bucket name from Terraform output `s3_bucket_name` |
| `ingress.host` | Public hostname (e.g. `bookgate.example.com`) |

---

## Image tag update flow

After the app repo CI pushes new images to ECR, update `values.yaml`:

```yaml
apiService:
  image:
    tag: "abc1234"   # new commit SHA
chatService:
  image:
    tag: "abc1234"
frontend:
  image:
    tag: "abc1234"
migrate:
  image:
    tag: "abc1234"
```

Commit and push to trigger `helm upgrade`.

---

## Deploy to EKS

```bash
# Authenticate to ECR (one-time per session)
aws ecr get-login-password --region ap-southeast-1 | \
  docker login --username AWS --password-stdin $ECR_REGISTRY

# First deploy
helm install bookgate ./bookgate \
  --namespace bookgate \
  --create-namespace \
  --set ecr.registry=$ECR_REGISTRY \
  --set apiService.image.tag=$IMAGE_TAG \
  --set chatService.image.tag=$IMAGE_TAG \
  --set frontend.image.tag=$IMAGE_TAG \
  --set migrate.image.tag=$IMAGE_TAG \
  --set apiService.env.s3BucketName=$S3_BUCKET \
  --set ingress.host=bookgate.example.com

# Upgrade
helm upgrade bookgate ./bookgate \
  --namespace bookgate \
  --set apiService.image.tag=$NEW_TAG \
  --set chatService.image.tag=$NEW_TAG \
  --set frontend.image.tag=$NEW_TAG \
  --set migrate.image.tag=$NEW_TAG
```

The pre-install/pre-upgrade migration Job runs Alembic migrations and
bootstraps the initial admin account before any Deployment rollout.
The upgrade is blocked if the Job fails.

---

## Ingress

The chart deploys an ALB Ingress via AWS Load Balancer Controller.

| Path | Backend |
|---|---|
| `/api/v1/chat` | chat-service (SSE — more specific, listed first) |
| `/api/v1` | api-service |
| `/` | frontend |

Key settings in `values.yaml`:

```yaml
ingress:
  host: bookgate.example.com
  scheme: internet-facing           # or internal
  idleTimeoutSeconds: 300           # must exceed longest SSE stream
  certificateArn: ""                # ACM ARN for HTTPS; empty = HTTP only
  groupName: bookgate               # ALB ingress group name
```

---

## Lint and dry-run

```bash
helm lint bookgate/

helm template bookgate bookgate/ \
  --set ecr.registry=123456789.dkr.ecr.ap-southeast-1.amazonaws.com \
  --set apiService.image.tag=abc1234 \
  --set chatService.image.tag=abc1234 \
  --set frontend.image.tag=abc1234 \
  --set migrate.image.tag=abc1234 \
  --set apiService.env.s3BucketName=bookgate-prod \
  --set ingress.host=bookgate.example.com
```

Expected rendered resources:

- `Job` — `bookgate-migrate-{revision}` (pre-install/pre-upgrade hook)
- `Deployment` — api-service, chat-service, frontend
- `Service` — api-service, chat-service, frontend (ClusterIP)
- `Ingress` — ALB with three path rules
