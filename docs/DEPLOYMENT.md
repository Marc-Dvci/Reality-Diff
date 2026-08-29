# Google Cloud deployment

Target project:

- Project ID: `reality-diff`
- Project number: `284853036406`
- Cloud/data region: `us-central1`
- Vertex AI model location: `global`

Resource creation can incur Google Cloud charges. Review the Terraform plan before applying it.

## Current deployment

The production service was first deployed (private) on 20 August 2026 and made public for judging on 27 August 2026:

- URL: `https://reality-diff-284853036406.us-central1.run.app`
- Ready revision: `reality-diff-v010-20260820-probes`
- Image: `v0.1.0-20260820`
- Image index digest: `sha256:1f35c1211b79699866954c676cc67cf871137b1c4607aedce181bab452db1a7e`
- Cloud Run: 1 vCPU, 512 MiB, concurrency 8, min 0, max 2, CPU throttling
- Budget: project-scoped €10 monthly alerts at 50%, 80%, 100%, and forecasted 100%

The live evidence and screenshots are in [CLOUD_DEPLOYMENT_EVIDENCE.md](CLOUD_DEPLOYMENT_EVIDENCE.md).

## Prerequisites

- Terraform 1.7+ (validated with 1.15.8)
- Google Cloud CLI authenticated with an account allowed to enable services, create IAM bindings, and provision the listed resources
- Docker authenticated to Artifact Registry

Always pass the explicit project because the workstation's active gcloud project may be different:

```powershell
gcloud auth application-default login
gcloud config set project reality-diff
gcloud auth configure-docker us-central1-docker.pkg.dev
```

## Bootstrap the registry and required APIs

Terraform needs the immutable image to exist before Cloud Run can be created. First apply only the APIs and repository:

```powershell
Set-Location infrastructure
$image = "us-central1-docker.pkg.dev/reality-diff/reality-diff/reality-diff:v0.1.0-20260820"
terraform init
terraform apply `
  -target='google_project_service.required' `
  -target='google_artifact_registry_repository.containers' `
  -var="image=$image"
```

Review the plan and confirm that Terraform resolves project number `284853036406`.

## Build and push once

Artifact Registry has immutable tags enabled, so choose a new tag for every changed image:

```powershell
Set-Location ..
docker build -t $image .
docker push $image
```

## Apply the complete private deployment

```powershell
Set-Location infrastructure
terraform plan -out=reality-diff.tfplan -var="image=$image"
terraform apply reality-diff.tfplan
terraform output service_url
```

The default is private (`public_demo=false`). To expose a sample deployment later, explicitly plan with `-var="public_demo=true"` and review the single-user/privacy boundary in `BUILD_AUDIT.md` first.

## Verify

```powershell
$url = terraform output -raw service_url
gcloud run services proxy reality-diff --project reality-diff --region us-central1 --port 8091
```

In another shell:

```powershell
python ..\scripts\demo-smoke.py http://127.0.0.1:8091
```

Inspect `/health`: production must report `gemini-3.7-flash`, `gemini-3.5-flash-lite`, `gemini-embedding-2`, project `reality-diff`, location `global`, and `live_models: true`.

The current resources were provisioned with `gcloud` while the Terraform files were validated in a credential-free pinned container. This kept the workstation's Application Default Credentials out of a third-party container. Before using Terraform against this already-live project, import the existing resources into a state backend; do not run a fresh apply that attempts to recreate them.

## Rollback and cleanup

- Roll back by applying a previously pushed immutable image tag.
- Firestore has delete protection and an `ABANDON` deletion policy.
- The media bucket has `force_destroy=false` and public-access prevention.
- Terraform does not disable the required APIs on destroy.

Those protections deliberately prevent an accidental infrastructure command from erasing user media or world memory.
