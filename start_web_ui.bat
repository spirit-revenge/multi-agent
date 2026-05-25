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

echo   URL:       http://localhost:7860
echo   Lectures:  %CD%\knowledge\
echo   Output:    %CD%\output\
echo   Press Ctrl+C to stop
echo ==========================================
echo.

python web_ui.py
pause
