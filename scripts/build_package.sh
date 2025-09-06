#!/usr/bin/env bash
set -euxo pipefail

# -----------------------------
# 1. 安装依赖
# -----------------------------
python -m pip install --upgrade pip build twine

# -----------------------------
# 2. 清理缓存和旧构建
# -----------------------------
find . -type d -name '__pycache__' -exec rm -rf {} +
find . -type f -name '*.py[co]' -delete
rm -rf dist/*

# -----------------------------
# 3. 构建 wheel + sdist
# -----------------------------
python -m build

# -----------------------------
# 4. 打包参数
# -----------------------------
project="scrapy_cffi"
version="${GITHUB_REF_NAME#release-}"  # CI 下使用 tag
temp_dir="package_temp"
output_dir="package_out"

# 清理临时目录和输出目录
rm -rf "$temp_dir" "$output_dir"
mkdir -p "$temp_dir" "$output_dir"

# -----------------------------
# 5. 复制源码和资源文件到临时目录
# -----------------------------
cp -r scrapy_cffi docs LICENSE README.md "$temp_dir/"

# -----------------------------
# 6. 压缩包输出路径（确保在临时目录外）
# -----------------------------
ZIP_FILE="$output_dir/${project}-${version}.zip"
TAR_FILE="$output_dir/${project}-${version}.tar.gz"

# -----------------------------
# 7. 压缩打包
# -----------------------------
# zip 打包
zip -r -q "$ZIP_FILE" "$temp_dir"/* \
    -x "*.git*" "*__pycache__*" "*.pytest_cache*" "*.egg-info*" "dist/*"

# tar 打包
tar -C "$temp_dir" \
    --exclude-vcs \
    --exclude="__pycache__" \
    --exclude="*.egg-info" \
    --exclude="dist" \
    -czf "$TAR_FILE" .

# -----------------------------
# 8. 清理临时目录
# -----------------------------
rm -rf "$temp_dir"

echo "✅ Package build complete: $ZIP_FILE and $TAR_FILE"
