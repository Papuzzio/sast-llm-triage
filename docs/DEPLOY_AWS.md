# Deploying TriageGPT to AWS (EKS)

Terraform builds the AWS side. Kubernetes runs the app. GitHub Actions scans every change and ships `main`.

```
GitHub Actions ──OIDC──► IAM role (main branch only)
   │  checkov · pip-audit · trivy · SBOM · cosign
   ▼
 ECR (immutable tags, scan on push, KMS) ──► EKS (private nodes, 2 AZs)
                                               └─ ns triagegpt (PSA restricted, default-deny NetworkPolicy)
                                                    └─ Deployment (non-root, read-only FS, no SA token)
                                                          ▲ env from Secret
 Secrets Manager (KMS) ──Pod Identity──► External Secrets Operator
```

## Cost. Read this first.

About **$0.23 an hour, or roughly $5.50 a day**, while it's up:

| Item | Rate |
| --- | --- |
| EKS control plane | $0.10/h |
| 2 × t3.medium nodes | about $0.08/h |
| NAT gateway | $0.045/h |
| KMS, Secrets Manager, logs | small |

Left running, that's about $165 a month. **Run `terraform destroy` when you're done** (step 7).

The app is never exposed to the internet. Every triage run spends your Anthropic/Gemini credits, so you reach it only through `kubectl port-forward`.

## Prerequisites (on your Mac)

```bash
brew install awscli terraform kubectl helm
# Docker Desktop running; `aws configure` done with an admin-capable user or SSO profile
aws sts get-caller-identity
```

## 1. Infrastructure

```bash
cd infra/terraform
cp terraform.tfvars.example terraform.tfvars
# set admin_cidrs to your IP:  curl -s https://checkip.amazonaws.com
terraform init
terraform plan -out tf.plan      # read it: ~60 resources, nothing public except the API endpoint (your IP only)
terraform apply tf.plan          # ~15 minutes, mostly EKS
git add .terraform.lock.hcl      # commit the provider lock file
```

If apply fails with "EntityAlreadyExists" on the GitHub OIDC provider, set `create_github_oidc_provider = false` in `terraform.tfvars` and run apply again.

## 2. API keys into Secrets Manager (they never touch Terraform state)

```bash
aws secretsmanager put-secret-value --region us-east-1 \
  --secret-id triagegpt/api-keys \
  --secret-string '{"ANTHROPIC_API_KEY":"sk-ant-...","GEMINI_API_KEY":"..."}'
```

## 3. First deploy

```bash
cd ../..
./scripts/deploy_eks.sh
kubectl -n triagegpt port-forward svc/triagegpt 8501:80
# open http://localhost:8501 and upload data/semgrep_juiceshop.json
```

## 4. Turn on CI/CD

```bash
terraform -chdir=infra/terraform output -raw github_ci_role_arn
```

In GitHub, go to **Settings → Secrets and variables → Actions → Variables** and add `AWS_CI_ROLE_ARN` with that value. From then on, every push to `main`:
- scans the image
- pushes it by commit SHA
- signs it with cosign
- rolls it out

## 5. Prove the controls work (screenshot these; they're your evidence)

```bash
# Pod Security Admission rejects a privileged pod
kubectl -n triagegpt run bad --image=busybox --privileged -- sleep 1        # expect: forbidden

# The app's identity can't touch the Kubernetes API (no token mounted)
kubectl -n triagegpt exec deploy/triagegpt -- ls /var/run/secrets/kubernetes.io 2>&1   # expect: No such file

# Read-only root filesystem
kubectl -n triagegpt exec deploy/triagegpt -- touch /app/x                  # expect: Read-only file system

# The CI role is limited to one namespace
kubectl auth can-i create deployments -n default \
  --as=arn:aws:sts::<acct>:assumed-role/triagegpt-github-ci/x                # expect: no

# NetworkPolicy blocks the instance metadata service
kubectl -n triagegpt exec deploy/triagegpt -- python -c \
  "import urllib.request;urllib.request.urlopen('http://169.254.169.254',timeout=3)"   # expect: timeout

# Signature check on the deployed image (after the first CI run)
cosign verify <ecr-url>@sha256:<digest> \
  --certificate-identity-regexp 'https://github.com/Papuzzio/sast-llm-triage/.*' \
  --certificate-oidc-issuer https://token.actions.githubusercontent.com
```

## 6. Security decisions (and why)

| Decision | Why |
| --- | --- |
| GitHub OIDC; trust pinned to `repo:Papuzzio/sast-llm-triage:ref:refs/heads/main` | No long-lived AWS keys in GitHub. PRs and forks can't assume the role. |
| CI gets EKS `EditPolicy` scoped to the `triagegpt` namespace only | A compromised pipeline can't touch the rest of the cluster. |
| Secrets Manager + External Secrets Operator + Pod Identity | Keys stay out of git, Terraform state and CI. One role, one secret. |
| KMS envelope encryption for Kubernetes Secrets | etcd holds ciphertext only. |
| ECR immutable tags; deploy by digest | What was scanned and signed is exactly what runs. |
| Private nodes, IMDSv2 with hop limit 1, egress policy blocks 169.254/16 | Pods can't steal the node role through instance metadata. |
| PSA `restricted`, non-root UID 10001, read-only FS, all capabilities dropped, no SA token | Container escape and API abuse have little to work with. |
| Default-deny NetworkPolicy; egress only DNS + 443 | Limits blast radius and data exfiltration paths. |
| ClusterIP only | No unauthenticated public endpoint spending your API credits. |

Accepted scanner findings are skipped inline with a reason (`# checkov:skip=` / `checkov.io/skip`).

Trivy has one accepted finding: the RSA private key in `data/juice-shop-src/lib/insecurity.ts`. It's OWASP Juice Shop's intentionally planted, publicly published key, and part of the test corpus the app triages. It's skipped for that one file only (see `ci.yml`).

## 7. Tear down

```bash
cd infra/terraform
terraform destroy
```

KMS keys go into a 7-day pending-deletion window. That's normal.
