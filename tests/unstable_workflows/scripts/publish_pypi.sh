#!/usr/bin/env bash
set -euxo pipefail

echo "Git tag: $GITHUB_REF_NAME"

if [[ "$GITHUB_REF_NAME" == test* ]]; then
    export TWINE_PASSWORD=$TWINE_PASSWORD_TEST
    twine upload --repository-url https://test.pypi.org/legacy/ dist/*
elif [[ "$GITHUB_REF_NAME" == release* ]]; then
    export TWINE_PASSWORD=$TWINE_PASSWORD_RELEASE
    twine upload dist/*
else
    echo "Tag does not match test* or release*, skipping PyPI upload."
fi
