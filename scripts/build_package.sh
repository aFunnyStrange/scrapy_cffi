#!/usr/bin/env bash
set -euxo pipefail

# 安装 build 工具
python -m pip install --upgrade pip build twine

# 清理缓存
find . -type d -name '__pycache__' -exec rm -rf {} +
find . -type f -name '*.py[co]' -delete
rm -rf dist/*

# 构建 wheel + sdist
python -m build

# 打包干净目录
project="scrapy_cffi"
version="${GITHUB_REF_NAME#release-}"
temp_dir="package_temp"

# 创建临时目录
rm -rf "$temp_dir"
mkdir -p "$temp_dir"

# 复制需要打包的文件
cp -r scrapy_cffi docs LICENSE README.md "$temp_dir/"

# 生成压缩包
pushd "$temp_dir"
zip -r "../${project}-${version}.zip" . -x "*.git*" "*__pycache__*" "*.pytest_cache*" "*.egg-info*" "dist/*"
tar -czf "../${project}-${version}.tar.gz" . --exclude-vcs --exclude="__pycache__" --exclude="*.egg-info" --exclude="dist"
popd

# 清理临时目录
rm -rf "$temp_dir"

echo "Package build complete: ${project}-${version}.zip and ${project}-${version}.tar.gz"
