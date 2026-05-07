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
set "PKG_DIR=%TEMP%\%PKG_NAME%"
set "PKG_ZIP=%ROOT%%PKG_NAME%.zip"

echo Packaging Pixelle-Video v%VERSION% for Windows x64
echo.
echo Source: %ROOT%
echo Output: %PKG_ZIP%
echo.

:: === Step 1: Clean up temp/build artifacts ===
echo [1/4] Cleaning build artifacts...

if exist "%ROOT%Pixelle-Video\.venv\" (
    echo   Removing .venv/ (will be recreated on first run)...
    rmdir /s /q "%ROOT%Pixelle-Video\.venv\"
)

if exist "%ROOT%Pixelle-Video\output\" (
    echo   Cleaning output/...
    rmdir /s /q "%ROOT%Pixelle-Video\output\"
)

if exist "%ROOT%Pixelle-Video\temp\" (
    echo   Cleaning temp/...
    rmdir /s /q "%ROOT%Pixelle-Video\temp\"
)

if exist "%ROOT%Pixelle-Video\data\" (
    echo   Cleaning data/...
    rmdir /s /q "%ROOT%Pixelle-Video\data\"
)

:: Remove pycache
echo   Cleaning __pycache__...
for /d /r "%ROOT%Pixelle-Video\" %%d in (__pycache__) do (
    if exist "%%d" rmdir /s /q "%%d" 2>nul
)

for /d /r "%ROOT%Pixelle-Video\" %%d in (.pytest_cache) do (
    if exist "%%d" rmdir /s /q "%%d" 2>nul
)

:: Remove .git artifacts
if exist "%ROOT%Pixelle-Video\.git\" (
    echo   Removing .git/ (saves ~200MB)...
    rmdir /s /q "%ROOT%Pixelle-Video\.git\"
)

:: Remove config.yaml (user-specific)
if exist "%ROOT%Pixelle-Video\config.yaml" (
    del "%ROOT%Pixelle-Video\config.yaml" 2>nul
)

:: Remove egg-info
for /d /r "%ROOT%Pixelle-Video\" %%d in (*.egg-info) do (
    if exist "%%d" rmdir /s /q "%%d" 2>nul
)

echo   Done.
echo.

:: === Step 2: Create temp staging directory ===
echo [2/4] Staging files...
if exist "%PKG_DIR%" rmdir /s /q "%PKG_DIR%"
mkdir "%PKG_DIR%" 2>nul

:: Copy everything
xcopy "%ROOT%*" "%PKG_DIR%\" /E /I /Q /H >nul

echo   Staged to: %PKG_DIR%
echo.

:: === Step 3: Create zip ===
echo [3/4] Creating zip package (this may take a while)...

:: Clean up any previous package
if exist "%PKG_ZIP%" del "%PKG_ZIP%" 2>nul

:: Use PowerShell for zip creation
powershell -Command "& {
    Add-Type -AssemblyName System.IO.Compression.FileSystem
    $compress = [System.IO.Compression.ZipFile]::Create('%PKG_ZIP:\=\\%')
    $source = '%PKG_DIR:\=\\%'
    $items = Get-ChildItem -Path $source -Recurse
    $baseLen = $source.Length + 1
    foreach ($item in $items) {
        $relPath = $item.FullName.Substring($baseLen)
        if (-not $item.PSIsContainer) {
            [System.IO.Compression.ZipFileExtensions]::CreateEntryFromFile($compress, $item.FullName, $relPath) | Out-Null
        }
    }
    $compress.Dispose()
}"

if !errorlevel! neq 0 (
    echo [ERROR] Failed to create zip package!
    rmdir /s /q "%PKG_DIR%" 2>nul
    pause
    exit /b 1
)

echo.
echo [4/4] Cleaning up staging directory...
rmdir /s /q "%PKG_DIR%" 2>nul

:: === Done ===
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
