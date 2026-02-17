import streamlit as st
import pandas as pd
import numpy as np
import cv2
import pytesseract
import re
import os
import io
from pdf2image import convert_from_path
from PIL import Image
import tempfile

# --- PAGE CONFIGURATION ---
st.set_page_config(
    page_title="PDF to Excel Converter",
    page_icon="📄",
    layout="wide"
)

# --- CSS FOR UI POLISH ---
st.markdown("""
<style>
    .stButton>button {
        width: 100%;
        background-color: #1f77b4;
        color: white;
        font-weight: bold;
        border-radius: 5px;
    }
    .main-header {
        text-align: center;
        color: #1f77b4;
        padding: 20px;
    }
</style>
""", unsafe_allow_html=True)

# ==========================================
#        IMAGE PREPROCESSING
# ==========================================

def preprocess_image(image_pil, enhance_quality=True):
    """Preprocess image for better OCR results."""
    img = cv2.cvtColor(np.array(image_pil), cv2.COLOR_RGB2BGR)
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    
    if enhance_quality:
        # Apply denoising
        denoised = cv2.fastNlMeansDenoising(gray, None, 10, 7, 21)
        
        # Apply thresholding
        _, thresh = cv2.threshold(denoised, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        
        # Apply morphological operations to clean up
        kernel = np.ones((1, 1), np.uint8)
        cleaned = cv2.morphologyEx(thresh, cv2.MORPH_CLOSE, kernel)
        
        return cleaned
    return gray

def enhance_image_for_ocr(image):
    """Additional image enhancement for better OCR accuracy."""
    # Convert to numpy array if PIL Image
    if isinstance(image, Image.Image):
        img = np.array(image)
        if len(img.shape) == 3:
            img = cv2.cvtColor(img, cv2.COLOR_RGB2GRAY)
    else:
        img = image.copy()
    
    # Increase contrast
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
    enhanced = clahe.apply(img)
    
    # Sharpen
    kernel = np.array([[-1, -1, -1],
                       [-1,  9, -1],
                       [-1, -1, -1]])
    sharpened = cv2.filter2D(enhanced, -1, kernel)
    
    return sharpened

# ==========================================
#        TABLE DETECTION
# ==========================================

def detect_tables(image):
    """Detect table structures in the image."""
    gray = preprocess_image(image, enhance_quality=True)
    
    # Detect horizontal lines
    horizontal_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (40, 1))
    detected_lines = cv2.morphologyEx(gray, cv2.MORPH_OPEN, horizontal_kernel, iterations=2)
    cnts = cv2.findContours(detected_lines, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    cnts = cnts[0] if len(cnts) == 2 else cnts[1]
    
    # Detect vertical lines
    vertical_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (1, 40))
    detected_lines = cv2.morphologyEx(gray, cv2.MORPH_OPEN, vertical_kernel, iterations=2)
    cnts2 = cv2.findContours(detected_lines, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    cnts2 = cnts2[0] if len(cnts2) == 2 else cnts2[1]
    
    return len(cnts) > 0 or len(cnts2) > 0

def extract_table_data(image, psm_mode=6):
    """Extract data from table-like structures."""
    enhanced = enhance_image_for_ocr(image)
    
    # Try different PSM modes for better table detection
    configs = [
        f'--psm {psm_mode}',  # Uniform block of text
        '--psm 4',  # Single column of text
        '--psm 11',  # Sparse text
    ]
    
    all_text = []
    for config in configs:
        try:
            text = pytesseract.image_to_string(enhanced, config=config)
            if text.strip():
                all_text.append(text)
        except:
            continue
    
    # Use the text with most content
    if all_text:
        return max(all_text, key=len)
    return ""

# ==========================================
#        TEXT EXTRACTION MODES
# ==========================================

def extract_text_blocks(image, mode="auto"):
    """Extract text in blocks (for structured documents)."""
    enhanced = enhance_image_for_ocr(image)
    
    if mode == "auto":
        # Try to detect if it's a table
        if detect_tables(image):
            return extract_table_data(image, psm_mode=6)
        else:
            # Use block text mode
            config = '--psm 6'
    elif mode == "table":
        config = '--psm 6'
    elif mode == "single_column":
        config = '--psm 4'
    elif mode == "single_block":
        config = '--psm 6'
    else:
        config = '--psm 6'
    
    text = pytesseract.image_to_string(enhanced, config=config)
    return text

def parse_text_to_dataframe(text, extraction_mode="structured"):
    """Parse extracted text into a DataFrame."""
    lines = [line.strip() for line in text.split('\n') if line.strip()]
    
    if not lines:
        return pd.DataFrame()
    
    if extraction_mode == "structured":
        # Try to detect structured data (key-value pairs, tables, etc.)
        return parse_structured_text(lines)
    elif extraction_mode == "table":
        # Try to parse as table
        return parse_table_text(lines)
    else:
        # Simple line-by-line extraction
        return pd.DataFrame({"Text": lines})

def parse_structured_text(lines):
    """Parse structured text with key-value pairs."""
    data = []
    current_record = {}
    
    for line in lines:
        # Check for key-value pairs (e.g., "Name: John", "Age: 25")
        if ':' in line:
            parts = line.split(':', 1)
            if len(parts) == 2:
                key = parts[0].strip()
                value = parts[1].strip()
                current_record[key] = value
        # Check for tab-separated values
        elif '\t' in line:
            values = line.split('\t')
            if len(values) > 1:
                if not current_record:
                    # First row might be headers
                    headers = [v.strip() for v in values]
                    continue
                else:
                    data.append(current_record)
                    current_record = {}
                    for i, val in enumerate(values):
                        if i < len(headers):
                            current_record[headers[i]] = val.strip()
        # Check for multiple spaces (potential columns)
        elif len(line.split()) > 3:
            parts = line.split()
            if len(parts) >= 2:
                # Treat as simple record
                if current_record:
                    data.append(current_record)
                current_record = {"Content": line}
        else:
            # Continuation of previous field
            if current_record:
                last_key = list(current_record.keys())[-1]
                current_record[last_key] += " " + line
    
    if current_record:
        data.append(current_record)
    
    if data:
        return pd.DataFrame(data)
    else:
        # Fallback: return as single column
        return pd.DataFrame({"Extracted Text": lines})

def parse_table_text(lines):
    """Parse text as table format."""
    rows = []
    headers = None
    
    for i, line in enumerate(lines):
        # Remove extra whitespace
        line = re.sub(r'\s+', ' ', line.strip())
        
        # Try to split by multiple spaces, tabs, or pipes
        if '\t' in line:
            cells = [c.strip() for c in line.split('\t')]
        elif '|' in line:
            cells = [c.strip() for c in line.split('|')]
        else:
            # Split by 2+ spaces
            cells = [c.strip() for c in re.split(r'\s{2,}', line)]
        
        if cells and any(c for c in cells):
            if headers is None and i < 3:
                # First few lines might be headers
                headers = cells
            else:
                if headers and len(cells) == len(headers):
                    rows.append(dict(zip(headers, cells)))
                elif len(cells) > 1:
                    # Use generic headers
                    if headers is None:
                        headers = [f"Column_{j+1}" for j in range(len(cells))]
                    # Pad or truncate to match headers
                    while len(cells) < len(headers):
                        cells.append("")
                    cells = cells[:len(headers)]
                    rows.append(dict(zip(headers, cells)))
    
    if rows:
        return pd.DataFrame(rows)
    else:
        # Fallback
        return pd.DataFrame({"Extracted Text": lines})

# ==========================================
#        MAIN PROCESSING FUNCTION
# ==========================================

def process_pdf(pdf_path, extraction_mode="structured", text_mode="auto", 
                dpi=300, progress_bar=None, status_text=None):
    """Main function to process PDF and extract data."""
    all_data = []
    
    try:
        images = convert_from_path(pdf_path, dpi=dpi)
    except Exception as e:
        st.error(f"Error reading PDF: {e}")
        return pd.DataFrame()
    
    total_pages = len(images)
    
    for page_num, img_pil in enumerate(images):
        if progress_bar:
            progress = (page_num + 1) / total_pages
            progress_bar.progress(progress, text=f"Processing page {page_num + 1} of {total_pages}...")
        
        if status_text:
            status_text.text(f"📄 Extracting text from page {page_num + 1}...")
        
        # Extract text from page
        text = extract_text_blocks(img_pil, mode=text_mode)
        
        if text.strip():
            # Parse text to DataFrame
            df_page = parse_text_to_dataframe(text, extraction_mode=extraction_mode)
            
            if not df_page.empty:
                # Add page number column
                df_page.insert(0, "Page", page_num + 1)
                all_data.append(df_page)
    
    if all_data:
        # Combine all pages
        final_df = pd.concat(all_data, ignore_index=True)
        return final_df
    else:
        return pd.DataFrame()

# ==========================================
#        STREAMLIT UI
# ==========================================

st.markdown('<h1 class="main-header">📄 PDF to Excel Converter</h1>', unsafe_allow_html=True)
st.markdown("### Extract data from PDF files using OCR and convert to Excel")

# Sidebar for settings
with st.sidebar:
    st.header("⚙️ Settings")
    
    extraction_mode = st.selectbox(
        "Extraction Mode",
        ["structured", "table", "simple"],
        help="structured: Detects key-value pairs and structured data\n"
             "table: Parses data as table format\n"
             "simple: Line-by-line extraction"
    )
    
    text_mode = st.selectbox(
        "Text Detection Mode",
        ["auto", "table", "single_column", "single_block"],
        help="auto: Automatically detects best mode\n"
             "table: Optimized for tables\n"
             "single_column: Single column of text\n"
             "single_block: Uniform block of text"
    )
    
    dpi = st.slider(
        "OCR Quality (DPI)",
        min_value=200,
        max_value=400,
        value=300,
        step=50,
        help="Higher DPI = Better quality but slower processing"
    )
    
    st.markdown("---")
    st.markdown("### 📋 Instructions")
    st.markdown("""
    1. Upload a PDF file (scanned or text-based)
    2. Choose extraction mode based on your document type
    3. Click 'Start Extraction'
    4. Review the extracted data
    5. Download as Excel file
    """)

# Main content area
uploaded_file = st.file_uploader("Upload PDF File", type=["pdf"], help="Supported: Scanned PDFs, Text PDFs, Tables")

if uploaded_file is not None:
    # Save uploaded file temporarily
    with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp_file:
        tmp_file.write(uploaded_file.getbuffer())
        temp_path = tmp_file.name
    
    file_size = len(uploaded_file.getbuffer()) / (1024 * 1024)  # Size in MB
    st.success(f"✅ File loaded: **{uploaded_file.name}** ({file_size:.2f} MB)")
    
    col1, col2 = st.columns([1, 1])
    
    with col1:
        extract_button = st.button("🚀 Start Extraction", use_container_width=True)
    
    with col2:
        if st.button("🔄 Reset", use_container_width=True):
            st.rerun()
    
    if extract_button:
        # Check Tesseract path (for Mac)
        try:
            # Try common Mac paths
            possible_paths = [
                '/opt/homebrew/bin/tesseract',
                '/usr/local/bin/tesseract',
                '/usr/bin/tesseract'
            ]
            
            tesseract_found = False
            for path in possible_paths:
                if os.path.exists(path):
                    pytesseract.pytesseract.tesseract_cmd = path
                    tesseract_found = True
                    break
            
            if not tesseract_found:
                # Try to use system default
                try:
                    pytesseract.get_tesseract_version()
                except:
                    st.error("⚠️ Tesseract OCR not found. Please install it:\n"
                            "Mac: `brew install tesseract`\n"
                            "Linux: `sudo apt-get install tesseract-ocr`\n"
                            "Windows: Download from GitHub")
                    st.stop()
        except Exception as e:
            st.warning(f"Tesseract check: {e}")
        
        # Create progress indicators
        progress_bar = st.progress(0, text="Initializing...")
        status_text = st.empty()
        
        # Process PDF
        with st.spinner("Processing PDF... This may take a while for large files."):
            df = process_pdf(
                temp_path,
                extraction_mode=extraction_mode,
                text_mode=text_mode,
                dpi=dpi,
                progress_bar=progress_bar,
                status_text=status_text
            )
        
        # Clean up
        progress_bar.empty()
        status_text.empty()
        
        if os.path.exists(temp_path):
            os.remove(temp_path)
        
        # Display results
        if not df.empty:
            st.balloons()
            st.success(f"✅ Successfully extracted {len(df)} rows from {uploaded_file.name}!")
            
            # Show statistics
            col1, col2, col3 = st.columns(3)
            with col1:
                st.metric("Total Rows", len(df))
            with col2:
                st.metric("Total Columns", len(df.columns))
            with col3:
                st.metric("Pages Processed", df['Page'].nunique() if 'Page' in df.columns else 1)
            
            # Display preview
            st.markdown("### 📊 Preview of Extracted Data")
            st.dataframe(df.head(20), use_container_width=True, height=400)
            
            # Download section
            st.markdown("### 📥 Download")
            
            buffer = io.BytesIO()
            with pd.ExcelWriter(buffer, engine='xlsxwriter') as writer:
                df.to_excel(writer, index=False, sheet_name='Extracted Data')
                worksheet = writer.sheets['Extracted Data']
                
                # Auto-adjust column widths
                for i, col in enumerate(df.columns):
                    max_len = max(
                        df[col].astype(str).map(len).max() if len(df) > 0 else len(col),
                        len(col)
                    ) + 2
                    worksheet.set_column(i, i, min(max_len, 50))
            
            buffer.seek(0)
            
            output_filename = uploaded_file.name.replace('.pdf', '_extracted.xlsx')
            
            st.download_button(
                label="📥 Download Excel File",
                data=buffer,
                file_name=output_filename,
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                use_container_width=True
            )
            
            # Show column info
            with st.expander("📋 Column Information"):
                st.json({col: str(df[col].dtype) for col in df.columns})
        else:
            st.error("❌ No data could be extracted from the PDF. Try adjusting the extraction settings or check if the PDF contains readable text/images.")
            st.info("💡 Tips:\n"
                   "- For scanned documents, ensure good image quality\n"
                   "- Try different extraction modes\n"
                   "- Increase DPI for better OCR accuracy\n"
                   "- Check if the PDF is password-protected")

else:
    st.info("👆 Please upload a PDF file to get started")
    
    # Show example use cases
    st.markdown("---")
    st.markdown("### 💡 Supported Document Types")
    col1, col2, col3 = st.columns(3)
    
    with col1:
        st.markdown("""
        **📋 Tables & Forms**
        - Invoice tables
        - Data sheets
        - Forms with fields
        """)
    
    with col2:
        st.markdown("""
        **📄 Structured Documents**
        - Reports
        - Lists
        - Key-value pairs
        """)
    
    with col3:
        st.markdown("""
        **🖼️ Scanned Documents**
        - Scanned PDFs
        - Image-based PDFs
        - Handwritten text (limited)
        """)
