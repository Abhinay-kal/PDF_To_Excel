import streamlit as st
import pandas as pd
import numpy as np
import cv2
import pytesseract
import re
import os
import io
from pdf2image import convert_from_path

# --- PAGE CONFIG ---
st.set_page_config(page_title="Voter Roll Digitizer (Grid Slicer)", page_icon="✂️", layout="wide")
st.markdown("""
<style>
    .stButton>button { width: 100%; background-color: #007BFF; color: white; font-weight: bold; }
</style>
""", unsafe_allow_html=True)

# ==========================================
#        CORE LOGIC: PROJECTION SLICING
# ==========================================

def preprocess_image(image_pil):
    """Converts to grayscale and applies thresholding for gap detection."""
    img = cv2.cvtColor(np.array(image_pil), cv2.COLOR_RGB2BGR)
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    # Binary inverse: Text becomes white, background black (easier to count pixels)
    _, thresh = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
    return img, gray, thresh

def find_gaps(projection, threshold_ratio=0.01):
    """Finds the start and end indices of white space gaps."""
    # A 'gap' is where the pixel count is very low (near zero)
    # We use a small threshold because scans aren't perfectly clean
    threshold = np.max(projection) * threshold_ratio
    gaps = []
    is_gap = False
    start = 0
    
    for i, val in enumerate(projection):
        if val < threshold and not is_gap:
            is_gap = True
            start = i
        elif val >= threshold and is_gap:
            is_gap = False
            # Only keep gaps wider than 5 pixels to avoid noise
            if i - start > 5:
                gaps.append((start, i))
    
    # Handle edge case: gap at the very end
    if is_gap:
        gaps.append((start, len(projection)))
        
    return gaps

def get_smart_cells(img, gray, thresh):
    """
    Intelligently slices the page into voter cells using Projection Profiles.
    """
    img_h, img_w = thresh.shape
    
    # 1. HORIZONTAL PROJECTION (Sum of pixels in each row)
    # We reduce the image to a single vertical line of counts
    h_proj = np.sum(thresh, axis=1)
    
    # Find gaps (The white space between rows of voters)
    row_gaps = find_gaps(h_proj, threshold_ratio=0.02)
    
    # Use gaps to define Row Coordinates
    # We want the content BETWEEN the gaps
    rows = []
    if not row_gaps:
        # Fallback: Just slice evenly if detection fails
        row_h = img_h // 10
        for i in range(10): rows.append((i*row_h, (i+1)*row_h))
    else:
        # Convert gaps to content regions
        # If gap 1 ends at A and gap 2 starts at B, content is A to B
        for i in range(len(row_gaps) - 1):
            y1 = row_gaps[i][1]
            y2 = row_gaps[i+1][0]
            # Filter small noise rows (headers/footers usually < 40px)
            if y2 - y1 > 50: 
                rows.append((y1, y2))

    cells = []
    
    # 2. VERTICAL PROJECTION (For each row, find columns)
    for y1, y2 in rows:
        row_slice = thresh[y1:y2, :]
        v_proj = np.sum(row_slice, axis=0)
        
        col_gaps = find_gaps(v_proj, threshold_ratio=0.02)
        
        # We expect 3 columns. If we find roughly 3 regions, use them.
        cols = []
        if len(col_gaps) >= 2:
             for i in range(len(col_gaps) - 1):
                x1 = col_gaps[i][1]
                x2 = col_gaps[i+1][0]
                if x2 - x1 > 50: # Filter skinny noise
                    cols.append((x1, x2))
        
        # Fallback: If we couldn't find clear gaps, slice evenly into 3
        if len(cols) != 3:
            cols = []
            col_w = img_w // 3
            cols.append((0, col_w))
            cols.append((col_w, col_w*2))
            cols.append((col_w*2, img_w))
            
        # 3. EXTRACT CELLS
        for x1, x2 in cols:
            # Crop the cell from the GRAY image (better for OCR than binary)
            # Add small padding (5px) to ensure we don't cut letters
            cell = gray[y1:y2, x1:x2]
            cells.append(cell)
            
    return cells

def clean_text(text):
    text = text.replace("|", "").replace("!", "").replace("'", "").replace("—", "-")
    # Remove 'Deleted' stamp noise
    text = re.sub(r'(DELETED|Delet|Avail|Photo)', '', text, flags=re.IGNORECASE)
    return text

def parse_cell_data(text):
    """
    Parses a single voter cell. 
    Since the cell is ISOLATED, we can trust line positions more.
    """
    text = clean_text(text)
    data = {"ID": "UNREAD", "Name": "", "Relation": "", "HouseNo": "", "Age": "", "Gender": ""}
    
    # Regex Patterns
    # ID: 3 Letters + 7 Digits (or similar)
    id_match = re.search(r'([A-Z]{2,4}[\sO0-9]{6,10})', text)
    if id_match:
        raw_id = id_match.group(1).replace(' ', '').replace('O', '0')
        # Filter: Must be mostly alphanumeric and > 6 chars
        if len(raw_id) > 6 and any(c.isdigit() for c in raw_id):
            data["ID"] = raw_id

    # House Number
    hn_match = re.search(r'No\s*[:\-\.]\s*([0-9A-Za-z\-/]+)', text, re.IGNORECASE)
    if hn_match: data["HouseNo"] = hn_match.group(1)

    # Age & Gender
    age_match = re.search(r'Age\s*[:\-\.]\s*(\d+)', text, re.IGNORECASE)
    if age_match: data["Age"] = age_match.group(1)
    
    gen_match = re.search(r'Gender\s*[:\-\.]\s*([A-Za-z]+)', text, re.IGNORECASE)
    if gen_match: 
        g = gen_match.group(1).lower()
        data["Gender"] = "Male" if "mal" in g else "Female"

    # Name Strategy:
    # Look for "Name:" prefix. If not found, assume the first long line is the Name.
    lines = [l.strip() for l in text.split('\n') if len(l.strip()) > 3]
    
    # Remove ID line if it was first
    if lines and data["ID"] in lines[0].replace(' ',''):
        lines.pop(0)

    for line in lines:
        if "Name" in line and ":" in line:
            parts = line.split(":", 1)
            if len(parts) > 1: data["Name"] = parts[1].strip()
            break
        elif any(x in line for x in ["Father", "Husband", "Mother"]):
             parts = re.split(r'[:\-]', line, 1)
             if len(parts) > 1:
                 data["Relation"] = f"{parts[0].strip()}: {parts[1].strip()}"
    
    # Fallback Name: Use first valid line if we didn't find "Name:"
    if not data["Name"] and lines:
        for line in lines:
            # Skip lines that look like attributes
            if not any(x in line for x in ["House", "Age", "Gender", "Father", "Mother", "Husband", "Num"]):
                data["Name"] = line
                break
                
    return data

def process_pdf(pdf_path, progress_bar=None):
    all_voters = []
    try:
        # DPI 300 is optimal for speed/accuracy balance
        images = convert_from_path(pdf_path, dpi=300)
    except Exception as e:
        st.error(f"Error reading PDF: {e}")
        return pd.DataFrame()

    total = len(images)
    for i, img_pil in enumerate(images):
        if progress_bar: progress_bar.progress((i + 1) / total, text=f"Slicing Page {i+1}...")
        
        # 1. Preprocess
        img, gray, thresh = preprocess_image(img_pil)
        
        # 2. Smart Slicing
        cells = get_smart_cells(img, gray, thresh)
        
        # 3. OCR Each Cell
        for cell in cells:
            # Check if cell is empty (white space)
            if np.mean(cell) > 250: continue
            
            # OCR
            text = pytesseract.image_to_string(cell, config='--psm 6')
            voter = parse_cell_data(text)
            
            # Filter Noise (Must have at least ID or Name)
            if voter["Name"] or (voter["ID"] != "UNREAD"):
                all_voters.append(voter)
                
    return pd.DataFrame(all_voters)

# ==========================================
#        UI FRONTEND
# ==========================================

st.title("✂️ Smart Grid Slicer")
st.markdown("### The 'Gap Detection' Method")
st.info("This method detects the WHITE SPACE between voters to slice the page, ignoring broken lines and skewed text.")

uploaded_file = st.file_uploader("Upload PDF", type=["pdf"])

if uploaded_file:
    temp_path = f"temp_{uploaded_file.name}"
    with open(temp_path, "wb") as f: f.write(uploaded_file.getbuffer())
    
    if st.button("🚀 Start Slicing Engine"):
        bar = st.progress(0, text="Initializing...")
        df = process_pdf(temp_path, bar)
        bar.empty()
        
        if os.path.exists(temp_path): os.remove(temp_path)

        if not df.empty:
            st.success(f"✅ Extracted {len(df)} voters!")
            
            c1, c2, c3 = st.columns(3)
            c1.metric("Count", len(df))
            c2.metric("IDs Found", len(df[df['ID'] != 'UNREAD']))
            c3.metric("Missing IDs", len(df[df['ID'] == 'UNREAD']))
            
            st.dataframe(df.head(10), use_container_width=True)

            buffer = io.BytesIO()
            with pd.ExcelWriter(buffer, engine='xlsxwriter') as writer:
                df.to_excel(writer, index=False, sheet_name='Voters')
            buffer.seek(0)
            
            st.download_button("📥 Download Excel", buffer, "Final_Smart_Slice.xlsx")
        else:
            st.error("No data found.")