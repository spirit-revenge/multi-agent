@echo off
REM LectureCrewLLM Web UI Startup Script for Windows

echo.
echo ==========================================
echo   LectureCrewLLM Web UI
echo ==========================================
echo.

REM Ensure required directories exist
if not exist "knowledge" mkdir knowledge
if not exist "conversations\sessions" mkdir conversations\sessions
if not exist "cache" mkdir cache
if not exist "output" mkdir output

REM Try to read WEB_UI_PORT from .env (default 7860)
set PORT=7860
if exist .env (
    for /f "tokens=1,2 delims==" %%a in ('findstr /b "WEB_UI_PORT" .env') do set PORT=%%b
)

echo   URL:       http://localhost:%PORT%
echo   Lectures:  %CD%\knowledge\
echo   Output:    %CD%\output\
echo   Press Ctrl+C to stop
echo ==========================================
echo.

python web_ui.py
