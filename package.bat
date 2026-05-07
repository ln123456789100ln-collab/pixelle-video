@echo off
chcp 65001 >nul
setlocal enabledelayedexpansion

echo ========================================
echo   Pixelle-Video - Package Builder
echo ========================================
echo.

:: Configuration
set "ROOT=%~dp0"
set "VERSION_FILE=%ROOT%Pixelle-Video\pyproject.toml"

:: Read version from pyproject.toml
for /f "tokens=2 delims= " %%a in ('findstr "version" "%VERSION_FILE%"') do (
    set "VERSION=%%a"
    goto :got_version
)
:got_version
set "VERSION=%VERSION:"=%"
if "%VERSION%"=="" set "VERSION=0.1.15"
set "PKG_NAME=pixelle-video-v%VERSION%-win64"
set "PKG_ZIP=%ROOT%%PKG_NAME%.zip"

echo Packaging Pixelle-Video v%VERSION% for Windows x64
echo.
echo Source: %ROOT%
echo Output: %PKG_ZIP%
echo.

:: Clean up any previous package
if exist "%PKG_ZIP%" del "%PKG_ZIP%" 2>nul

:: === Step 1: Clean up temp/build artifacts ===
echo [1/3] Cleaning build artifacts...

if exist "%ROOT%Pixelle-Video\.venv\" (
    echo   Removing .venv/ (will be recreated on first run)...
    rmdir /s /q "%ROOT%Pixelle-Video\.venv\"
)

if exist "%ROOT%Pixelle-Video\output\" (
    rmdir /s /q "%ROOT%Pixelle-Video\output\"
)

if exist "%ROOT%Pixelle-Video\temp\" (
    rmdir /s /q "%ROOT%Pixelle-Video\temp\"
)

if exist "%ROOT%Pixelle-Video\data\" (
    rmdir /s /q "%ROOT%Pixelle-Video\data\"
)

:: Remove __pycache__ and egg-info
for /d /r "%ROOT%Pixelle-Video\" %%d in (__pycache__ .pytest_cache *.egg-info) do (
    if exist "%%d" rmdir /s /q "%%d" 2>nul
)

:: Remove config.yaml (user-specific)
if exist "%ROOT%Pixelle-Video\config.yaml" (
    del "%ROOT%Pixelle-Video\config.yaml" 2>nul
)

echo   Done.
echo.

:: === Step 2: Create zip (direct from source, exclude .git) ===
echo [2/3] Creating zip package...
echo   This may take a few minutes (processing python/ + tools/)...
echo.

powershell -Command "& {
    Add-Type -AssemblyName System.IO.Compression.FileSystem
    $zipPath = '%PKG_ZIP:\=\\%'
    $source = '%ROOT:\=\\%'
    $excludeDirs = @('.git')

    $compress = [System.IO.Compression.ZipFile]::Create($zipPath)
    $items = Get-ChildItem -Path $source -Recurse
    $baseLen = $source.Length

    foreach ($item in $items) {
        if ($item.PSIsContainer) { continue }

        $relPath = $item.FullName.Substring($baseLen)
        # Skip files in excluded directories
        $skip = $false
        foreach ($exDir in $excludeDirs) {
            if ($relPath -match ('^' + [regex]::Escape($exDir) + '\\')) {
                $skip = $true
                break
            }
        }
        if (-not $skip) {
            [System.IO.Compression.ZipFileExtensions]::CreateEntryFromFile($compress, $item.FullName, $relPath) | Out-Null
        }
    }
    $compress.Dispose()
}"

if !errorlevel! neq 0 (
    echo [ERROR] Failed to create zip package!
    pause
    exit /b 1
)

:: === Step 3: Show result ===
echo.
echo [3/3] Done!
echo.
echo ========================================
echo   Package created successfully!
echo ========================================
echo.
echo   File: %PKG_ZIP%
echo.
echo   To distribute:
echo   1. Upload this zip to Baidu Netdisk / GitHub Releases
echo   2. Users extract and run start.bat
echo   3. First run auto-installs dependencies
echo.
echo   Size:
call :GetFileSize "%PKG_ZIP%"
echo.

goto :eof

:GetFileSize
set "FILE=%~1"
for %%a in ("%FILE%") do set "SIZE=%%~za"
set /a "SIZE_MB=%SIZE% / 1048576"
echo     %SIZE_MB% MB
goto :eof
