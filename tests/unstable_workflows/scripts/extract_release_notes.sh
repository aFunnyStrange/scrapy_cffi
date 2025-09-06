#!/usr/bin/env bash
set -euxo pipefail

version="${GITHUB_REF_NAME#release-}"

echo "Extracting release notes for version $version"
if [ -f CHANGELOG.md ]; then
    notes=$(awk "/## \\[$version\\]/ {flag=1; next} /^## \\[/ && flag {flag=0} flag" CHANGELOG.md)
fi
if [ -z "$notes" ]; then
    notes="- No changelog entry found for $version"
fi

echo "content<<EOF" >> $GITHUB_OUTPUT
echo "$notes" >> $GITHUB_OUTPUT
echo "EOF" >> $GITHUB_OUTPUT
