# Pixelle-Video Packaging Script
Write-Host "=== Packaging Pixelle-Video ===" -ForegroundColor Cyan
Write-Host ""

$ROOT = Split-Path -Parent $MyInvocation.MyCommand.Path
$zipPath = Join-Path $ROOT "pixelle-video-v0.1.15-win64.zip"

# Step 1: Clean artifacts
Write-Host "[1/3] Cleaning build artifacts..." -ForegroundColor Yellow

$cleanDirs = @(
    "Pixelle-Video\.venv",
    "Pixelle-Video\output",
    "Pixelle-Video\temp",
    "Pixelle-Video\data"
)
foreach ($dir in $cleanDirs) {
    $fullPath = Join-Path $ROOT $dir
    if (Test-Path $fullPath) {
        Remove-Item -Recurse -Force $fullPath
        Write-Host "  Removed $dir"
    }
}

# Remove __pycache__ etc.
Get-ChildItem -Path (Join-Path $ROOT "Pixelle-Video") -Recurse -Directory -Include "__pycache__", ".pytest_cache", "*.egg-info" | ForEach-Object {
    Remove-Item -Recurse -Force $_.FullName -ErrorAction SilentlyContinue
}
Write-Host "  Cleaned __pycache__"

# Remove config.yaml (user-specific)
$configPath = Join-Path $ROOT "Pixelle-Video\config.yaml"
if (Test-Path $configPath) {
    Remove-Item -Force $configPath
    Write-Host "  Removed config.yaml"
}

# Remove old zip
if (Test-Path $zipPath) { Remove-Item -Force $zipPath }

Write-Host "  Done"
Write-Host ""

# Step 2: Create zip
Write-Host "[2/3] Creating zip package..." -ForegroundColor Yellow
Write-Host "  (processing python/ + tools/ may take a while)"
Write-Host ""

# Get total file count for progress
$totalFiles = (Get-ChildItem -Path $ROOT -Recurse -File | Where-Object { $_.FullName -notmatch '\\.git\\' }).Count
Write-Host "  Compressing $totalFiles files..."

Compress-Archive -Path "$ROOT\*" -DestinationPath $zipPath -CompressionLevel Optimal

Write-Host ""
Write-Host "[3/3] Done!" -ForegroundColor Green

# Show result
$size = (Get-Item $zipPath).Length
$mb = [math]::Round($size / 1MB, 1)

Write-Host ""
Write-Host "========================" -ForegroundColor Cyan
Write-Host "Package created!" -ForegroundColor Green
Write-Host "========================" -ForegroundColor Cyan
Write-Host ""
Write-Host "  File: $zipPath"
Write-Host "  Size: $mb MB"
Write-Host ""
Write-Host "Share this zip with your users."
Write-Host "They extract and double-click start.bat"
