$models = @("gemma4:e2b", "gemma4:e4b", "gemma4:26b")

foreach ($model in $models) {
  Write-Host "Pulling $model ..."
  docker exec goi-ollama ollama pull $model
}

Write-Host "Model bootstrap complete."