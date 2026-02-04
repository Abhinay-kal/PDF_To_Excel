import cv2
import numpy as np
from pdf2image import convert_from_path
import pytesseract
import pandas as pd
import re
import os

# --- 1. PRE-PROCESSING ---
def preprocess_page(image_pil):
    # Convert to OpenCV
    img = cv2.cvtColor(np.array(image_pil), cv2.COLOR_RGB2BGR)
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    
    # Threshold to get black text on white background
    thresh = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)[1]
    
    return thresh, img

# --- 2. BLOB DETECTION (The New Strategy) ---
def get_text_blobs(thresh_img, original_img):
    img_h, img_w = original_img.shape[:2]
    
    # A. DILATION (The Magic Step)
    # We smear the text. 
    # (25, 15) kernel means: connect things that are 25px apart horizontally
    # and 15px apart vertically. This merges Name+ID+Photo into one block.
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (25, 15))
    dilated = cv2.dilate(thresh_img, kernel, iterations=1)
    
    # B. Find Contours of these "Blobs"
    contours, _ = cv2.findContours(dilated, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    
    valid_boxes = []
    
    # C. Filter Logic
    # A voter card is roughly 1/3rd width and 1/10th height
    min_w = img_w * 0.20  # Min 20% width
    max_w = img_w * 0.40  # Max 40% width (don't pick up full rows)
    min_h = 50            # Min height
    
    for c in contours:
        x, y, w, h = cv2.boundingRect(c)
        
        if w > min_w and w < max_w and h > min_h:
            valid_boxes.append((x, y, w, h))
            
    # D. Sort (Top-Bottom, Left-Right)
    # We sort by Y first (with a tolerance of 20px to group rows)
    boxes = sorted(valid_boxes, key=lambda b: (b[1] // 50, b[0]))
    
    return boxes

# --- 3. PARSING ---
def clean_typos(data):
    if data["Gender"]:
        g = data["Gender"].lower()
        if "fem" in g: data["Gender"] = "Female"
        elif "mal" in g: data["Gender"] = "Male"
    if data["ID"]:
        data["ID"] = data["ID"].replace(" ", "").replace("$", "S").replace("O", "0")
    return data

def parse_voter_data(text):
    text = text.replace("*", "").replace("?", "").replace("!", "").replace("'", "")
    data = {"Name": "", "Relation": "", "HouseNo": "", "Age": "", "Gender": "", "ID": ""}
    
    # Regex Patterns
    id_match = re.search(r'([A-Z]{3}\d{7})', text)
    if id_match: data["ID"] = id_match.group(1)

    hn_match = re.search(r'House\s*Number\s*[:\-\.]\s*([0-9A-Za-z\-/]+)', text, re.IGNORECASE)
    if hn_match: data["HouseNo"] = hn_match.group(1)

    age_match = re.search(r'Age\s*[:\-\.]\s*(\d+)', text, re.IGNORECASE)
    if age_match: data["Age"] = age_match.group(1)
        
    gender_match = re.search(r'Gender\s*[:\-\.]\s*([A-Za-z]+)', text, re.IGNORECASE)
    if gender_match: data["Gender"] = gender_match.group(1)

    # Line Parsing
    lines = [line.strip() for line in text.split('\n') if line.strip()]
    for line in lines:
        if any(x in line for x in ["House Number", "Age:", "Gender:", "ID:", "Photo", "Available"]):
            continue
            
        if any(x in line for x in ["Father", "Husband", "Mother", "Other"]):
            parts = re.split(r'[:\-]', line, 1)
            if len(parts) > 1:
                data["Relation"] = f"{parts[0].strip()}: {parts[1].strip()}"
        elif "Name" in line or "Name:" in line:
            parts = re.split(r'[:\-]', line, 1)
            if len(parts) > 1:
                data["Name"] = parts[1].strip()
        elif not data["Name"] and len(line) > 3 and not re.search(r'\d', line):
            if "Avail" not in line and "Delet" not in line:
                data["Name"] = line

    return clean_typos(data)

# --- 4. MAIN PROCESS ---
def process_pdf(pdf_path, progress_bar=None):
    all_voters = []
    try:
        images = convert_from_path(pdf_path)
    except Exception as e:
        return f"Error: {e}"

    for i, img_pil in enumerate(images):
        thresh, original_img = preprocess_page(img_pil)
        
        # USE BLOB DETECTION
        boxes = get_text_blobs(thresh, original_img)
        
        for box in boxes:
            x, y, w, h = box
            # Add padding to ensure we don't clip text
            roi = original_img[y-5:y+h+5, x-5:x+w+5]
            
            # Safe crop check
            if roi.size == 0: continue
            
            text = pytesseract.image_to_string(roi, config='--psm 6')
            info = parse_voter_data(text)
            
            if info["Name"] or info["ID"]:
                all_voters.append(info)
                
    return pd.DataFrame(all_voters)

# --- DEBUG & RUN ---
if __name__ == "__main__":
    TEST_PDF = "goa.pdf" 
    
    print(f"🚀 Running Blob Detection on {TEST_PDF}...")
    if os.path.exists(TEST_PDF):
        
        # 1. VISUAL CHECK
        pages = convert_from_path(TEST_PDF, first_page=1, last_page=1)
        thresh, img = preprocess_page(pages[0])
        boxes = get_text_blobs(thresh, img)
        
        print(f"Found {len(boxes)} text blobs.")
        
        # Draw the blobs to a file so you can see what it found
        debug_img = img.copy()
        for i, (x, y, w, h) in enumerate(boxes):
            cv2.rectangle(debug_img, (x, y), (x+w, y+h), (0, 0, 255), 2)
            cv2.putText(debug_img, str(i+1), (x, y), cv2.FONT_HERSHEY_SIMPLEX, 1, (0,0,255), 2)
            
        cv2.imwrite("debug_blobs.jpg", debug_img)
        print("📸 Check 'debug_blobs.jpg' - You should see red boxes around every voter.")
        
        # 2. RUN EXTRACTION
        df = process_pdf(TEST_PDF)
        if not df.empty:
            print(f"✅ Success! Extracted {len(df)} voters.")
            print(df.head())
            df.to_excel("Final_Blob_Output.xlsx", index=False)
        else:
            print("❌ Still no voters found. Check debug_blobs.jpg to see if boxes are correct.")
    else:
        print("File not found.")