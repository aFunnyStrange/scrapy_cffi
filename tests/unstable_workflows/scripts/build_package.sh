#!/usr/bin/env bash
set -euxo pipefail

# -------------------------------
# 升级 pip + 安装 build 和 twine
# -------------------------------
python -m pip install --upgrade pip build twine

# -------------------------------
# 清理 Python 缓存
# -------------------------------
find . -type d -name '__pycache__' -exec rm -rf {} +
find . -type f -name '*.py[co]' -delete

# -------------------------------
# 清理 dist 目录
# -------------------------------
rm -rf dist/*
python -m build

# -------------------------------
# 打包参数
# -------------------------------
project="scrapy_cffi"
version="${GITHUB_REF_NAME#release-}"
temp_dir="package_temp"
tar_temp_dir="package_temp_tar"
output_dir="package_out"

# -------------------------------
# 清理临时目录和输出目录
# -------------------------------
rm -rf "$temp_dir" "$tar_temp_dir" "$output_dir"
mkdir -p "$temp_dir" "$tar_temp_dir" "$output_dir"

# -------------------------------
# 复制项目文件到临时目录
# -------------------------------
cp -r scrapy_cffi docs LICENSE README.md "$temp_dir/"

# -------------------------------
# 当前工作目录
# -------------------------------
BASE_DIR="$(pwd)"

# -------------------------------
# 生成压缩包绝对路径
# -------------------------------
ZIP_FILE="$BASE_DIR/$output_dir/${project}-${version}.zip"
TAR_FILE="$BASE_DIR/$output_dir/${project}-${version}.tar.gz"

# -------------------------------
# zip 压缩
# -------------------------------
pushd "$temp_dir"
zip -r -q "$ZIP_FILE" . -x "*.git*" "*__pycache__*" "*.pytest_cache*" "*.egg-info*" "dist/*"
popd

# -------------------------------
# tar 压缩（干净临时目录）
# -------------------------------
# 复制需要打包的文件到 tar 临时目录
cp -r "$temp_dir"/scrapy_cffi "$tar_temp_dir/"
cp -r "$temp_dir"/docs "$tar_temp_dir/"
cp "$temp_dir"/LICENSE "$tar_temp_dir/"
cp "$temp_dir"/README.md "$tar_temp_dir/"

# 生成 tar.gz
tar -C "$tar_temp_dir" \
    --exclude-vcs \
    --exclude="__pycache__" \
    --exclude="*.egg-info" \
    -czf "$TAR_FILE" .

# -------------------------------
# 清理临时目录
# -------------------------------
rm -rf "$temp_dir" "$tar_temp_dir"

echo "Package build complete: $ZIP_FILE and $TAR_FILE"
