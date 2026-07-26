param(
    [ValidateSet("single", "redis-sentinel", "redis-cluster", "rabbitmq-cluster", "kafka-cluster")]
    [string]$Topology = "single",
    [string]$ProjectName = "",
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$Services = @()
)

$ErrorActionPreference = "Stop"
$infraDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$composeRelativePath = if ($Topology -eq "single") {
    "docker-compose.yml"
} else {
    Join-Path $Topology "docker-compose.yml"
}
$composeFile = Join-Path $infraDir $composeRelativePath
$envFile = Join-Path $infraDir ".env"
$exampleEnvFile = Join-Path $infraDir ".env.example"

if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
    throw "Docker CLI was not found. Install Docker with the Compose plugin first."
}

if (-not (Test-Path -LiteralPath $composeFile)) {
    throw "Topology '$Topology' was not generated. Run: scrapy-cffi geninfra --all"
}

if (-not $ProjectName) {
    $workspaceName = Split-Path -Leaf (Split-Path -Parent $infraDir)
    $workspaceSlug = $workspaceName.ToLowerInvariant() -replace '[^a-z0-9_-]', '_'
    $ProjectName = "scrapy_cffi_${workspaceSlug}_dev_$($Topology.Replace('-', '_'))"
}

docker compose version | Out-Null
if ($LASTEXITCODE -ne 0) {
    throw "The Docker Compose plugin is unavailable."
}

if (-not (Test-Path -LiteralPath $envFile)) {
    Copy-Item -LiteralPath $exampleEnvFile -Destination $envFile
    Write-Host "Created $envFile from .env.example"
}

$composeArgs = @(
    "compose", "--project-name", $ProjectName,
    "--env-file", $envFile, "--file", $composeFile,
    "up", "--detach", "--wait"
) + $Services

& docker @composeArgs
if ($LASTEXITCODE -ne 0) {
    throw "Development infrastructure failed to start."
}

Write-Host "Development topology '$Topology' is ready (project: $ProjectName)."
