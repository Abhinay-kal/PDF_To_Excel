import cv2
import numpy as np
from pdf2image import convert_from_path
import pytesseract
import pandas as pd
import re
import os

# --- 1. PRE-PROCESSING ---
def preprocess_page(image_pil):
    img = cv2.cvtColor(np.array(image_pil), cv2.COLOR_RGB2BGR)
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    thresh = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)[1]
    return thresh, img

# --- 2. GRID DETECTION ---
def detect_grid(thresh_img):
    horizontal_scale = 35
    vertical_scale = 35
    v_len = thresh_img.shape[0] // vertical_scale
    h_len = thresh_img.shape[1] // horizontal_scale
    
    ver_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (1, v_len))
    hor_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (h_len, 1))
    
    vertical_lines = cv2.morphologyEx(thresh_img, cv2.MORPH_OPEN, ver_kernel, iterations=2)
    horizontal_lines = cv2.morphologyEx(thresh_img, cv2.MORPH_OPEN, hor_kernel, iterations=2)
    
    grid_mask = cv2.addWeighted(vertical_lines, 0.5, horizontal_lines, 0.5, 0.0)
    grid_mask = cv2.dilate(grid_mask, cv2.getStructuringElement(cv2.MORPH_RECT, (2, 2)), iterations=1)
    
    _, grid_mask = cv2.threshold(grid_mask, 0, 255, cv2.THRESH_BINARY)
    return grid_mask

# --- 3. SORTING ---
def sort_contours(contours):
    bounding_boxes = [cv2.boundingRect(c) for c in contours]
    if not contours: return []
    
    cnts_boxes = sorted(zip(contours, bounding_boxes), key=lambda b: b[1][1])
    
    final_sorted_contours = []
    rows = []
    current_row = []
    last_y = 0
    row_threshold = 50
    
    for i, (cnt, box) in enumerate(cnts_boxes):
        x, y, w, h = box
        if i == 0:
            current_row.append((cnt, box))
            last_y = y
        else:
            if abs(y - last_y) <= row_threshold:
                current_row.append((cnt, box))
            else:
                current_row.sort(key=lambda b: b[1][0])
                rows.append(current_row)
                current_row = [(cnt, box)]
                last_y = y
                
    if current_row:
        current_row.sort(key=lambda b: b[1][0])
        rows.append(current_row)
    
    for row in rows:
        for item in row:
            final_sorted_contours.append(item[0])
            
    return final_sorted_contours

def get_voter_boxes(grid_mask, original_img_shape):
    contours, _ = cv2.findContours(grid_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    valid_contours = []
    img_h, img_w = original_img_shape[:2]
    min_width = img_w * 0.20 
    
    for c in contours:
        x, y, w, h = cv2.boundingRect(c)
        if w > min_width and h > 50 and w < (img_w * 0.9):
            valid_contours.append(c)
            
    return sort_contours(valid_contours)

# --- 4. PARSING & CLEANING (UPDATED) ---
def clean_typos(data):
    """
    Step 3: Fix common OCR errors and standardize data.
    """
    # Fix Gender Typos
    gender = data["Gender"].lower().strip()
    if gender in ["mala", "maie", "mle", "rnale", "male."]:
        data["Gender"] = "Male"
    elif gender in ["femala", "femaie", "fermale", "fernale", "female."]:
        data["Gender"] = "Female"
        
    # Fix ID Typos (Remove spaces, confusing chars)
    if data["ID"]:
        data["ID"] = data["ID"].replace(" ", "").replace("$", "S").replace("O", "0")
        # Heuristic: If ID starts with letters but ends with 'O' instead of '0', fix it
        # Example: SMV123456O -> SMV1234560
    
    return data

def validate_entry(data):
    """
    Step 3 Validation: Flag rows that are missing critical info.
    """
    status = []
    
    if not data["Name"] or len(data["Name"]) < 3:
        status.append("Missing Name")
    
    if not data["Age"]:
        status.append("Missing Age")
        
    if not data["ID"]:
        status.append("Missing ID")
        
    if not status:
        return "OK"
    else:
        return "REVIEW: " + ", ".join(status)

def parse_voter_data(text):
    # A. Noise Cleaning
    clean_text = text.replace("*", "").replace("?", "").replace("!", "").replace("'", "").replace('"', "")
    clean_text = clean_text.replace("Narne", "Name").replace("Nare", "Name")
    
    data = {"Name": "", "Relation": "", "HouseNo": "", "Age": "", "Gender": "", "ID": "", "Status": ""}
    
    # B. Regex Extraction
    id_match = re.search(r'([A-Z]{3}\d{7})', clean_text)
    if id_match: data["ID"] = id_match.group(1)

    hn_match = re.search(r'House\s*Number\s*[:\-\.]\s*([0-9A-Za-z\-/]+)', clean_text, re.IGNORECASE)
    if hn_match: data["HouseNo"] = hn_match.group(1)

    age_match = re.search(r'Age\s*[:\-\.]\s*(\d+)', clean_text, re.IGNORECASE)
    if age_match: data["Age"] = age_match.group(1)
        
    gender_match = re.search(r'Gender\s*[:\-\.]\s*([A-Za-z]+)', clean_text, re.IGNORECASE)
    if gender_match: data["Gender"] = gender_match.group(1)

    # C. Name/Relation Line Scan
    lines = [line.strip() for line in clean_text.split('\n') if line.strip()]
    for line in lines:
        if any(x in line for x in ["House Number", "Age:", "Gender:", "Photo", "Available"]):
            continue
            
        if any(x in line for x in ["Father", "Husband", "Mother", "Other"]):
            parts = re.split(r'[:\-]', line, 1)
            if len(parts) > 1:
                rel_type = parts[0].strip()
                rel_name = parts[1].strip()
                data["Relation"] = f"{rel_type}: {rel_name}"
        
        elif "Name" in line or "Name:" in line:
            parts = re.split(r'[:\-]', line, 1)
            if len(parts) > 1:
                data["Name"] = parts[1].strip()
        else:
            if not data["Name"] and len(line) > 3 and not re.search(r'\d', line):
                data["Name"] = line

    # D. Apply Cleaning & Validation
    data = clean_typos(data)
    data["Status"] = validate_entry(data)
    
    return data

# --- 5. MAIN PROCESS ---
def process_pdf(pdf_path, progress_bar=None):
    all_voters = []
    try:
        images = convert_from_path(pdf_path)
    except Exception as e:
        return f"Error: {e}"

    total = len(images)
    for i, img_pil in enumerate(images):
        if progress_bar:
            progress_bar.progress((i + 1) / total, text=f"Scanning Page {i+1}/{total}...")

        processed_img, original_img = preprocess_page(img_pil)
        grid_only = detect_grid(processed_img)
        boxes = get_voter_boxes(grid_only, original_img.shape)
        
        for box in boxes:
            x, y, w, h = cv2.boundingRect(box)
            roi = original_img[y:y+h, x:x+w]
            text = pytesseract.image_to_string(roi, config='--psm 6')
            info = parse_voter_data(text)
            
            # Save valid entries
            if info["Name"] or info["ID"]:
                all_voters.append(info)
                
    return pd.DataFrame(all_voters)

if __name__ == "__main__":
    TEST_PDF = "page 4 Goa (1).pdf"
    if os.path.exists(TEST_PDF):
        print("Running Test with Cleaning & Validation...")
        df = process_pdf(TEST_PDF)
        df.to_excel("Cleaned_Voter_List.xlsx", index=False)
        print("Done! Saved 'Cleaned_Voter_List.xlsx'")
        print(df[["Name", "Gender", "Status"]].head(10))