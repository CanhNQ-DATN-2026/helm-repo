# Bookgate Helm Charts — CLAUDE.md

## Repo overview
Helm chart deploy toàn bộ Bookgate stack lên EKS. Chart tại `bookgate/`.
Namespace mặc định: `bookgate`.

## Chart structure
```
bookgate/
├── Chart.yaml
├── values.yaml              # production defaults — chỉnh sửa ở đây
└── templates/
    ├── _helpers.tpl         # bookgate.name, bookgate.image
    ├── serviceaccount.yaml  # backend-sa với IRSA annotation
    ├── api-service-deployment.yaml
    ├── api-service-service.yaml
    ├── chat-service-deployment.yaml
    ├── chat-service-service.yaml
    ├── frontend-deployment.yaml
    ├── frontend-service.yaml
    ├── external-secret.yaml # ESO ExternalSecret → bookgate-secret
    └── ingress.yaml         # AWS Load Balancer Controller
```

## Secrets flow
ESO (External Secrets Operator) đọc từ AWS Secrets Manager → tạo K8s Secret `bookgate-secret`.
SM secret path: `bookgate/dev/app-secrets` (dev) hoặc `bookgate/prod/app-secrets` (prod).
Keys trong secret: `DATABASE_URL`, `SECRET_KEY`, `ADMIN_PASSWORD`, `OPENAI_API_KEY`.

**ESO phải sync xong trước khi app pods start.** Nếu pod báo lỗi mount secret → kiểm tra ExternalSecret status trước.

## IRSA
`backend-sa` ServiceAccount được annotate với IAM role ARN.
Role có quyền: `s3:PutObject`, `s3:GetObject`, `s3:DeleteObject`, `s3:ListBucket` trên S3 bucket sách.
Không cần Secrets Manager permission (ESO handle riêng bằng ClusterSecretStore).

## Values cần override khi deploy

```yaml
ecr:
  registry: "392423995152.dkr.ecr.us-east-1.amazonaws.com"  # terraform output ecr_registry_url

apiService:
  image:
    tag: "<commit-sha>"
  serviceAccount:
    roleArn: "<terraform output backend_role_arn>"

chatService:
  image:
    tag: "<commit-sha>"

frontend:
  image:
    tag: "<commit-sha>"

ingress:
  host: "bookgate.example.com"
  certificateArn: "<ACM cert ARN>"

externalSecrets:
  remoteSecretName: "bookgate/dev/app-secrets"  # đổi thành prod khi cần
```

## Helm install command
```bash
helm upgrade --install bookgate ./bookgate \
  --namespace bookgate \
  --create-namespace \
  --set ecr.registry="<ECR_REGISTRY>" \
  --set apiService.image.tag="<IMAGE_TAG>" \
  --set chatService.image.tag="<IMAGE_TAG>" \
  --set frontend.image.tag="<IMAGE_TAG>" \
  --set apiService.serviceAccount.roleArn="<BACKEND_ROLE_ARN>" \
  --set ingress.certificateArn="<CERT_ARN>" \
  --wait --timeout 5m
```

## CI/CD
- Pipeline: `.gitlab-ci.yml` — stages: `lint` → `deploy`
- `lint`: `helm lint bookgate/`
- `deploy`: OIDC → EKS kubeconfig → `helm upgrade --install`
- Khi trigger từ app pipeline: auto deploy
- Khi push trực tiếp vào helm repo: manual gate

## CI variables (GitLab repo settings)
| Variable | Mô tả |
|----------|-------|
| `AWS_ROLE_ARN` | IAM role cho helm CI (cần `eks:DescribeCluster` + EKS access entry) |
| `AWS_REGION` | `us-east-1` |
| `ECR_REGISTRY` | `392423995152.dkr.ecr.us-east-1.amazonaws.com` |
| `EKS_CLUSTER_NAME` | `bookgate-eks` |
| `BACKEND_ROLE_ARN` | terraform output `backend_role_arn` |
| `CERTIFICATE_ARN` | ACM certificate ARN |

## EKS auth
Helm CI role cần được add vào EKS (aws-auth ConfigMap hoặc access entry) với quyền `system:masters`.
Cluster dùng `CONFIG_MAP` mode (mặc định) — dùng `kubectl edit configmap aws-auth -n kube-system`.
