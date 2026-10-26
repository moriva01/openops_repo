$ErrorActionPreference = 'Stop'
$taskRoot = Split-Path -Parent $PSScriptRoot
Push-Location $taskRoot
try {
    docker compose up -d --build
    if ($LASTEXITCODE -ne 0) { throw 'Monitoring stack startup failed' }
    $taskNetworks = docker inspect zetaris-driver-1 --format '{{json .NetworkSettings.Networks}}' | ConvertFrom-Json
    if (-not $taskNetworks.openops_default) {
        docker network connect openops_default zetaris-driver-1
        if ($LASTEXITCODE -ne 0) { throw 'Zetaris datasource network attachment failed' }
    }
    Write-Output 'Monitoring services started; Zetaris driver can reach the application database.'
} finally { Pop-Location }
