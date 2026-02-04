# backend.py
import cv2
import numpy as np
import pytesseract
import pandas as pd
from pdf2image import convert_from_path
import re

def parse_voter_text(text):
    """
    Regex logic to extract data from raw OCR text.
    """
    # Regex patterns based on the Goa voter roll format
    data = {}
    
    # 1. Voter ID (e.g., SMV0334946)
    id_match = re.search(r'([A-Z]{3}\d{7})', text)
    data['VoterID'] = id_match.group(1) if id_match else "N/A"
    
    # 2. House Number
    house_match = re.search(r'House\s*Number\s*[:\-\.]\s*([0-9A-Za-z\-/]+)', text, re.IGNORECASE)
    data['HouseNo'] = house_match.group(1) if house_match else ""
    
    # 3. Age & Gender
    age_match = re.search(r'Age\s*[:\-\.]\s*(\d+)', text, re.IGNORECASE)
    gender_match = re.search(r'Gender\s*[:\-\.]\s*(Male|Female)', text, re.IGNORECASE)
    
    data['Age'] = age_match.group(1) if age_match else ""
    data['Gender'] = gender_match.group(1) if gender_match else ""
    
    # 4. Name (This is tricky, usually the first non-empty line after cleaning)
    lines = [line for line in text.split('\n') if line.strip()]
    # Simple heuristic: Look for lines that don't start with metadata keys
    for line in lines:
        if "Name" in line and "Father" not in line and "Husband" not in line:
            data['Name'] = line.replace("Name:", "").strip()
            break
            
    return data

def process_pdf(pdf_file_path):
    """
    Main function: Input PDF path -> Output Pandas DataFrame
    """
    final_data = []
    
    # 1. Convert PDF to Images
    try:
        images = convert_from_path(pdf_file_path)
    except Exception as e:
        return f"Error: {e}"

    for page_num, img_pil in enumerate(images):
        # Convert to OpenCV format
        img = cv2.cvtColor(np.array(img_pil), cv2.COLOR_RGB2BGR)
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        
        # 2. Thresholding
        thresh = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)[1]

        # 3. Grid Detection (The "Chopper")
        # Define kernels based on image size
        h_len = img.shape[1] // 35
        v_len = img.shape[0] // 35
        
        ver_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (1, v_len))
        hor_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (h_len, 1))
        
        img_v = cv2.morphologyEx(thresh, cv2.MORPH_OPEN, ver_kernel, iterations=2)
        img_h = cv2.morphologyEx(thresh, cv2.MORPH_OPEN, hor_kernel, iterations=2)
        
        grid_mask = cv2.addWeighted(img_v, 0.5, img_h, 0.5, 0.0)
        
        # 4. Find Contours (Boxes)
        contours, _ = cv2.findContours(grid_mask, cv2.RETR_TREE, cv2.CHAIN_APPROX_SIMPLE)
        
        # Sort contours top-to-bottom, then left-to-right (Crucial for correct order)
        # (Simplified sorting for now - usually requires a custom sort key)
        contours = sorted(contours, key=lambda ctr: cv2.boundingRect(ctr)[1]) 

        for c in contours:
            x, y, w, h = cv2.boundingRect(c)
            
            # Filter valid voter boxes
            if w > 100 and h > 50 and w < (img.shape[1] * 0.9):
                # Crop
                roi = img[y:y+h, x:x+w]
                
                # 5. OCR
                text = pytesseract.image_to_string(roi)
                
                # 6. Parse
                extracted = parse_voter_text(text)
                if extracted.get('VoterID') != "N/A": # Only add if it looks like a voter
                    final_data.append(extracted)

    # 7. Create DataFrame
    df = pd.DataFrame(final_data)
    return df