---
name: github-actions-node-runtime-upgrade
description: Fix GitHub Actions Node runtime deprecation warnings separately from the app's own Node version, then validate both the workflow and Docker image.
triggers:
  - GitHub Actions warns that Node.js 20 actions are deprecated
  - CI passes or fails with annotations about actions being forced to Node 24
  - Need to modernise both workflow actions and the app Docker image
---

# GitHub Actions Node Runtime Upgrade

Use this when a repo's CI shows warnings like:
- "Node.js 20 actions are deprecated"
- "Actions will be forced to run with Node.js 24"

## Core distinction

There are two separate Node runtimes:

1. GitHub Actions runtime
- Used internally by actions like `actions/checkout` and `docker/build-push-action`
- Controlled by the action versions and optionally `FORCE_JAVASCRIPT_ACTIONS_TO_NODE24`
- Not affected by the app Dockerfile base image

2. Application/runtime Node
- Used by the app build and container runtime
- Controlled by the Dockerfile base image such as `node:20-alpine`
- Does not remove GitHub's action-runtime warning by itself

Do not treat these as the same issue.

## Procedure

### 1. Inspect current workflow and Dockerfile
Use file tools to read:
- `.github/workflows/*.yml`
- `Dockerfile`
- `package.json`

Confirm:
- which actions are used in the workflow
- current Docker image tag
- whether the app already builds locally on a newer Node

### 2. Check latest action releases
Use `gh api` instead of guessing:

- `gh api repos/actions/checkout/releases/latest --jq '.tag_name, .published_at'`
- `gh api repos/docker/build-push-action/releases/latest --jq '.tag_name, .published_at'`
- `gh api repos/docker/setup-buildx-action/releases/latest --jq '.tag_name, .published_at'`
- `gh api repos/docker/login-action/releases/latest --jq '.tag_name, .published_at'`

### 3. Update the workflow
Typical upgrade path seen working:
- `actions/checkout@v6`
- `docker/setup-buildx-action@v4`
- `docker/login-action@v4`
- `docker/build-push-action@v7`

Also add at workflow `env:` level:
- `FORCE_JAVASCRIPT_ACTIONS_TO_NODE24: true`

This helps validate the workflow against the new runtime now, instead of waiting for GitHub's forced switch.

### 4. Update the app Dockerfile separately
If the user wants the app on a newer Node too, change all stages consistently:
- `FROM node:20-alpine` -> `FROM node:24-alpine`

Check all stages, not just the first one:
- deps
- builder
- runner

### 5. Validate before push
Run both validations locally:

- app build:
  - `npm run build`
- container build:
  - `docker build -t <repo>:test .`

If only `npm run build` passes, that is not enough. The workflow may still fail inside Docker.

### 6. Commit only the intended files
If the repo has unrelated local changes, stage only:
- `.github/workflows/build-push.yml`
- `Dockerfile`

Then commit with a narrow message, for example:
- `ci: update actions and move app image to Node 24`

### 7. Push and verify CI
Use `gh run list` and `gh run watch <run_id> --exit-status`.

After the run finishes, inspect the run summary again and confirm:
- workflow succeeded
- previous Node 20 deprecation annotation is gone

## Pitfalls

- Updating the Dockerfile alone will not remove GitHub Actions runtime warnings.
- Updating actions alone will not upgrade the app container's Node version.
- Do not bundle unrelated local changes into the CI fix commit.
- `gh release view vX` may fail for some repos; `gh api repos/<owner>/<repo>/releases/latest` is more reliable.

## Verification checklist

- [ ] Workflow actions upgraded
- [ ] `FORCE_JAVASCRIPT_ACTIONS_TO_NODE24: true` added
- [ ] Dockerfile stages all moved to the intended Node version
- [ ] `npm run build` passes locally
- [ ] `docker build` passes locally
- [ ] GitHub Actions run passes after push
- [ ] No Node 20 deprecation annotation remains in the new run
