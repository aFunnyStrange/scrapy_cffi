#!/usr/bin/env bash
set -euxo pipefail

for file in dist/* scrapy_cffi-*.zip scrapy_cffi-*.tar.gz; do
    sha256sum "$file" > "$file.sha256"
done
