import cv2
import numpy as np
from pdf2image import convert_from_path
import pytesseract
import pandas as pd
import re
import os

# --- 1. SIMPLE PRE-PROCESSING ---
def get_vertical_strips(image_pil):
    # 1. High DPI Conversion happen at load time, here we just convert to array
    img = cv2.cvtColor(np.array(image_pil), cv2.COLOR_RGB2BGR)
    
    # 2. Grayscale only (NO Thresholding - this fixes the "0 blobs" issue)
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    
    img_h, img_w = gray.shape
    col_w = img_w // 3
    
    # 3. Blind Slice into 3 vertical strips
    # We add 10px overlap to ensure we don't cut a letter in half
    strip_1 = gray[0:img_h, 0 : col_w + 10]
    strip_2 = gray[0:img_h, col_w - 10 : col_w * 2 + 10]
    strip_3 = gray[0:img_h, col_w * 2 - 10 : img_w]
    
    return [strip_1, strip_2, strip_3]

# --- 2. ROBUST PARSING ---
def parse_raw_text_block(text):
    """
    Splits a long string of text into voter chunks using the ID as a separator.
    """
    voters = []
    
    # Regex to find Voter IDs (Start of a new record)
    # Matches: 3 Letters + 7 Digits (e.g., SMV0334946)
    # We use capturing group () to keep the ID in the split list
    split_data = re.split(r'([A-Z]{3}\d{7})', text)
    
    # split_data will look like: [trash, ID_1, Data_1, ID_2, Data_2, ...]
    # We step through 2 items at a time
    for i in range(1, len(split_data) - 1, 2):
        v_id = split_data[i].strip()
        v_data = split_data[i+1].strip()
        
        # Parse the inner data
        info = extract_details(v_id, v_data)
        if info["Name"]: # Validity Check
            voters.append(info)
            
    return voters

def extract_details(v_id, text):
    data = {"ID": v_id, "Name": "", "Relation": "", "HouseNo": "", "Age": "", "Gender": ""}
    
    # Clean noise
    text = text.replace("|", "").replace("!", "").replace("'", "")
    
    # 1. House Number
    hn = re.search(r'House\s*Number\s*[:\-\.]\s*([0-9A-Za-z\-/]+)', text, re.IGNORECASE)
    if hn: data["HouseNo"] = hn.group(1)
    
    # 2. Age & Gender
    age = re.search(r'Age\s*[:\-\.]\s*(\d+)', text, re.IGNORECASE)
    if age: data["Age"] = age.group(1)
    
    gen = re.search(r'Gender\s*[:\-\.]\s*([A-Za-z]+)', text, re.IGNORECASE)
    if gen: 
        g = gen.group(1).lower()
        data["Gender"] = "Male" if "mal" in g and "fe" not in g else "Female"

    # 3. Name & Relation
    lines = [line.strip() for line in text.split('\n') if line.strip()]
    for line in lines:
        if any(x in line for x in ["House Number", "Age:", "Gender:", "Photo", "Avail", "Delet"]):
            continue
            
        # Relation (Father/Husband/Mother)
        if any(x in line for x in ["Father", "Husband", "Mother", "Other"]):
            parts = re.split(r'[:\-]', line, 1)
            if len(parts) > 1:
                data["Relation"] = f"{parts[0].strip()}: {parts[1].strip()}"
        
        # Name (Look for "Name:" OR assume first line without numbers is Name)
        elif not data["Name"]:
            if "Name" in line or "Narne" in line:
                parts = re.split(r'[:\-]', line, 1)
                if len(parts) > 1: data["Name"] = parts[1].strip()
            # Fallback: First generic text line is usually the Name
            elif len(line) > 3 and not re.search(r'\d', line):
                data["Name"] = line
                
    return data

# --- 3. MAIN PROCESS ---
def process_pdf(pdf_path, progress_bar=None):
    all_voters = []
    try:
        # CRITICAL: dpi=300 ensures small text is readable
        images = convert_from_path(pdf_path, dpi=300)
    except Exception as e:
        return f"Error: {e}"

    total = len(images)
    for i, img_pil in enumerate(images):
        if progress_bar:
            progress_bar.progress((i + 1) / total, text=f"Reading Page {i+1}/{total}...")

        # 1. Get 3 vertical strips (Raw Grayscale)
        strips = get_vertical_strips(img_pil)
        
        # 2. Process each strip
        for strip in strips:
            # --psm 6 is "Assume a single uniform block of text"
            raw_text = pytesseract.image_to_string(strip, config='--psm 6')
            
            # 3. Mine data
            voters = parse_raw_text_block(raw_text)
            all_voters.extend(voters)
                
    return pd.DataFrame(all_voters)

# --- DEBUG RUNNER ---
if __name__ == "__main__":
    TEST_PDF = "goa.pdf"
    if os.path.exists(TEST_PDF):
        print("🚀 Running Brute Force Stream Method...")
        df = process_pdf(TEST_PDF)
        
        if not df.empty:
            print(f"✅ Success! Found {len(df)} voters.")
            print(df.head(10))
            df.to_excel("Final_BruteForce_Output.xlsx", index=False)
        else:
            print("❌ No data found. Tesseract output was empty.")
            # Debug: Check one strip text
            print("   Running diagnostic on first page...")
            images = convert_from_path(TEST_PDF, dpi=300, first_page=1, last_page=1)
            strips = get_vertical_strips(images[0])
            txt = pytesseract.image_to_string(strips[0], config='--psm 6')
            print(f"   --- RAW TEXT SAMPLE ---\n{txt[:500]}\n   -----------------------")
    else:
        print("File 'goa.pdf' not found.")