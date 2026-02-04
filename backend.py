import cv2
import numpy as np
from pdf2image import convert_from_path
import pytesseract
import pandas as pd
import re
import os

# --- 1. PRE-PROCESSING ---
def get_vertical_strips(image_pil):
    img = cv2.cvtColor(np.array(image_pil), cv2.COLOR_RGB2BGR)
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    
    img_h, img_w = gray.shape
    col_w = img_w // 3
    
    # Slice 3 vertical strips with overlap
    strips = [
        gray[0:img_h, 0 : col_w + 10],
        gray[0:img_h, col_w - 10 : col_w * 2 + 10],
        gray[0:img_h, col_w * 2 - 10 : img_w]
    ]
    return strips

# --- 2. TEXT CLEANING ---
def clean_id(text):
    # 1. Remove noise chars but keep spaces for now
    text = text.upper()
    
    # 2. Fix common OCR digits-as-letters
    # Only replace O with 0 if it looks like the numeric part of an ID
    # (Simple approach: just replace all for ID candidate)
    clean = text.replace('$', 'S').replace('O', '0').replace('I', '1').replace('B', '8')
    
    # 3. Strip everything except A-Z and 0-9
    clean = re.sub(r'[^A-Z0-9]', '', clean)
    return clean

def clean_typos(data):
    if data["Gender"]:
        g = data["Gender"].lower()
        if "fem" in g: data["Gender"] = "Female"
        elif "mal" in g: data["Gender"] = "Male"
    return data

# --- 3. PARSING LOGIC ---
def parse_strip_text(text):
    lines = [line.strip() for line in text.split('\n') if line.strip()]
    
    voters = []
    current_voter = {}
    
    for i, line in enumerate(lines):
        # DETECT NAME (Anchor)
        # Regex explanation:
        # (Name|Narne|Nane) -> Matches common OCR typos
        # [\W_]* -> Matches any garbage symbols like ' * ' or ' ? '
        # [:\-\.|] -> Matches the separator
        if re.match(r'(Name|Narne|Nane|Mame)[\W_]*[:\-\.|]', line, re.IGNORECASE):
            
            # Save previous voter
            if current_voter and current_voter.get("Name"):
                current_voter = clean_typos(current_voter)
                voters.append(current_voter)
            
            current_voter = {
                "Name": "", "Relation": "", "HouseNo": "", 
                "Age": "", "Gender": "", "ID": "UNREAD_ID"
            }
            
            # Extract Name
            # Use maxsplit=1 to avoid splitting on names that contain ':'
            parts = re.split(r'[:\-\.|]', line, maxsplit=1)
            if len(parts) > 1:
                current_voter["Name"] = parts[1].strip()
            
            # HUNT FOR ID (Look Backwards)
            # We look back up to 6 lines to find the ID
            for back_idx in range(1, 7): 
                if i - back_idx >= 0:
                    prev_line = lines[i - back_idx]
                    
                    # Skip common trash lines
                    if any(x in prev_line for x in ["Avail", "Delet", "Photo", "Sect", "Assem", "Part"]):
                        continue
                        
                    # Candidate Cleaning
                    clean_cand = clean_id(prev_line)
                    
                    # Logic: Standard ID is 10 chars (3 Letters + 7 Numbers)
                    # We accept 7-12 chars to be safe
                    if 7 <= len(clean_cand) <= 12:
                        # Strong signal: Starts with letters, ends with numbers
                        # Or just a good length mix
                        if re.match(r'^[A-Z]{3}', clean_cand):
                            current_voter["ID"] = clean_cand
                            break # Found it, stop looking

        elif current_voter:
            # RELATION
            if any(x in line for x in ["Father", "Husband", "Mother", "Other"]):
                parts = re.split(r'[:\-\.|]', line, maxsplit=1)
                if len(parts) > 1:
                    current_voter["Relation"] = f"{parts[0].strip()}: {parts[1].strip()}"
            
            # HOUSE NUMBER
            elif "House Number" in line:
                hn_match = re.search(r'Number\s*[:\-\.|]\s*([0-9A-Za-z\-/]+)', line, re.IGNORECASE)
                if hn_match:
                    current_voter["HouseNo"] = hn_match.group(1)
            
            # AGE & GENDER
            elif "Age" in line or "Gender" in line:
                age_match = re.search(r'Age\s*[:\-\.|]\s*(\d+)', line, re.IGNORECASE)
                if age_match: current_voter["Age"] = age_match.group(1)
                
                gen_match = re.search(r'Gender\s*[:\-\.|]\s*([A-Za-z]+)', line, re.IGNORECASE)
                if gen_match: current_voter["Gender"] = gen_match.group(1)

    # Save last voter
    if current_voter and current_voter.get("Name"):
        current_voter = clean_typos(current_voter)
        voters.append(current_voter)
        
    return voters

# --- 4. MAIN PROCESS ---
def process_pdf(pdf_path, progress_bar=None):
    all_voters = []
    try:
        images = convert_from_path(pdf_path, dpi=300)
    except Exception as e:
        return f"Error: {e}"

    total = len(images)
    for i, img_pil in enumerate(images):
        if progress_bar:
            progress_bar.progress((i + 1) / total, text=f"Processing Page {i+1}...")

        strips = get_vertical_strips(img_pil)
        
        for strip in strips:
            text = pytesseract.image_to_string(strip, config='--psm 6')
            voters = parse_strip_text(text)
            all_voters.extend(voters)
                
    return pd.DataFrame(all_voters)

if __name__ == "__main__":
    TEST_PDF = "goa.pdf"
    if os.path.exists(TEST_PDF):
        print("🚀 Running Final Polished Method...")
        df = process_pdf(TEST_PDF)
        
        if not df.empty:
            print(f"✅ Success! Extracted {len(df)} voters.")
            print(df[["ID", "Name", "Age"]].head(10))
            df.to_excel("Final_Clean_Output.xlsx", index=False)
        else:
            print("❌ No data found.")
    else:
        print("File not found.")