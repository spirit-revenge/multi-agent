@echo off
REM LectureCrewLLM Web UI Startup Script for Windows
REM This script starts the Flask web application

setlocal enabledelayedexpansion

echo.
echo ==========================================
echo. 🚀 LectureCrewLLM Web UI Launcher
echo ==========================================
echo.

REM Check if conda is available
where conda >nul 2>nul
if %ERRORLEVEL% neq 0 (
    echo. ❌ Error: Conda is not installed or not in PATH
    echo. Please install Anaconda/Miniconda first
    pause
    exit /b 1
)

REM Check if the camel environment exists
conda info --envs | find "camel" >nul 2>nul
if %ERRORLEVEL% neq 0 (
    echo. ❌ Error: Conda environment 'camel' not found
    echo. Please create the environment first
    pause
    exit /b 1
)

REM Check if Flask is installed
echo. 📦 Checking Flask installation...
conda run -n camel python -c "import flask" >nul 2>nul
if %ERRORLEVEL% neq 0 (
    echo. ⚠️  Flask not found. Installing Flask...
    call conda run -n camel pip install Flask==3.0.0 >nul 2>nul
    if %ERRORLEVEL% equ 0 (
        echo. ✅ Flask installed successfully
    ) else (
        echo. ❌ Failed to install Flask
        pause
        exit /b 1
    )
) else (
    echo. ✅ Flask is installed
)

REM Check if required directories exist
echo.
echo. 📁 Checking directories...
if not exist "knowledge" mkdir knowledge
if not exist "conversations" mkdir conversations
if not exist "conversations\sessions" mkdir conversations\sessions
if not exist "cache" mkdir cache
if not exist "output" mkdir output
if not exist "templates" mkdir templates
if not exist "static" mkdir static
echo. ✅ All directories ready

REM Get current directory
for /f "delims=" %%i in ('cd') do set "SCRIPT_DIR=%%i"

REM Display startup information
echo.
echo ==========================================
echo ✅ Ready to start Web UI
echo ==========================================
echo.
echo 📍 Web UI URL:      http://localhost:7860
echo 📂 Lecture files:   %SCRIPT_DIR%\knowledge\
echo 💾 Conversations:   %SCRIPT_DIR%\conversations\
echo 📊 Cache:           %SCRIPT_DIR%\cache\
echo 📄 Outputs:         %SCRIPT_DIR%\output\
echo.
echo 🎯 Press Ctrl+C to stop the server
echo ==========================================
echo.

REM Start the web UI
call conda run -n camel python web_ui.py
pause
