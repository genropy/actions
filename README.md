# Genropy Github Actions

This repository contains Github actions related to Genropy projects.

Maintainer: Christopher R. Gabriel <cgabriel@softwell.it>

## Usage

### In Your Repository

Create a workflow file (e.g., `.github/workflows/docker-build.yml`) in your repository:

```yaml
name: Build and Push Docker Image

on: [push]

jobs:
  build-and-push:
    runs-on: ubuntu-latest
    permissions:
      contents: read
      packages: write

    steps:
      - uses: genropy/actions@main
        with:
          image_name: your-project-name
          instance_name: your-instance-name
          registry_token: ${{ secrets.REGISTRY_TOKEN }}
          github_clone_token: ${{ secrets.SOFTWELL_CI_BUILD_TOKEN }}
```

Replace:
- `your-project-name` with your Docker image name
- `your-instance-name` with your genropy instance name

The image is published as `<registry>/<repository owner>/<image_name>:<tag>`.

## Parameters

### Required Inputs

- `image_name` - Name of the Docker image to build
- `instance_name` - Instance name for genropy operations
- `registry_token` - Token used to log in to the container registry (the login user is `github.actor`)

### Optional Inputs

- `registry` - Container registry URL used to reference the image (default: `hub.genro.com`)
- `push_registry` - Registry endpoint used for login/push, e.g. an in-cluster service (default: `forgejo.forgejo.svc.cluster.local:3000`). Pass an empty string to push directly to `registry`. Deployers are always notified with the `registry` address.
- `python_version` - Python version to use (default: `3.11`)
- `genropy_branch` - Branch (or tag/commit) of [genropy](https://github.com/genropy/genropy) to install (default: `master`)
- `subfolder` - Repository subfolder containing the projects (default: empty)
- `github_clone_token` - Token for cloning private repositories from github.com (default: empty)
- `genro_clone_token` - Token for cloning private repositories from hub.genro.com (default: empty)
- `image_tag` - Override the computed image tag (default: empty, see below)
- `deployer_urls` - Comma-separated deployer URLs to notify after a successful build; if empty, no notification is sent
- `deployer_token` - Token sent to the deployers for authentication
- `compliance_check` - Run the compliance check before building (default: `true`)
- `compliance_fail_on` - Lowest finding level that fails the build: `HIGH`, `MEDIUM` or `NONE` for report only (default: `MEDIUM`)

### Compliance Check

Before installing genropy and building, the action runs `compliance/compliance.py`
on the checked-out repository. It statically looks for code that can break with
the newer genropy (custom login, client writes to the rootenv, tinyMCE, unset
`currentEnv` keys, ...) and prints each finding with file and line.
The build stops if there are findings at or above `compliance_fail_on`.
You can also run it locally:

```bash
python3 compliance/compliance.py /path/to/project [--min LOW] [--fail-on MEDIUM] [--json]
```

### Image Tag

Unless `image_tag` is set, the tag is computed from the branch that triggered the workflow:
- `main`, `master` and `develop` produce `latest`
- any other branch uses the branch name, with `/` replaced by `-` (e.g. `feature/foo` becomes `feature-foo`)

## Example with All Options

```yaml
name: Build and Push Docker Image

on:
  push:
    branches:
      - main
      - develop

jobs:
  build-and-push:
    runs-on: ubuntu-latest
    permissions:
      contents: read
      packages: write

    steps:
      - uses: genropy/actions@main
        with:
          image_name: my-application
          instance_name: my-app-instance
          registry: hub.genro.com
          push_registry: forgejo.forgejo.svc.cluster.local:3000
          python_version: '3.12'
          genropy_branch: develop
          subfolder: /projects
          image_tag: ''
          registry_token: ${{ secrets.REGISTRY_TOKEN }}
          github_clone_token: ${{ secrets.SOFTWELL_CI_BUILD_TOKEN }}
          genro_clone_token: ${{ secrets.GENRO_CLONE_TOKEN }}
          deployer_urls: ${{ secrets.GENROPY_DEPLOYER_URLS }}
          deployer_token: ${{ secrets.GENROPY_DEPLOYER_TOKEN }}
```

## Notify Genropy Deployers (standalone)

The deployer notification is also available as a standalone action, so other
workflows (e.g. ones building non-genropy images) can notify deployers without
using the full build action. The main action calls it automatically.

```yaml
    steps:
      - uses: genropy/actions/notify@main
        with:
          image: hub.genro.com/my-org/my-application:latest
          deployer_urls: ${{ secrets.GENROPY_DEPLOYER_URLS }}
          deployer_token: ${{ secrets.GENROPY_DEPLOYER_TOKEN }}
```

Inputs:

- `image` (required) - Full image reference sent to the deployers
- `deployer_urls` - Comma-separated deployer URLs; if empty, the step is skipped
- `deployer_token` - Token sent to the deployers for authentication

Each deployer receives a `POST` with JSON body `{"token": "...", "image": "..."}`.

## Compliance Check (standalone)

The compliance check is also available as a standalone action, e.g. to run it on
pull requests without building. The main action runs it automatically before the build.

```yaml
    steps:
      - uses: actions/checkout@v4
      - uses: genropy/actions/compliance@main
        with:
          fail_on: MEDIUM
```

Inputs:

- `path` - Project directory to check (default: the workspace, i.e. the checked-out repository)
- `fail_on` - Lowest finding level that fails the step: `HIGH`, `MEDIUM` or `NONE` for report only (default: `MEDIUM`)
- `min_level` - Lowest finding level shown in the report: `HIGH`, `MEDIUM`, `LOW` or `INFO` (default: `LOW`)

It needs `python3` 3.9 or newer, which GitHub-hosted Ubuntu runners already have.

## Requirements

Your repository needs:
- A valid genropy configuration for the instance
- A registry token secret (e.g. `REGISTRY_TOKEN`) able to push to the container registry
- Clone token secrets (e.g. `SOFTWELL_CI_BUILD_TOKEN`, `GENRO_CLONE_TOKEN`) if the project depends on private repositories

## Versioning

You can reference specific versions of the action:
- `@main` - Latest version (recommended for testing)
- `@v1.0.0` - Specific tagged version (recommended for production)
- `@abc1234` - Specific commit hash
