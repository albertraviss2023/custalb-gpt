param(
    [ValidateSet("kokoro", "xtts", "all")]
    [string]$Provider = "kokoro"
)

$ErrorActionPreference = "Stop"

$composeFile = "infra/docker-compose.yml"

function Wait-Healthy {
    param(
        [Parameter(Mandatory = $true)][string]$ContainerName,
        [int]$MaxWaitSeconds = 180
    )

    $deadline = (Get-Date).AddSeconds($MaxWaitSeconds)
    while ((Get-Date) -lt $deadline) {
        $status = docker inspect $ContainerName --format "{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}" 2>$null
        if ($status -eq "healthy" -or $status -eq "running") {
            Write-Host "OK: $ContainerName is $status." -ForegroundColor Green
            return
        }
        Start-Sleep -Seconds 3
    }
    throw "Timed out waiting for $ContainerName to become ready."
}

if ($Provider -eq "kokoro" -or $Provider -eq "all") {
    Write-Host ">>> Pulling Kokoro image..." -ForegroundColor Yellow
    docker pull ghcr.io/remsky/kokoro-fastapi-cpu:latest | Out-Null
    Write-Host ">>> Starting Kokoro service..." -ForegroundColor Yellow
    docker compose -f $composeFile up -d kokoro-tts | Out-Null
    Wait-Healthy -ContainerName "goi-kokoro-tts"
}

if ($Provider -eq "xtts" -or $Provider -eq "all") {
    Write-Host ">>> Pulling XTTS image..." -ForegroundColor Yellow
    docker pull ghcr.io/coqui-ai/xtts-streaming-server:latest | Out-Null
    Write-Host ">>> Starting XTTS service..." -ForegroundColor Yellow
    docker compose -f $composeFile --profile tts-xtts up -d xtts-tts | Out-Null
    Wait-Healthy -ContainerName "goi-xtts-tts"
}

Write-Host ""
Write-Host "TTS bootstrap complete." -ForegroundColor Cyan
