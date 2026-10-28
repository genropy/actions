#!/usr/bin/env bash
# Notify one or more Genropy deployers that a new image is available.
# Env: IMAGE (full image reference), DEPLOYER_URLS (comma-separated), DEPLOYER_TOKEN
set -euo pipefail

if [ -z "${DEPLOYER_URLS:-}" ]; then
  echo "GENROPY_DEPLOYER_URLS not set, skipping deployer notification"
  exit 0
fi
if [ -z "${IMAGE:-}" ]; then
  echo "IMAGE not set, cannot notify deployers" >&2
  exit 1
fi

IFS=',' read -ra URLS <<< "$DEPLOYER_URLS"
for URL in "${URLS[@]}"; do
  URL="$(echo "$URL" | xargs)"
  [ -z "$URL" ] && continue
  echo "Notifying deployer at $URL with image $IMAGE"
  curl -fsSL -X POST "$URL" \
    -H "Content-Type: application/json" \
    --data "$(jq -n --arg token "${DEPLOYER_TOKEN:-}" --arg image "$IMAGE" '{token: $token, image: $image}')"
done
