# PDF to Excel Converter

A powerful tool that converts PDF files to Excel spreadsheets using OCR (Optical Character Recognition) technology. This tool can extract data from both scanned PDFs and text-based PDFs, making it perfect for digitizing documents, extracting tables, and converting structured data.

## Features

- 📄 **Multiple Extraction Modes**: Structured data, tables, or simple line-by-line extraction
- 🖼️ **OCR Technology**: Uses Tesseract OCR to extract text from scanned documents
- 📊 **Smart Table Detection**: Automatically detects and extracts table structures
- ⚙️ **Customizable Settings**: Adjust DPI, extraction mode, and text detection mode
- 📥 **Excel Export**: Clean, formatted Excel files with auto-adjusted column widths
- 🎨 **Modern UI**: Beautiful Streamlit interface with real-time progress tracking

## Prerequisites

### System Requirements

1. **Python 3.8+**
2. **Tesseract OCR** - Required for text extraction
3. **Poppler** - Required for PDF to image conversion

### Installing System Dependencies

#### macOS
```bash
# Install Tesseract OCR
brew install tesseract

# Install Poppler
brew install poppler
```

#### Linux (Ubuntu/Debian)
```bash
# Install Tesseract OCR
sudo apt-get update
sudo apt-get install tesseract-ocr

# Install Poppler
sudo apt-get install poppler-utils
```

#### Windows
1. Download Tesseract from: https://github.com/UB-Mannheim/tesseract/wiki
2. Download Poppler from: https://github.com/oschwartz10612/poppler-windows/releases
3. Add both to your system PATH

## Installation

1. **Clone or download this repository**

2. **Create a virtual environment (recommended)**
```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

3. **Install Python dependencies**
```bash
pip install -r requirements.txt
```

## Usage

### Running the Application

```bash
streamlit run pdf_to_excel_converter.py
```

The application will open in your default web browser at `http://localhost:8501`

### How to Use

1. **Upload PDF**: Click "Upload PDF File" and select your PDF document
2. **Configure Settings** (optional):
   - **Extraction Mode**: Choose how data should be extracted
     - `structured`: For documents with key-value pairs
     - `table`: For table-like structures
     - `simple`: Line-by-line extraction
   - **Text Detection Mode**: Choose OCR detection method
     - `auto`: Automatically detects the best mode
     - `table`: Optimized for tables
     - `single_column`: For single column documents
     - `single_block`: For uniform text blocks
   - **OCR Quality (DPI)**: Higher values = better quality but slower (200-400)
3. **Start Extraction**: Click "🚀 Start Extraction"
4. **Review Results**: Preview the extracted data
5. **Download**: Click "📥 Download Excel File" to save the results

## Extraction Modes Explained

### Structured Mode
Best for documents with:
- Key-value pairs (e.g., "Name: John Doe")
- Forms with labels
- Documents with consistent formatting

### Table Mode
Best for:
- Tabular data
- Spreadsheet-like content
- Documents with clear rows and columns

### Simple Mode
Best for:
- Plain text documents
- Line-by-line data
- Unstructured content

## Tips for Best Results

1. **Image Quality**: Higher quality scans produce better OCR results
2. **DPI Settings**: Use 300-400 DPI for scanned documents, 200-300 for text PDFs
3. **Document Type**: Choose the extraction mode that matches your document structure
4. **Large Files**: Processing large PDFs may take time - be patient!
5. **Language**: Currently optimized for English text. For other languages, you may need to install additional Tesseract language packs.

## Troubleshooting

### Tesseract Not Found
- **macOS**: Ensure Tesseract is installed via Homebrew and in PATH
- **Linux**: Check installation with `tesseract --version`
- **Windows**: Verify Tesseract is in system PATH

### Poppler Errors
- Ensure Poppler is installed and accessible
- On Windows, add Poppler `bin` directory to PATH

### Poor OCR Results
- Try increasing DPI setting
- Ensure PDF images are clear and not too dark/light
- Try different extraction modes
- For scanned documents, ensure good image quality

### Memory Issues
- Process PDFs page by page for very large files
- Reduce DPI if processing is too slow
- Close other applications to free up memory

## File Structure

```
PDF_To_Excel/
├── pdf_to_excel_converter.py  # Main application
├── backend.py                 # Original voter list converter (legacy)
├── requirements.txt           # Python dependencies
├── README.md                  # This file
└── venv/                      # Virtual environment (created locally)
```

## Technical Details

- **OCR Engine**: Tesseract OCR
- **Image Processing**: OpenCV
- **PDF Processing**: pdf2image (Poppler)
- **Data Processing**: Pandas
- **Excel Export**: openpyxl, xlsxwriter
- **UI Framework**: Streamlit

## Limitations

- OCR accuracy depends on image quality
- Complex layouts may require manual adjustment
- Handwritten text has limited support
- Very large PDFs may take significant time to process
- Currently optimized for English text

## Future Enhancements

- [ ] Multi-language support
- [ ] Batch processing multiple PDFs
- [ ] Custom field mapping
- [ ] Advanced table detection algorithms
- [ ] Export to other formats (CSV, JSON)
- [ ] Cloud deployment support

## License

This project is open source and available for personal and commercial use.

## Support

For issues or questions:
1. Check the troubleshooting section
2. Verify all dependencies are installed correctly
3. Ensure your PDF is not corrupted or password-protected

---

**Made with ❤️ for easy PDF data extraction**
