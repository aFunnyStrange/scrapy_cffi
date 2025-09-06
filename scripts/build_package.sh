#!/usr/bin/env bash
set -euxo pipefail

# 升级 pip + 安装 build 和 twine
python -m pip install --upgrade pip build twine

# 清理缓存
find . -type d -name '__pycache__' -exec rm -rf {} +
find . -type f -name '*.py[co]' -delete
rm -rf dist/*

# 构建 wheel + sdist
python -m build

# 打包参数
project="scrapy_cffi"
version="${GITHUB_REF_NAME#release-}"
temp_dir="package_temp"
output_dir="package_out"

# 清理临时目录和输出目录
rm -rf "$temp_dir" "$output_dir"
mkdir -p "$temp_dir" "$output_dir"

# 复制需要打包的文件到临时目录
cp -r scrapy_cffi docs LICENSE README.md "$temp_dir/"

# 进入临时目录
pushd "$temp_dir"

# 压缩包输出路径
ZIP_FILE="../$output_dir/${project}-${version}.zip"
TAR_FILE="../$output_dir/${project}-${version}.tar.gz"

# zip 打包
zip -r -q "$ZIP_FILE" . -x "*.git*" "*__pycache__*" "*.pytest_cache*" "*.egg-info*" "dist/*"

# tar 打包，-C . 表示切换到当前目录，只打包临时目录内容
tar -czf "$TAR_FILE" --exclude-vcs --exclude="__pycache__" --exclude="*.egg-info" --exclude="dist" -C . .

popd

# 清理临时目录
rm -rf "$temp_dir"

echo "Package build complete: $ZIP_FILE and $TAR_FILE"
