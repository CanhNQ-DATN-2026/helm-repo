# Final GitOps Runbook

Mục tiêu:
- repo `helm-charts` là nguồn cấu hình duy nhất cho môi trường dev
- Argo CD sync app `bookgate` từ repo này
- app lên qua `http://bookgate.canhnq.online`

## 1. Kiểm tra cluster prerequisites

```bash
kubectl get pods -n kube-system -l app.kubernetes.io/name=aws-load-balancer-controller
kubectl get pods -n external-secrets
kubectl get clustersecretstore aws-secretsmanager
kubectl get pods -n argocd
```

## 2. Kiểm tra secret trên AWS

```bash
aws secretsmanager get-secret-value \
  --region us-east-1 \
  --secret-id bookgate/dev/app-secrets \
  --query SecretString \
  --output text | jq
```

## 3. Kiểm tra image tag trong repo Helm

```bash
sed -n '1,220p' /Users/nguyenquangcanh/atlantic/helm-charts/bookgate/values.yaml
```

Tag hiện tại phải tồn tại trong cả 3 repo ECR:

```bash
aws ecr describe-images --region us-east-1 --repository-name bookgate/api-service --image-ids imageTag=4028443
aws ecr describe-images --region us-east-1 --repository-name bookgate/chat-service --image-ids imageTag=4028443
aws ecr describe-images --region us-east-1 --repository-name bookgate/frontend --image-ids imageTag=4028443
```

## 4. Apply Argo CD application

```bash
kubectl apply -f /Users/nguyenquangcanh/atlantic/helm-charts/argocd/bookgate-dev.yaml
```

## 5. Sync và chờ app healthy

```bash
argocd app sync bookgate-dev --insecure
argocd app wait bookgate-dev --health --sync --insecure
```

Hoặc kiểm tra bằng kubectl:

```bash
kubectl get application bookgate-dev -n argocd
kubectl get pods -n bookgate
kubectl get ingress -n bookgate -o wide
```

## 6. Verify app

```bash
kubectl get externalsecret -n bookgate
kubectl get secret bookgate-secret -n bookgate
kubectl logs -n bookgate deploy/bookgate-external-dns --tail=100
curl -I http://bookgate.canhnq.online
curl http://bookgate.canhnq.online/health
```

Kỳ vọng:
- `bookgate-secret` sync thành công
- `api`, `chat`, `frontend`, `bookgate-external-dns` chạy ổn
- ingress có ALB hostname
- `bookgate.canhnq.online` trả `200 OK`

## 7. Release mới

Khi app repo build image tag mới:

1. sửa `bookgate/values.yaml`
2. commit
3. push repo `helm-charts`
4. Argo CD tự sync

Ví dụ commit:

```bash
cd /Users/nguyenquangcanh/atlantic/helm-charts
git add bookgate/values.yaml
git commit -m "Bump Bookgate dev image tag"
git push origin main
```
