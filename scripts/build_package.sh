#!/usr/bin/env bash
set -euxo pipefail

python -m pip install --upgrade pip build twine

find . -type d -name '__pycache__' -exec rm -rf {} +
find . -type f -name '*.py[co]' -delete
rm -rf dist/*

python -m build

project="scrapy_cffi"
version="${GITHUB_REF_NAME#release-}"
temp_dir="package_temp"

rm -rf "$temp_dir"
mkdir -p "$temp_dir"

cp -r scrapy_cffi docs LICENSE README.md "$temp_dir/"

pushd "$temp_dir"
tar -czf "../${project}-${version}.tar.gz" --exclude-vcs --exclude="__pycache__" --exclude="*.egg-info" --exclude="dist" .
zip -r "../${project}-${version}.zip" . -x "*.git*" "*__pycache__*" "*.pytest_cache*" "*.egg-info*" "dist/*"

popd

rm -rf "$temp_dir"

echo "Package build complete: ${project}-${version}.zip and ${project}-${version}.tar.gz"
