param(
    [string[]]$Model
)

$ErrorActionPreference = "Stop"

$defaultModels = @(
    "gemma4:e2b",
    "gemma4:e4b",
    "gemma4:26b",
    "qwen2.5:3b"
)

$models = if ($Model -and $Model.Count -gt 0) {
    $Model
} else {
    $defaultModels
}

$successfulModels = @()
$failedModels = @()

foreach ($model in $models) {
    Write-Host ""
    Write-Host ">>> Pulling $model via Ollama ..." -ForegroundColor Yellow

    docker exec goi-ollama ollama pull $model
    if ($LASTEXITCODE -eq 0) {
        $successfulModels += $model
        Write-Host "OK: $model pulled." -ForegroundColor Green
    } else {
        $failedModels += $model
        Write-Host "FAILED: $model" -ForegroundColor Red
    }
}

Write-Host ""
Write-Host "Bootstrap complete." -ForegroundColor Cyan
Write-Host "Successful: $($successfulModels.Count)"
Write-Host "Failed: $($failedModels.Count)"

if ($failedModels.Count -gt 0) {
    Write-Host "Failed models:" -ForegroundColor Red
    $failedModels | ForEach-Object { Write-Host " - $_" -ForegroundColor Red }
    exit 1
}
