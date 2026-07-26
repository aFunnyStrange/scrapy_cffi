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
    throw "Topology '$Topology' was not generated. Run: scrapy-cffi infra generate"
}
if (-not $ProjectName) {
    $projectConfig = Join-Path (Split-Path -Parent $infraDir) "scrapy_cffi.toml"
    $projectPrefix = "scrapy_cffi"
    if (Test-Path -LiteralPath $projectConfig) {
        $configMatch = Select-String -LiteralPath $projectConfig `
            -Pattern '^\s*infra_project_name\s*=\s*[''"]([^''"]+)[''"]' |
            Select-Object -First 1
        if ($configMatch) {
            $projectPrefix = $configMatch.Matches[0].Groups[1].Value
        }
    }
    $projectPrefix = $projectPrefix.ToLowerInvariant() -replace '[^a-z0-9_-]', '_'
    $ProjectName = "${projectPrefix}_$($Topology.Replace('-', '_'))"
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
