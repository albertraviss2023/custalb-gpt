param(
  [switch]$Build
)

$composeFile = "infra/docker-compose.yml"

if ($Build) {
  docker compose -f $composeFile up --build -d
} else {
  docker compose -f $composeFile up -d
}

Write-Host "Stack started. UI: http://localhost:3000 API: http://localhost:8000"