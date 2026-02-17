@echo off
REM PDF to Excel Converter - Run Script for Windows

echo Starting PDF to Excel Converter...
echo.

REM Check if virtual environment exists
if exist "venv" (
    echo Virtual environment found
    call venv\Scripts\activate.bat
) else (
    echo Virtual environment not found. Creating one...
    python -m venv venv
    call venv\Scripts\activate.bat
    echo Installing dependencies...
    pip install -r requirements.txt
)

REM Check if Tesseract is installed
where tesseract >nul 2>&1
if %ERRORLEVEL% EQU 0 (
    echo Tesseract OCR found
) else (
    echo WARNING: Tesseract OCR not found in PATH.
    echo Please install Tesseract from: https://github.com/UB-Mannheim/tesseract/wiki
    echo.
    pause
    exit /b 1
)

echo.
echo Starting Streamlit application...
echo.

streamlit run pdf_to_excel_converter.py

pause
