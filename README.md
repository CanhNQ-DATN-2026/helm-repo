# Bookgate Helm Repo

Repo này là source of truth cho deploy Bookgate bằng Argo CD.

Hiện tại repo chứa:
- chart ứng dụng `bookgate/`
- values base `bookgate/values.yaml`
- values live `bookgate/values.yaml`
- manifest Argo CD `argocd/bookgate-dev.yaml`

URL mục tiêu hiện tại:
- app: `http://bookgate.canhnq.online`
- Argo CD: `http://argocd.canhnq.online`

## Mô hình GitOps

Luồng chuẩn:
1. Terraform tạo hạ tầng AWS và các IAM role/Route 53 cần thiết.
2. Cluster-level addons được cài trước:
   - `aws-load-balancer-controller`
   - `external-secrets`
   - `ClusterSecretStore/aws-secretsmanager`
   - Argo CD
3. Repo này giữ toàn bộ desired state của app.
4. Argo CD đọc `argocd/bookgate-dev.yaml`, render chart `bookgate/` với `values.yaml`, rồi sync vào namespace `bookgate`.

Điểm quan trọng:
- Không còn phụ thuộc vào `helm upgrade --set ...` để giữ cấu hình môi trường.
- Mọi giá trị runtime của môi trường dev phải nằm trong Git, trừ secret value thật nằm trong AWS Secrets Manager.

## Prerequisites

Những thứ phải có trước khi apply Argo CD Application:
- EKS cluster đã chạy được
- Route 53 hosted zone `canhnq.online`
- AWS Load Balancer Controller hoạt động
- External Secrets Operator hoạt động
- `ClusterSecretStore` tên `aws-secretsmanager`
- Secret trên AWS Secrets Manager:
  - `bookgate/dev/app-secrets`
- ECR đã có image tag tương ứng
- Argo CD đã được cài trong cluster

## Repo Structure

```text
argocd/bookgate-dev.yaml
bookgate/Chart.yaml
bookgate/values.yaml
bookgate/values.yaml
bookgate/templates/
```

## Values Strategy

`bookgate/values.yaml`
- base values dùng chung
- không chứa cấu hình môi trường thật
- không nên sửa theo từng release

`bookgate/values.yaml`
- desired state thật của môi trường dev hiện tại
- đang chứa:
  - ECR registry
  - image tag
  - backend IRSA role ARN
  - external-dns IRSA role ARN
  - S3 bucket
  - domain `bookgate.canhnq.online`
  - secret path `bookgate/dev/app-secrets`

## Current Dev Config

Dev hiện đang được chuẩn hóa theo:
- release name: `bookgate`
- namespace: `bookgate`
- ingress host: `bookgate.canhnq.online`
- external-dns: `enabled`
- external secret source: `bookgate/dev/app-secrets`

## Argo CD Application

Manifest sẵn có:
- [argocd/bookgate-dev.yaml](/Users/nguyenquangcanh/atlantic/helm-charts/argocd/bookgate-dev.yaml)

Manifest này:
- trỏ tới repo `https://github.com/CanhNQ-DATN-2026/helm-repo.git`
- dùng chart path `bookgate`
- dùng values file `values.yaml`
- đặt release name là `bookgate`
- bật:
  - `automated.prune=true`
  - `automated.selfHeal=true`

Apply:

```bash
cd /Users/nguyenquangcanh/atlantic/helm-charts
kubectl apply -f argocd/bookgate-dev.yaml
```

Kiểm tra:

```bash
kubectl get applications -n argocd
kubectl describe application bookgate-dev -n argocd
```

Nếu muốn sync tay lần đầu:

```bash
argocd app sync bookgate-dev --insecure
argocd app wait bookgate-dev --health --sync --insecure
```

## First Bootstrap

### 1. Kiểm tra addons trong cluster

```bash
kubectl get pods -n kube-system -l app.kubernetes.io/name=aws-load-balancer-controller
kubectl get pods -n external-secrets
kubectl get clustersecretstore aws-secretsmanager
kubectl get pods -n argocd
```

### 2. Kiểm tra secret trên AWS

```bash
aws secretsmanager get-secret-value \
  --region us-east-1 \
  --secret-id bookgate/dev/app-secrets \
  --query SecretString \
  --output text | jq
```

Bắt buộc phải có:
- `DATABASE_URL`
- `SECRET_KEY`
- `ADMIN_PASSWORD`
- `OPENAI_API_KEY`

### 3. Kiểm tra image tag có tồn tại trong ECR

Ví dụ với tag hiện tại `4028443`:

```bash
aws ecr describe-images --region us-east-1 --repository-name bookgate/api-service --image-ids imageTag=4028443
aws ecr describe-images --region us-east-1 --repository-name bookgate/chat-service --image-ids imageTag=4028443
aws ecr describe-images --region us-east-1 --repository-name bookgate/frontend --image-ids imageTag=4028443
```

### 4. Apply Argo CD application

```bash
kubectl apply -f /Users/nguyenquangcanh/atlantic/helm-charts/argocd/bookgate-dev.yaml
```

### 5. Verify sau sync

```bash
kubectl get pods -n bookgate
kubectl get externalsecret -n bookgate
kubectl get secret -n bookgate bookgate-secret
kubectl get ingress -n bookgate -o wide
kubectl logs -n bookgate deploy/bookgate-external-dns --tail=100
curl -I http://bookgate.canhnq.online
curl http://bookgate.canhnq.online/health
```

Kỳ vọng:
- `bookgate-secret` đã sync
- `api`, `chat`, `frontend`, `bookgate-external-dns` đều chạy
- ingress có ALB hostname
- `bookgate.canhnq.online` trả `200 OK`

## Release Flow

Khi app repo build ra image tag mới:

1. sửa tag trong [bookgate/values.yaml](/Users/nguyenquangcanh/atlantic/helm-charts/bookgate/values.yaml)
2. commit
3. push lên remote
4. Argo CD tự sync hoặc sync tay

Ví dụ:

```yaml
apiService:
  image:
    tag: "NEW_TAG"

chatService:
  image:
    tag: "NEW_TAG"

frontend:
  image:
    tag: "NEW_TAG"
```

## Secret Rotation Flow

Khi đổi secret ở AWS Secrets Manager:

1. update `bookgate/dev/app-secrets`
2. chờ ESO sync theo `refreshInterval: 1h`
3. hoặc ép sync:

```bash
kubectl annotate externalsecret -n bookgate bookgate-secret force-sync=$(date +%s) --overwrite
```

4. restart pod để app nhận env mới:

```bash
kubectl rollout restart deployment/bookgate-api -n bookgate
kubectl rollout restart deployment/bookgate-chat -n bookgate
```

## GitOps-specific Notes

Chart đã được chỉnh để phù hợp hơn với Argo CD:
- `ExternalSecret` không còn dùng Helm hook
- `ExternalSecret` có `sync-wave: -1`
- workloads có `sync-wave: 1`
- ingress có `sync-wave: 2`
- helper image template render được cả tag số

Điều này giúp Argo CD apply theo thứ tự ổn định hơn và tránh lệ thuộc vào `helm install/upgrade` semantics.

## Manual Fallback

Nếu cần render để debug:

```bash
cd /Users/nguyenquangcanh/atlantic/helm-charts
helm lint ./bookgate -f ./bookgate/values.yaml
helm template bookgate ./bookgate -n bookgate -f ./bookgate/values.yaml
```

Nếu cần deploy tay tạm thời:

```bash
helm upgrade --install bookgate ./bookgate \
  --namespace bookgate \
  --create-namespace \
  -f ./bookgate/values.yaml \
  --wait \
  --timeout 10m
```

## Troubleshooting

`Application OutOfSync`
- xem diff trong Argo CD trước, vì app đang dùng auto-sync và prune

`ExternalSecret` không sync
- kiểm tra `external-secrets` pod
- kiểm tra `ClusterSecretStore/aws-secretsmanager`
- kiểm tra IAM role của ESO còn trust đúng OIDC hiện tại

`external-dns` không tạo record
- kiểm tra `externalDns.enabled=true` trong `values.yaml`
- kiểm tra role ARN trong `values.yaml`
- kiểm tra log `deploy/bookgate-external-dns`

`InvalidImageName`
- chart đã xử lý tag số bằng `%v`
- nếu image không pull được thì vấn đề nằm ở tag chưa có trong ECR

`Chat` lỗi dù pod chạy
- `OPENAI_API_KEY` trong `bookgate/dev/app-secrets` sai hoặc hết hạn
