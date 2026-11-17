#!/usr/bin/env bash
# Wait for the containerised UI before starting browser tests.
set -euo pipefail

url="${1:-http://127.0.0.1:7860/}"
deadline=$((SECONDS + 180))

until curl --fail --silent --show-error --max-time 5 "$url" >/dev/null 2>&1; do
  if ((SECONDS >= deadline)); then
    echo "Timed out waiting for ${url}" >&2
    exit 1
  fi
  sleep 2
done

echo "UI is ready at ${url}"
