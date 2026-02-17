#!/bin/bash

# PDF to Excel Converter - Run Script

echo "🚀 Starting PDF to Excel Converter..."
echo ""

# Check if virtual environment exists
if [ -d "venv" ]; then
    echo "✅ Virtual environment found"
    source venv/bin/activate
else
    echo "⚠️  Virtual environment not found. Creating one..."
    python3 -m venv venv
    source venv/bin/activate
    echo "📦 Installing dependencies..."
    pip install -r requirements.txt
fi

# Check if Tesseract is installed
if command -v tesseract &> /dev/null; then
    echo "✅ Tesseract OCR found"
else
    echo "⚠️  Tesseract OCR not found. Please install it:"
    echo "   macOS: brew install tesseract"
    echo "   Linux: sudo apt-get install tesseract-ocr"
    exit 1
fi

echo ""
echo "🌐 Starting Streamlit application..."
echo ""

streamlit run pdf_to_excel_converter.py
