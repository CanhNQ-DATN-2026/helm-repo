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
        ├── external-secret.yaml        # ESO ExternalSecret → creates bookgate-secret
        ├── api-service-deployment.yaml
        ├── api-service-service.yaml
        ├── chat-service-deployment.yaml
        ├── chat-service-service.yaml
        ├── frontend-deployment.yaml
        ├── frontend-service.yaml
        └── ingress.yaml                # ALB Ingress
```

---

## Secret contract

### What Terraform creates

Terraform creates two Secrets Manager secrets:

| SM Secret | Who creates it | Contents |
|---|---|---|
| `bookgate/dev/app-secrets` | Terraform (shell only, values filled by operator) | `DATABASE_URL`, `SECRET_KEY`, `ADMIN_PASSWORD`, `OPENAI_API_KEY` |
| `rds!db-bookgate-dev-postgres` | AWS RDS (auto-managed) | `username`, `password` |

The chart only consumes `bookgate/dev/app-secrets`.
The RDS-managed secret is used to **construct** `DATABASE_URL` — see below.

### How DATABASE_URL is sourced

`DATABASE_URL` does not exist pre-built anywhere. The operator must construct
and populate it once after `terraform apply`:

```bash
# 1. Get the RDS endpoint from Terraform
DB_HOST=$(terraform output -raw rds_endpoint)   # returns host:port
# rds_endpoint includes :5432, so strip the port for the URL
DB_ADDRESS=$(echo $DB_HOST | cut -d: -f1)

# 2. Get the RDS master password from the RDS-managed SM secret
DB_PASS=$(aws secretsmanager get-secret-value \
  --secret-id $(terraform output -raw db_credentials_secret_arn) \
  --query SecretString --output text | jq -r .password)

# 3. Populate app-secrets with all four required keys
aws secretsmanager put-secret-value \
  --secret-id bookgate/dev/app-secrets \
  --secret-string "$(jq -n \
    --arg db  "postgresql://bookgate_admin:${DB_PASS}@${DB_ADDRESS}:5432/bookgate" \
    --arg sk  "CHANGE_ME_32_char_random_string" \
    --arg ap  "CHANGE_ME_admin_password" \
    --arg oai "sk-..." \
    '{DATABASE_URL:$db, SECRET_KEY:$sk, ADMIN_PASSWORD:$ap, OPENAI_API_KEY:$oai}')"
```

This is a **one-time setup step** after Terraform provisions the cluster.
On upgrades the secret already exists and ESO keeps it in sync.

### What ESO creates

The chart deploys an `ExternalSecret` that tells ESO to read
`bookgate/dev/app-secrets` and create `bookgate-secret` in the `bookgate`
namespace with these keys:

| K8s Secret key | SM property | Used by |
|---|---|---|
| `DATABASE_URL` | `DATABASE_URL` | api-service, migrate job |
| `SECRET_KEY` | `SECRET_KEY` | api-service, chat-service, migrate job |
| `ADMIN_PASSWORD` | `ADMIN_PASSWORD` | api-service, migrate job |
| `OPENAI_API_KEY` | `OPENAI_API_KEY` | chat-service |

---

## Cluster-level prerequisites (done once, not by this chart)

### 1. Install ESO

```bash
helm repo add external-secrets https://charts.external-secrets.io
helm install eso external-secrets/external-secrets \
  --namespace external-secrets --create-namespace
```

### 2. Create ClusterSecretStore

ESO needs its own ServiceAccount with IRSA permission to read SM.
The `ClusterSecretStore` name must match `externalSecrets.clusterSecretStoreName`
in `values.yaml` (default: `aws-secretsmanager`).

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

```bash
kubectl apply -f cluster-secret-store.yaml
```

---

## Required values.yaml overrides before deploy

| Key | Description | Source |
|---|---|---|
| `ecr.registry` | ECR registry URL | Terraform output `ecr_registry_url` (use frontend or backend URL prefix) |
| `apiService.image.tag` | App image tag | App repo CI (commit SHA) |
| `chatService.image.tag` | App image tag | App repo CI |
| `frontend.image.tag` | App image tag | App repo CI |
| `apiService.env.s3BucketName` | S3 bucket name | Terraform output `s3_bucket_name` |
| `ingress.host` | Public hostname | e.g. `bookgate.example.com` |
| `externalSecrets.remoteSecretName` | SM secret name | `bookgate/dev/app-secrets` (dev) or `bookgate/prod/app-secrets` (prod) |

---

## Operational sequence

### First install

```
1. terraform apply
   └─ creates: EKS, RDS, S3, ECR, bookgate/dev/app-secrets (shell)

2. Populate app-secrets in SM  ← ONE-TIME MANUAL STEP
   └─ construct DATABASE_URL from rds_endpoint + rds_master_password
   └─ set SECRET_KEY, ADMIN_PASSWORD, OPENAI_API_KEY

3. Install ESO + create ClusterSecretStore  ← ONCE PER CLUSTER

4. helm install bookgate ./bookgate --namespace bookgate --create-namespace ...
   └─ creates: ExternalSecret, Deployments, Services, Ingress

5. Wait for ESO to sync
   └─ kubectl get externalsecret -n bookgate bookgate-secret -w
   └─ wait for READY = True

6. Run database migration  ← EXPLICIT STEP
   └─ see "Running migrations" section below

7. Verify app pods are Running
   └─ kubectl get pods -n bookgate
```

### Upgrade (new image tag)

```
1. Update image tags in values.yaml, commit, push
2. helm upgrade bookgate ./bookgate --namespace bookgate ...
   └─ ExternalSecret already exists, bookgate-secret already exists
   └─ Deployments roll out new image
3. If schema changed: run migration explicitly (step 6 above)
```

---

## Running migrations

Migration is an **explicit operational step**, not a Helm hook.
Run it after confirming `bookgate-secret` is synced and before (or after)
rolling out a new Deployment — depending on whether the migration is
forwards-compatible.

```bash
# Verify secret is synced first
kubectl get secret bookgate-secret -n bookgate

# Run migration
IMAGE="<ECR_REGISTRY>/bookgate/api-service:<IMAGE_TAG>"

kubectl apply -f - <<EOF
apiVersion: batch/v1
kind: Job
metadata:
  name: bookgate-migrate-$(date +%Y%m%d%H%M%S)
  namespace: bookgate
spec:
  ttlSecondsAfterFinished: 3600
  backoffLimit: 2
  template:
    spec:
      restartPolicy: Never
      containers:
        - name: migrate
          image: $IMAGE
          command: ["bash", "scripts/migrate.sh"]
          envFrom:
            - secretRef:
                name: bookgate-secret
          env:
            - name: ADMIN_EMAIL
              value: "admin@bookgate.com"
            - name: ADMIN_FULL_NAME
              value: "System Admin"
            - name: S3_BUCKET_NAME
              value: "<S3_BUCKET_NAME>"
            - name: AWS_DEFAULT_REGION
              value: "ap-southeast-1"
EOF

# Tail logs to confirm success
kubectl logs -n bookgate -l job-name=bookgate-migrate-... -f
```

Migration does: Alembic `upgrade head` + bootstrap admin account (idempotent).
No sample/demo data is created.

---

## Image tag update flow

```yaml
# values.yaml — update all four tags to the new commit SHA
apiService:
  image:
    tag: "abc1234"
chatService:
  image:
    tag: "abc1234"
frontend:
  image:
    tag: "abc1234"
```

Commit and push → Helm repo CI runs `helm upgrade`.

---

## Ingress

| Path | Backend |
|---|---|
| `/api/v1/chat` | chat-service (SSE — listed first) |
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
  --set apiService.env.s3BucketName=bookgate-prod \
  --set ingress.host=bookgate.example.com
```

Expected rendered resources:

- `ExternalSecret` — ESO creates `bookgate-secret` from SM
- `Deployment` — api-service, chat-service, frontend
- `Service` — api-service, chat-service, frontend (ClusterIP)
- `Ingress` — ALB with three path rules
