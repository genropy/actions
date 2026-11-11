# Genropy Github Actions

This repository contains Github actions related to Genropy projects.

The main action builds the image with
[genro-toolchain](https://github.com/genropy/genro-toolchain) (`gnr-dockerize`),
a standalone replacement for `gnr app dockerize`: Genropy is not installed on
the runner.

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
- `toolchain_ref` - Branch, tag or commit of [genro-toolchain](https://github.com/genropy/genro-toolchain) to use (default: `main`)
- `base_image` - Base image for the build, e.g. `ghcr.io/genropy/genropy:develop` (default: empty, i.e. `ghcr.io/genropy/genropy:latest`)
- `subfolder` - Repository subfolder containing the projects (default: empty)
- `github_clone_token` - Token for cloning private repositories from github.com (default: empty)
- `genro_clone_token` - Token for cloning private repositories from hub.genro.com (default: empty)
- `image_tag` - Override the computed image tag (default: empty, see below)
- `deployer_urls` - Comma-separated deployer URLs to notify after a successful build; if empty, no notification is sent
- `deployer_token` - Token sent to the deployers for authentication
- `compliance_check` - Run the compliance check before building (default: `true`)
- `compliance_fail_on` - Lowest finding level that fails the build: `HIGH`, `MEDIUM` or `NONE` for report only (default: `MEDIUM`)

### Compliance Check

Before building, the action runs `compliance/compliance.py`
on the checked-out repository. It statically looks for code that can break with
the newer genropy (custom login, client writes to the rootenv, tinyMCE, unset
`currentEnv` keys, ...) and prints each finding with file and line.
The build stops if there are findings at or above `compliance_fail_on`.
You can also run it locally:

```bash
python3 compliance/compliance.py /path/to/project [--min LOW] [--fail-on MEDIUM] [--json]
```

A static check cannot tell a deliberate choice from a mistake. When a finding is
intended (e.g. an override of `login_createNewUser` that must not depend on the
`new_user` preference), mark it with `# compliance: ok <RULE> <reason>`, either at
the end of the reported line or alone on the line immediately above it:

```python
def login_createNewUser(self, **kwargs):  # compliance: ok LOGIN-NEWUSER registration ignores the new_user preference
    ...

# compliance: ok ENV-KEY always set by the instance's own onAuthenticating
sede_id = self.db.currentEnv['sede_id']
```

The marker drops only the findings of the rule it names, and only when a reason
follows the rule. For a function the reported line is the `def` line (its
decorators sit above it), so use the trailing form there. An `ENV-KEY` finding
is marked when any read of its key carries the marker. In `.js` files `//`
works as well as `#`. Marked findings never fail the step: they are listed after
the others with their reason, and under `marked` with `--json`, whose output is
`{"<project>": {"findings": [...], "marked": [...]}}`.

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
          toolchain_ref: main
          base_image: ghcr.io/genropy/genropy:develop
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

### How the image is built

- The instance is looked up by name in the checked-out repository
  (`instances/<name>` or `*/instances/<name>`), or under `subfolder` when set.
- The instance repository is taken from the checked-out commit (no extra clone).
- The other repositories come from the instance `config/build.json`, which
  **must be committed**: genro-toolchain cannot generate it. Without it the image
  contains only the instance repository. Generate it once with
  `gnr app dockerize --build-gen` and commit it.
- Debian packages listed in `config/apt-dependencies.txt` are installed in the image.

## Requirements

Your repository needs:
- A valid genropy configuration for the instance, including a committed `config/build.json`
- A registry token secret (e.g. `REGISTRY_TOKEN`) able to push to the container registry
- Clone token secrets (e.g. `SOFTWELL_CI_BUILD_TOKEN`, `GENRO_CLONE_TOKEN`) if the project depends on private repositories

## Versioning

You can reference specific versions of the action:
- `@main` - Latest version (recommended for testing)
- `@v1.0.0` - Specific tagged version (recommended for production)
- `@abc1234` - Specific commit hash
