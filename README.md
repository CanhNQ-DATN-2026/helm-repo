# Bookgate Helm Repo

Helm chart repo for deploying Bookgate workloads to EKS.

This repo deploys only:
- `api-service`
- `chat-service`
- `frontend`

This repo does not provision AWS infrastructure. Infrastructure is owned by the Terraform repo.

## What This Repo Assumes

Before installing this chart, these AWS resources must already exist:
- VPC, subnets, EKS cluster
- RDS PostgreSQL
- S3 bucket for book files
- ECR repositories and pushed images
- IAM roles for:
  - backend IRSA
  - AWS Load Balancer Controller
  - External Secrets Operator
- AWS Secrets Manager secret `bookgate/dev/app-secrets`

## Required Secret Contract

AWS Secrets Manager secret:
- `bookgate/dev/app-secrets`

Expected keys:
- `DATABASE_URL`
- `SECRET_KEY`
- `ADMIN_PASSWORD`
- `OPENAI_API_KEY`

The chart creates an `ExternalSecret` that syncs this secret into Kubernetes as:
- `bookgate-secret`

## IRSA Usage

This chart creates:
- ServiceAccount `backend-sa`

`api-service` uses that ServiceAccount and expects:
- `apiService.serviceAccount.roleArn` to be set

Expected S3 permissions on the backend IRSA role:
- `s3:PutObject`
- `s3:GetObject`
- `s3:DeleteObject`
- `s3:ListBucket`

## Argo CD Note

If you move to Argo CD later, you do not need the old GitLab/Helm deployer RBAC for this repo anymore.

That old RBAC was only for a CI job calling `helm upgrade` directly into the cluster.
With Argo CD, sync permissions belong to Argo CD itself, not to this repo.

## Bootstrap From Scratch

### 1. Create infrastructure

In the Terraform repo:

```bash
cd /Users/nguyenquangcanh/atlantic/terraform
terraform init
terraform apply
```

Export the values needed later:

```bash
cd /Users/nguyenquangcanh/atlantic/terraform

export AWS_REGION=us-east-1
export EKS_CLUSTER_NAME=$(terraform output -raw eks_cluster_name)
export VPC_ID=$(terraform output -raw vpc_id)
export LBC_ROLE_ARN=$(terraform output -raw lbc_role_arn)
export BACKEND_ROLE_ARN=$(terraform output -raw backend_role_arn)
export ECR_REGISTRY=$(terraform output -raw ecr_registry_url)
export S3_BUCKET_NAME=$(terraform output -raw s3_bucket_name)
export RDS_ENDPOINT=$(terraform output -raw rds_endpoint)
export DB_SECRET_ARN=$(terraform output -raw db_credentials_secret_arn)
export APP_SECRET_ARN=$(terraform output -raw app_secrets_secret_arn)
export OIDC_PROVIDER_ARN=$(terraform output -raw eks_oidc_provider_arn)
export OIDC_ISSUER_HOST=$(terraform output -raw eks_cluster_oidc_issuer | sed 's#^https://##')
```

### 2. Get cluster admin access

The cluster is created by CI role bootstrap, so after recreate you must grant your IAM user access again.

Run the GitHub Actions workflow in `terraform-infra`:
- `EKS Grant Admin Access`

Then locally:

```bash
aws eks update-kubeconfig --region "$AWS_REGION" --name "$EKS_CLUSTER_NAME"
kubectl get nodes
```

### 3. Rebuild and push app images if ECR was destroyed

If ECR repositories were deleted during destroy, push images again from the app repo:

```bash
cd /Users/nguyenquangcanh/atlantic/bookgate
export IMAGE_TAG=$(git rev-parse --short HEAD)

aws ecr get-login-password --region "$AWS_REGION" | \
  docker login --username AWS --password-stdin "$ECR_REGISTRY"

docker buildx build --platform linux/amd64 \
  -t "$ECR_REGISTRY/bookgate/api-service:$IMAGE_TAG" \
  --push ./api-service

docker buildx build --platform linux/amd64 \
  -t "$ECR_REGISTRY/bookgate/chat-service:$IMAGE_TAG" \
  --push ./chat-service

docker buildx build --platform linux/amd64 \
  -t "$ECR_REGISTRY/bookgate/frontend:$IMAGE_TAG" \
  --push ./frontend
```

### 4. Populate AWS Secrets Manager app secret

Get the real RDS password from the RDS-managed secret and build `DATABASE_URL`:

```bash
export DB_PASSWORD=$(aws secretsmanager get-secret-value \
  --secret-id "$DB_SECRET_ARN" \
  --query SecretString \
  --output text | jq -r '.password')

export DATABASE_URL="postgresql://bookgate_admin:${DB_PASSWORD}@${RDS_ENDPOINT}/bookgate"
export SECRET_KEY=$(openssl rand -hex 32)
export ADMIN_PASSWORD='your-admin-password'
export OPENAI_API_KEY='sk-...'

aws secretsmanager put-secret-value \
  --secret-id "$APP_SECRET_ARN" \
  --secret-string "$(jq -nc \
    --arg DATABASE_URL "$DATABASE_URL" \
    --arg SECRET_KEY "$SECRET_KEY" \
    --arg ADMIN_PASSWORD "$ADMIN_PASSWORD" \
    --arg OPENAI_API_KEY "$OPENAI_API_KEY" \
    '{DATABASE_URL:$DATABASE_URL,SECRET_KEY:$SECRET_KEY,ADMIN_PASSWORD:$ADMIN_PASSWORD,OPENAI_API_KEY:$OPENAI_API_KEY}')"
```

### 5. Install AWS Load Balancer Controller

```bash
helm repo add eks https://aws.github.io/eks-charts
helm repo update

helm upgrade --install aws-load-balancer-controller eks/aws-load-balancer-controller \
  -n kube-system \
  --version 3.2.1 \
  --set clusterName="$EKS_CLUSTER_NAME" \
  --set region="$AWS_REGION" \
  --set vpcId="$VPC_ID" \
  --set serviceAccount.create=true \
  --set serviceAccount.name=aws-load-balancer-controller \
  --set-string serviceAccount.annotations."eks\.amazonaws\.com/role-arn"="$LBC_ROLE_ARN"
```

### 6. Update External Secrets trust policy for the new EKS OIDC issuer

After recreating EKS, the OIDC provider changes. Update the trust policy of the existing ESO IAM role:

```bash
cat > /tmp/eso-trust-policy.json <<EOF
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Principal": {
        "Federated": "${OIDC_PROVIDER_ARN}"
      },
      "Action": "sts:AssumeRoleWithWebIdentity",
      "Condition": {
        "StringEquals": {
          "${OIDC_ISSUER_HOST}:aud": "sts.amazonaws.com",
          "${OIDC_ISSUER_HOST}:sub": "system:serviceaccount:external-secrets:external-secrets"
        }
      }
    }
  ]
}
EOF

aws iam update-assume-role-policy \
  --role-name bookgate-eks-external-secrets-role \
  --policy-document file:///tmp/eso-trust-policy.json
```

### 7. Install External Secrets Operator

```bash
helm repo add external-secrets https://charts.external-secrets.io
helm repo update

helm upgrade --install external-secrets external-secrets/external-secrets \
  -n external-secrets \
  --create-namespace \
  --version 2.3.0 \
  --set installCRDs=true \
  --set serviceAccount.create=true \
  --set serviceAccount.name=external-secrets \
  --set-string serviceAccount.annotations."eks\.amazonaws\.com/role-arn"="arn:aws:iam::392423995152:role/bookgate-eks-external-secrets-role"
```

### 8. Create ClusterSecretStore

```bash
cat <<EOF | kubectl apply -f -
apiVersion: external-secrets.io/v1
kind: ClusterSecretStore
metadata:
  name: aws-secretsmanager
spec:
  provider:
    aws:
      service: SecretsManager
      region: us-east-1
EOF
```

### 9. Install the app

In this repo:

```bash
cd /Users/nguyenquangcanh/atlantic/helm-charts

helm upgrade --install bookgate ./bookgate \
  --namespace bookgate \
  --create-namespace \
  --set ecr.registry="$ECR_REGISTRY" \
  --set apiService.image.tag="$IMAGE_TAG" \
  --set chatService.image.tag="$IMAGE_TAG" \
  --set frontend.image.tag="$IMAGE_TAG" \
  --set apiService.serviceAccount.roleArn="$BACKEND_ROLE_ARN" \
  --set apiService.env.awsDefaultRegion="$AWS_REGION" \
  --set apiService.env.s3BucketName="$S3_BUCKET_NAME" \
  --set externalSecrets.remoteSecretName="bookgate/dev/app-secrets" \
  --set ingress.host=""
```

### 10. Wait for secret sync

```bash
kubectl get externalsecret -n bookgate
kubectl get secret bookgate-secret -n bookgate
```

### 11. Run DB migration and seed

Migration is still manual in the current design:

```bash
kubectl exec -n bookgate deploy/bookgate-api -- sh -lc 'cd /app && alembic upgrade head && python -m scripts.seed'
```

### 12. Verify

```bash
kubectl get pods -n bookgate
kubectl get ingress -n bookgate
```

Get the ALB DNS name:

```bash
kubectl get ingress -n bookgate
```

## Validation Commands

```bash
helm lint bookgate/
```

```bash
helm template bookgate bookgate/ \
  --set ecr.registry=123456789012.dkr.ecr.us-east-1.amazonaws.com \
  --set apiService.image.tag=abc1234 \
  --set chatService.image.tag=abc1234 \
  --set frontend.image.tag=abc1234 \
  --set apiService.serviceAccount.roleArn=arn:aws:iam::123456789012:role/bookgate-eks-backend-role \
  --set apiService.env.s3BucketName=bookgate-dev-books-123456789012 \
  --set apiService.env.awsDefaultRegion=us-east-1 \
  --set externalSecrets.remoteSecretName=bookgate/dev/app-secrets \
  --set ingress.host=""
```
