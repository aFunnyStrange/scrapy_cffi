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

# 清理临时目录
rm -rf "$temp_dir"
mkdir -p "$temp_dir"

# 复制需要打包的文件到临时目录
cp -r scrapy_cffi docs LICENSE README.md "$temp_dir/"

# 进入临时目录
pushd "$temp_dir"

# 检测系统类型
OS_TYPE="$(uname | tr '[:upper:]' '[:lower:]')"
if [[ "$OS_TYPE" == msys* ]] || [[ "$OS_TYPE" == mingw* ]]; then
    # Windows Git Bash / MSYS
    ZIP_CMD="zip -r -q"
    TAR_CMD="tar -czf"
else
    # Linux / macOS
    ZIP_CMD="zip -r -q"
    TAR_CMD="tar -czf"
fi

# 压缩包输出到临时目录外，避免被打包进去
$ZIP_CMD "../${project}-${version}.zip" . -x "*.git*" "*__pycache__*" "*.pytest_cache*" "*.egg-info*" "dist/*"
$TAR_CMD "../${project}-${version}.tar.gz" --exclude-vcs --exclude="__pycache__" --exclude="*.egg-info" --exclude="dist" .

# 返回上级目录
popd

# 清理临时目录
rm -rf "$temp_dir"

echo "Package build complete: ${project}-${version}.zip and ${project}-${version}.tar.gz"
