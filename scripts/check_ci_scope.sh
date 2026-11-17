#!/usr/bin/env bash
# Enforce the M6 CI boundary: build and test, never provision AWS or push images.
set -euo pipefail

patterns='aws-actions/|amazon-ecr-login|configure-aws-credentials|cdk (bootstrap|deploy|destroy|diff)|aws ecr|aws cloudformation|docker push'
# Include action inputs and BuildKit exporters. Dynamic push inputs cannot be
# proven safe, so reject expressions while allowing the literal push: false.
patterns+='|["'"'"']?push["'"'"']?[[:space:]]*:[[:space:]]*(["'"'"']?true|.*\$\{\{)|type[[:space:]]*=[[:space:]]*registry|push[[:space:]]*=[[:space:]]*true'

if grep -RniE "$patterns" .github/workflows; then
  echo "ERROR: workflow contains an AWS/registry deployment step." >&2
  echo "M6 CI is limited to local image builds and container E2E tests." >&2
  exit 1
fi

echo "CI scope check passed: no AWS provisioning, ECR push, or deployment steps."
