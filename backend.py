import cv2
import numpy as np
from pdf2image import convert_from_path
import pytesseract
import pandas as pd
import re
import os

# --- 1. PRE-PROCESSING (No changes) ---
def get_vertical_strips(image_pil):
    img = cv2.cvtColor(np.array(image_pil), cv2.COLOR_RGB2BGR)
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    
    img_h, img_w = gray.shape
    col_w = img_w // 3
    
    # 3 strips with slight overlap
    strips = [
        gray[0:img_h, 0 : col_w + 10],
        gray[0:img_h, col_w - 10 : col_w * 2 + 10],
        gray[0:img_h, col_w * 2 - 10 : img_w]
    ]
    return strips

# --- 2. STATE MACHINE PARSING (New Strategy) ---
def clean_id(text):
    # Try to fix garbled IDs like 'svos40ass'
    # 1. Remove non-alphanumeric
    clean = re.sub(r'[^A-Z0-9]', '', text.upper())
    # 2. Hard fixes for common OCR mistakes
    clean = clean.replace('$', 'S').replace('O', '0')
    return clean

def parse_strip_text(text):
    lines = [line.strip() for line in text.split('\n') if line.strip()]
    
    voters = []
    current_voter = {}
    
    # Buffer to look backwards for ID
    line_buffer = []
    
    for i, line in enumerate(lines):
        # DETECT NEW VOTER (Anchor: "Name :" or "Narne :")
        if re.match(r'(Name|Narne)\s*[:\-\.|]', line, re.IGNORECASE):
            
            # 1. Save Previous Voter (if exists)
            if current_voter and current_voter.get("Name"):
                voters.append(current_voter)
            
            # 2. Start New Voter
            current_voter = {
                "Name": "", "Relation": "", "HouseNo": "", 
                "Age": "", "Gender": "", "ID": ""
            }
            
            # 3. Extract Name
            # Split by separator to get the name part
            parts = re.split(r'[:\-\.|]', line, 1)
            if len(parts) > 1:
                current_voter["Name"] = parts[1].strip()
            
            # 4. HUNT FOR ID (Look Backwards 1-3 lines)
            # The ID usually sits just above the Name or after "Available"
            # We look for a "short alphanumeric string" (e.g., svos40ass)
            found_id = False
            for back_idx in range(1, 5): # Look back 4 lines
                if i - back_idx >= 0:
                    prev_line = lines[i - back_idx]
                    
                    # Ignore "Available", "Deleted", "Photo", "Section"
                    if any(x in prev_line for x in ["Avail", "Delet", "Photo", "Sect", "Assem"]):
                        continue
                        
                    # Candidate check: Short string (5-12 chars), contains digits
                    # Example: "SMV0410241" or "svos40ass"
                    clean_cand = clean_id(prev_line)
                    if 5 <= len(clean_cand) <= 12 and any(c.isdigit() for c in clean_cand):
                        current_voter["ID"] = clean_cand
                        found_id = True
                        break
            
            # If still no ID, mark as "Unknown" (Don't skip the voter!)
            if not current_voter.get("ID"):
                current_voter["ID"] = "UNREAD_ID"

        # DETECT ATTRIBUTES (If we are inside a voter block)
        elif current_voter:
            # RELATION
            if any(x in line for x in ["Father", "Husband", "Mother", "Other"]):
                parts = re.split(r'[:\-\.|]', line, 1)
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
                if gen_match:
                    g = gen_match.group(1).lower()
                    if "mal" in g and "fe" not in g: current_voter["Gender"] = "Male"
                    elif "fe" in g: current_voter["Gender"] = "Female"

    # Append the very last voter
    if current_voter and current_voter.get("Name"):
        voters.append(current_voter)
        
    return voters

# --- 3. MAIN PROCESS ---
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
            # Raw OCR (psm 6 is best for columns)
            text = pytesseract.image_to_string(strip, config='--psm 6')
            
            # Parse line-by-line
            voters = parse_strip_text(text)
            all_voters.extend(voters)
                
    return pd.DataFrame(all_voters)

if __name__ == "__main__":
    TEST_PDF = "goa.pdf"
    if os.path.exists(TEST_PDF):
        print("🚀 Running Name-Anchor Method...")
        df = process_pdf(TEST_PDF)
        
        if not df.empty:
            print(f"✅ Success! Extracted {len(df)} voters.")
            print(df.head(10))
            df.to_excel("Final_Output.xlsx", index=False)
        else:
            print("❌ Still no data. Showing raw text from first strip:")
            images = convert_from_path(TEST_PDF, dpi=300, first_page=1, last_page=1)
            strips = get_vertical_strips(images[0])
            print(pytesseract.image_to_string(strips[0], config='--psm 6')[:500])