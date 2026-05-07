@echo off
chcp 65001 >nul
setlocal enabledelayedexpansion

echo ========================================
echo   Pixelle-Video - Windows Launcher
echo ========================================
echo.

:: Set environment variables
set "PYTHON_HOME=%~dp0python\python311"
set "PATH=%PYTHON_HOME%;%PYTHON_HOME%\Scripts;%~dp0tools\ffmpeg\bin;%PATH%"
set "PROJECT_ROOT=%~dp0Pixelle-Video"

:: Change to project directory
cd /d "%PROJECT_ROOT%"

:: Set PYTHONPATH to project root for module imports
set "PYTHONPATH=%PROJECT_ROOT%"

:: Set PIXELLE_VIDEO_ROOT environment variable for reliable path resolution
set "PIXELLE_VIDEO_ROOT=%PROJECT_ROOT%"

:: ==================== First-time setup ====================
echo [Setup] Checking environment...

:: Step 1: Create config.yaml if missing
if not exist "%PROJECT_ROOT%\config.yaml" (
    if exist "%PROJECT_ROOT%\config.example.yaml" (
        echo [Setup] Creating config.yaml from config.example.yaml...
        copy "%PROJECT_ROOT%\config.example.yaml" "%PROJECT_ROOT%\config.yaml" >nul
        echo [Setup] ✓ config.yaml created. Please configure your API keys in the web UI.
    ) else (
        echo [Setup] ⚠ config.example.yaml not found, creating minimal config.yaml...
        (
            echo # Pixelle-Video Configuration
            echo # Configure API keys and settings in the Web UI after starting.
            echo llm:
            echo   base_url: ""
            echo   api_key: ""
            echo   model: ""
            echo comfyui:
            echo   runninghub_api_key: ""
        ) > "%PROJECT_ROOT%\config.yaml"
    )
) else (
    echo [Setup] ✓ config.yaml found
)

:: Step 2: Create .venv + install dependencies if missing
if not exist "%PROJECT_ROOT%\.venv\" (
    echo [Setup] First-time setup detected. Installing dependencies...
    echo [Setup] This may take a few minutes...
    echo.

    :: Create virtual environment
    "%PYTHON_HOME%\python.exe" -m venv "%PROJECT_ROOT%\.venv"
    if !errorlevel! neq 0 (
        echo [ERROR] Failed to create virtual environment
        pause
        exit /b 1
    )

    :: Install project in editable mode
    echo [Setup] Installing pixelle-video and dependencies...
    "%PROJECT_ROOT%\.venv\Scripts\pip.exe" install -e "%PROJECT_ROOT%"
    if !errorlevel! neq 0 (
        echo [ERROR] Failed to install dependencies
        pause
        exit /b 1
    )

    echo.
    echo [Setup] ✓ Dependencies installed successfully!
    echo.
) else (
    echo [Setup] ✓ Virtual environment found
)

:: ==================== Launch ====================
echo.
echo ========================================
echo   Starting Pixelle-Video Web UI...
echo ========================================
echo.
echo Browser will open automatically.
echo Press Ctrl+C to stop the server
echo.
echo Note: Configure API keys and settings in the Web UI.
echo ========================================
echo.

"%PROJECT_ROOT%\.venv\Scripts\python.exe" -m streamlit run web\app.py

if errorlevel 1 (
    echo.
    echo [ERROR] Failed to start. Please check:
    echo   1. API keys are configured in config.yaml or the Web UI
    echo   2. Internet connection is available
    echo.
    pause
)
