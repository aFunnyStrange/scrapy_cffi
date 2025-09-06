#!/usr/bin/env bash
set -euxo pipefail

version="${GITHUB_REF_NAME#release-}"

if [[ "$GITHUB_REF_NAME" == release* ]]; then
    echo "Checking CHANGELOG.md for version $version"
    if ! grep -q "## \[$version\]" CHANGELOG.md; then
        echo "❌ ERROR: CHANGELOG.md missing $version"
        exit 1
    fi
else
    echo "Skipping changelog check (not a release tag)"
fi
