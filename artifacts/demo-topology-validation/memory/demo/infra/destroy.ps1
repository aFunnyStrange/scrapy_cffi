param(
    [ValidateSet("single", "redis-sentinel", "redis-cluster", "rabbitmq-cluster", "kafka-cluster")]
    [string]$Topology = "single",
    [string]$ProjectName = ""
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
if (-not (Test-Path -LiteralPath $envFile)) {
    Copy-Item -LiteralPath $exampleEnvFile -Destination $envFile
}

Write-Warning "Destroying containers and data volumes owned by Compose project '$ProjectName'."
& docker compose --project-name $ProjectName --env-file $envFile --file $composeFile down --volumes --remove-orphans
if ($LASTEXITCODE -ne 0) {
    throw "Development topology destroy failed."
}
Write-Host "Development topology '$Topology' was destroyed."
