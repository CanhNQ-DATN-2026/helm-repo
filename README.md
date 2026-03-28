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
        ├── external-secret.yaml      # ExternalSecret — ESO syncs bookgate-secret from SM
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

## How secrets work

The chart creates an `ExternalSecret` object. ESO watches it and automatically
syncs `bookgate-secret` from AWS Secrets Manager — no manual `kubectl` needed.

```
Terraform
  └─ creates AWS Secrets Manager secret "bookgate/prod"
        ↓
ESO (running in cluster, has IRSA to read SM)
  └─ reads ExternalSecret CR created by this chart
  └─ fetches values from SM
  └─ creates/updates K8s Secret "bookgate-secret"
        ↓
Deployments / migrate Job
  └─ env vars injected via secretKeyRef
```

### Cluster-level prerequisites (done once, not by this chart)

**1. Install ESO:**
```bash
helm repo add external-secrets https://charts.external-secrets.io
helm install eso external-secrets/external-secrets \
  --namespace external-secrets --create-namespace
```

**2. Create a ClusterSecretStore** pointing to AWS Secrets Manager.
ESO uses its own ServiceAccount with IRSA to call SM:

```yaml
apiVersion: external-secrets.io/v1beta1
kind: ClusterSecretStore
metadata:
  name: aws-secretsmanager
spec:
  provider:
    aws:
      service: SecretsManager
      region: ap-southeast-1
      auth:
        jwt:
          serviceAccountRef:
            name: external-secrets
            namespace: external-secrets
```

The `ClusterSecretStore` name must match `externalSecrets.clusterSecretStoreName`
in `values.yaml` (default: `aws-secretsmanager`).

### What ESO creates

`bookgate-secret` K8s Secret with these keys, pulled from SM secret `bookgate/prod`:

| Key | Description |
|---|---|
| `DATABASE_URL` | Full RDS connection string |
| `SECRET_KEY` | JWT signing key |
| `ADMIN_PASSWORD` | Initial admin password |
| `OPENAI_API_KEY` | OpenAI API key |

The SM secret is created by Terraform with these exact key names.

---

## Required values.yaml overrides

| Key | Description |
|---|---|
| `ecr.registry` | ECR registry URL (Terraform output `ecr_registry_url`) |
| `apiService.image.tag` | Image tag from app repo CI |
| `chatService.image.tag` | Image tag from app repo CI |
| `frontend.image.tag` | Image tag from app repo CI |
| `migrate.image.tag` | Must match `apiService.image.tag` |
| `apiService.env.s3BucketName` | S3 bucket name (Terraform output `s3_bucket_name`) |
| `ingress.host` | Public hostname (e.g. `bookgate.example.com`) |
| `externalSecrets.remoteSecretName` | SM secret name created by Terraform (default: `bookgate/prod`) |

---

## Image tag update flow

After app repo CI pushes new images to ECR, update `values.yaml`:

```yaml
apiService:
  image:
    tag: "abc1234"
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

Commit and push → Helm repo CI runs `helm upgrade`.

---

## Deploy to EKS

```bash
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

| Path | Backend |
|---|---|
| `/api/v1/chat` | chat-service (SSE — listed first, more specific) |
| `/api/v1` | api-service |
| `/` | frontend |

```yaml
ingress:
  host: bookgate.example.com
  scheme: internet-facing
  idleTimeoutSeconds: 300    # must exceed longest SSE stream
  certificateArn: ""         # ACM ARN for HTTPS; empty = HTTP only
  groupName: bookgate
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

- `ExternalSecret` — triggers ESO to create `bookgate-secret` from SM
- `Job` — `bookgate-migrate-{revision}` (pre-install/pre-upgrade hook)
- `Deployment` — api-service, chat-service, frontend
- `Service` — api-service, chat-service, frontend (ClusterIP)
- `Ingress` — ALB with three path rules
