function Show-Menu {
    Clear-Host
    Write-Host "===============================================" -ForegroundColor Cyan
    Write-Host "   TurboGPT Personal Assistant Manager" -ForegroundColor Cyan
    Write-Host "===============================================" -ForegroundColor Cyan
    Write-Host "1) Bootstrap Models (Pull via Ollama)"
    Write-Host "2) Start Stack (Docker Compose Up)"
    Write-Host "3) Stop Stack (Docker Compose Down)"
    Write-Host "4) Clean Unused Docker Stuff (Prune)"
    Write-Host "5) Full Reset (Delete ALL Models and Databases)"
    Write-Host "Q) Exit"
    Write-Host "===============================================" -ForegroundColor Cyan
}

function Bootstrap-Models {
    & "$PSScriptRoot\bootstrap-models.ps1"
    if ($LASTEXITCODE -eq 0) {
        Write-Host "`nModel pre-caching complete." -ForegroundColor Green
    } else {
        Write-Host "`nModel pre-caching finished with errors. Check output above." -ForegroundColor Red
    }
    Pause
}

function Start-Stack {
    Write-Host "`n>>> Starting TurboGPT Stack..." -ForegroundColor Yellow
    docker compose -f infra/docker-compose.yml up --build -d
    Write-Host "`nStack started!" -ForegroundColor Green
    Write-Host "UI:  http://localhost:3000"
    Write-Host "API: http://localhost:8001 (Internal 8000)"
    Pause
}

function Stop-Stack {
    Write-Host "`n>>> Stopping Stack..." -ForegroundColor Yellow
    docker compose -f infra/docker-compose.yml down
    Pause
}

function Clean-Docker {
    Write-Host "`n>>> Cleaning unused Docker resources..." -ForegroundColor Yellow
    docker system prune -f
    Write-Host "`nCleanup complete." -ForegroundColor Green
    Pause
}

function Full-Reset {
    $confirm = Read-Host "Are you sure you want to delete ALL models and databases? (y/N)"
    if ($confirm -eq 'y') {
        Write-Host "`n>>> Wiping everything..." -ForegroundColor Red
        docker compose -f infra/docker-compose.yml down -v
        docker volume rm personal-goi_vllm-data personal-goi_api-data
        Write-Host "`nSystem reset complete." -ForegroundColor Green
    }
    Pause
}

while ($true) {
    Show-Menu
    $choice = Read-Host "Select an option"
    switch ($choice) {
        "1" { Bootstrap-Models }
        "2" { Start-Stack }
        "3" { Stop-Stack }
        "4" { Clean-Docker }
        "5" { Full-Reset }
        "q" { exit }
        "Q" { exit }
        default { Write-Host "Invalid option, try again." -ForegroundColor Red; Start-Sleep -Seconds 1 }
    }
}
