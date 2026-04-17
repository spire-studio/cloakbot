#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
SOURCE_IMAGE="$ROOT_DIR/cloakbot_logo.png"
OUTPUT_DIR="$ROOT_DIR/webui/public"

if ! command -v sips >/dev/null 2>&1; then
  echo "sips is required to generate webui icons." >&2
  exit 1
fi

if [[ ! -f "$SOURCE_IMAGE" ]]; then
  echo "Missing source image: $SOURCE_IMAGE" >&2
  exit 1
fi

mkdir -p "$OUTPUT_DIR"
cp "$SOURCE_IMAGE" "$OUTPUT_DIR/cloakbot-logo.png"

sips -z 16 16 "$SOURCE_IMAGE" --out "$OUTPUT_DIR/favicon-16x16.png" >/dev/null
sips -z 32 32 "$SOURCE_IMAGE" --out "$OUTPUT_DIR/favicon-32x32.png" >/dev/null
sips -z 180 180 "$SOURCE_IMAGE" --out "$OUTPUT_DIR/apple-touch-icon.png" >/dev/null
sips -z 192 192 "$SOURCE_IMAGE" --out "$OUTPUT_DIR/android-chrome-192x192.png" >/dev/null
sips -z 512 512 "$SOURCE_IMAGE" --out "$OUTPUT_DIR/android-chrome-512x512.png" >/dev/null
