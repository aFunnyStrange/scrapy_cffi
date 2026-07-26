#!/usr/bin/env sh
set -eu

infra_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
topology="single"
project_name="${SCRAPY_CFFI_INFRA_PROJECT:-}"

while [ "$#" -gt 0 ]; do
    case "$1" in
        --topology)
            [ "$#" -ge 2 ] || { echo "--topology requires a value" >&2; exit 2; }
            topology="$2"
            shift 2
            ;;
        --project-name)
            [ "$#" -ge 2 ] || { echo "--project-name requires a value" >&2; exit 2; }
            project_name="$2"
            shift 2
            ;;
        --)
            shift
            break
            ;;
        *)
            break
            ;;
    esac
done

case "$topology" in
    single) compose_file="$infra_dir/docker-compose.yml" ;;
    redis-sentinel|redis-cluster|rabbitmq-cluster|kafka-cluster)
        compose_file="$infra_dir/$topology/docker-compose.yml"
        ;;
    *) echo "Unsupported topology: $topology" >&2; exit 2 ;;
esac

if [ ! -f "$compose_file" ]; then
    echo "Topology '$topology' was not generated. Run: scrapy-cffi infra generate" >&2
    exit 1
fi
if [ -z "$project_name" ]; then
    project_config="$(dirname -- "$infra_dir")/scrapy_cffi.toml"
    project_prefix="scrapy_cffi"
    if [ -f "$project_config" ]; then
        configured_prefix=$(awk -F= '/^[[:space:]]*infra_project_name[[:space:]]*=/ { value=$2; gsub(/^[[:space:]"]+|[[:space:]"]+$/, "", value); print value; exit }' "$project_config")
        [ -z "$configured_prefix" ] || project_prefix="$configured_prefix"
    fi
    project_prefix=$(printf '%s' "$project_prefix" | tr '[:upper:]' '[:lower:]' | tr -c 'a-z0-9_-' '_')
    project_name="${project_prefix}_$(printf '%s' "$topology" | tr '-' '_')"
fi

env_file="$infra_dir/.env"
if ! command -v docker >/dev/null 2>&1; then
    echo "Docker CLI was not found. Install Docker with the Compose plugin first." >&2
    exit 1
fi
docker compose version >/dev/null

if [ ! -f "$env_file" ]; then
    cp "$infra_dir/.env.example" "$env_file"
    echo "Created $env_file from .env.example"
fi

docker compose \
    --project-name "$project_name" \
    --env-file "$env_file" \
    --file "$compose_file" \
    up --detach --wait "$@"

echo "Development topology '$topology' is ready (project: $project_name)."
