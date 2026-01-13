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
          org_clone_token: ${{ secrets.SOFTWELL_CI_BUILD_TOKEN }}
          github_token: ${{ secrets.GITHUB_TOKEN }}
```

Replace:
- `your-project-name` with your Docker image name
- `your-instance-name` with your genropy instance name

## Parameters

### Required Inputs

- `image_name` - Name of the Docker image to build
- `instance_name` - Instance name for genropy operations
- `org_clone_token` - GitHub token with access to private repositories
- `github_token` - GitHub token for container registry authentication (use `${{ secrets.GITHUB_TOKEN }}`)

### Optional Inputs

- `registry` - Container registry URL (default: `ghcr.io`)
- `python_version` - Python version to use (default: `3.11`)

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
          registry: ghcr.io
          python_version: '3.12'
          org_clone_token: ${{ secrets.SOFTWELL_CI_BUILD_TOKEN }}
          github_token: ${{ secrets.GITHUB_TOKEN }}
```

## Requirements

Your repository needs:
- A valid genropy configuration for the instance
- The `SOFTWELL_CI_BUILD_TOKEN` secret configured in repository settings
- Proper permissions for GitHub Actions to push to the container registry

## Versioning

You can reference specific versions of the action:
- `@main` - Latest version (recommended for testing)
- `@v1.0.0` - Specific tagged version (recommended for production)
- `@abc1234` - Specific commit hash
