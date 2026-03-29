# Bookgate Helm Charts — CLAUDE.md

## Repo overview
Repo này chứa Helm chart production để deploy Bookgate lên EKS.
Chart chính nằm ở `bookgate/`.

Deployable workloads:
- `api-service`
- `chat-service`
- `frontend`

Không có Postgres, MinIO, gateway, hay local-only manifests trong chart này.

## Chart structure
```text
bookgate/
├── Chart.yaml
├── values.yaml
└── templates/
    ├── _helpers.tpl
    ├── serviceaccount.yaml
    ├── api-service-deployment.yaml
    ├── api-service-service.yaml
    ├── chat-service-deployment.yaml
    ├── chat-service-service.yaml
    ├── frontend-deployment.yaml
    ├── frontend-service.yaml
    ├── external-secret.yaml
    └── ingress.yaml
```

## Secret flow
- Chart tạo `ExternalSecret`
- ESO đọc từ AWS Secrets Manager secret `${project}/${environment}/app-secrets`
- ESO tạo K8s Secret `bookgate-secret`
- Pods inject env bằng `secretKeyRef`

Required keys trong `bookgate-secret`:
- `DATABASE_URL`
- `SECRET_KEY`
- `ADMIN_PASSWORD`
- `OPENAI_API_KEY`

`DATABASE_URL` phải được operator populate vào app secret sau `terraform apply`.

## IRSA
- Chart tạo `backend-sa` qua `templates/serviceaccount.yaml`
- `api-service` dùng `serviceAccountName: backend-sa`
- ServiceAccount này phải được annotate với Terraform output `backend_role_arn`
- Quyền role backend chỉ cần S3:
  - `s3:PutObject`
  - `s3:GetObject`
  - `s3:DeleteObject`
  - `s3:ListBucket`

App pods không cần Secrets Manager permission; ESO handle phần đó riêng.

## Values cần override
| Key | Meaning |
|---|---|
| `ecr.registry` | ECR registry prefix |
| `apiService.image.tag` | image tag cho api-service |
| `chatService.image.tag` | image tag cho chat-service |
| `frontend.image.tag` | image tag cho frontend |
| `apiService.serviceAccount.roleArn` | Terraform output `backend_role_arn` |
| `apiService.env.s3BucketName` | Terraform output `s3_bucket_name` |
| `ingress.host` | public host |
| `ingress.certificateArn` | ACM certificate ARN nếu dùng HTTPS |
| `externalSecrets.remoteSecretName` | ví dụ `bookgate/dev/app-secrets` hoặc `bookgate/prod/app-secrets` |

## Deploy flow

### First install
1. `terraform apply`
2. Populate AWS Secrets Manager app secret
3. Cài ESO + `ClusterSecretStore` ở cluster level
4. `helm upgrade --install`
5. Chờ `ExternalSecret` sync thành `bookgate-secret`
6. Chạy migration explicit ngoài Helm hook

### Upgrade
1. Update image tags
2. `helm upgrade`
3. Nếu schema đổi, chạy migration explicit

Migration không còn là Helm hook.

## CI/CD
- Pipeline file: `.gitlab-ci.yml`
- `lint`: `helm lint bookgate/`
- `deploy`: assume role qua OIDC, `aws eks update-kubeconfig`, rồi `helm upgrade --install`
- Trigger mode hiện tại:
  - push vào helm repo: manual gate
  - pipeline trigger: auto deploy

Nếu workflow thực tế muốn manual hoàn toàn, cần sửa `.gitlab-ci.yml`.

## CI variables
| Variable | Meaning |
|---|---|
| `AWS_ROLE_ARN` | IAM role cho Helm CI |
| `AWS_REGION` | AWS region |
| `ECR_REGISTRY` | ECR registry prefix |
| `EKS_CLUSTER_NAME` | cluster name |
| `BACKEND_ROLE_ARN` | Terraform output `backend_role_arn` |
| `CERTIFICATE_ARN` | ACM cert ARN |

Khuyến nghị thêm biến riêng cho:
- `REMOTE_SECRET_NAME`
- `INGRESS_HOST`

## EKS auth
- Helm CI role cần `eks:DescribeCluster`
- Role đó còn phải được map vào EKS auth
- Không bắt buộc dùng `system:masters`; ưu tiên RBAC tối thiểu cho namespace app
- Có thể dùng `aws-auth` hoặc EKS access entry tùy cluster auth mode thực tế
