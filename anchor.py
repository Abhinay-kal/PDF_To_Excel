import cv2

import numpy as np

from pdf2image import convert_from_path

import pytesseract

import pandas as pd

import re

import os

  

# --- 1. PRE-PROCESSING ---

def preprocess_page(image_pil):

# Convert to standard OpenCV format

img = cv2.cvtColor(np.array(image_pil), cv2.COLOR_RGB2BGR)

# Convert to grayscale for better OCR

gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

# We apply a slight sharpening to make text pop, but NO thresholding

# Tesseract handles grayscale better than binary for "block" reading

return gray, img

  

# --- 2. THE ANCHOR METHOD (No Grids) ---

def extract_voters_from_column(column_img):

"""

Reads a vertical strip of the page and splits it by Voter ID.

"""

# 1. OCR the entire tall strip at once

# psm 6 = Assume a single uniform block of text

text = pytesseract.image_to_string(column_img, config='--psm 6')

# 2. Split by Voter ID Pattern (e.g., SMV1234567 or BKT...)

# We look for 3 letters followed by 7 digits

# The 'split' will give us: [trash, ID1, Data1, ID2, Data2...]

pattern = r'([A-Z]{3}\d{7})'

chunks = re.split(pattern, text)

voters = []

# Iterate through the chunks.

# Because of how split works, 'chunks' will look like:

# [ "Header text...", "SMV1234567", "Name: John...", "SMV7654321", "Name: Jane..." ]

# So we loop with step=2 to grab (ID, Data) pairs.

# We start from index 1 because index 0 is usually header trash

for i in range(1, len(chunks)-1, 2):

voter_id = chunks[i].strip()

raw_data = chunks[i+1].strip()

# Combine them for parsing

full_block = f"ID: {voter_id}\n{raw_data}"

parsed = parse_voter_data(full_block)

if parsed["Name"]: # Only keep if we found a name

voters.append(parsed)

return voters

  

# --- 3. PARSING LOGIC (Regex) ---

def clean_typos(data):

# Standard typo cleaning

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

# ID

id_match = re.search(r'(ID[:\s]*)([A-Z]{3}\d{7})', text)

if id_match: data["ID"] = id_match.group(2)

elif re.search(r'([A-Z]{3}\d{7})', text): # Fallback

data["ID"] = re.search(r'([A-Z]{3}\d{7})', text).group(1)

  

# House No

hn_match = re.search(r'House\s*Number\s*[:\-\.]\s*([0-9A-Za-z\-/]+)', text, re.IGNORECASE)

if hn_match: data["HouseNo"] = hn_match.group(1)

  

# Age & Gender

age_match = re.search(r'Age\s*[:\-\.]\s*(\d+)', text, re.IGNORECASE)

if age_match: data["Age"] = age_match.group(1)

gender_match = re.search(r'Gender\s*[:\-\.]\s*([A-Za-z]+)', text, re.IGNORECASE)

if gender_match: data["Gender"] = gender_match.group(1)

  

# Name & Relation

lines = [line.strip() for line in text.split('\n') if line.strip()]

for line in lines:

if any(x in line for x in ["House Number", "Age:", "Gender:", "ID:", "Photo", "Available"]):

continue

# Relation

if any(x in line for x in ["Father", "Husband", "Mother", "Other"]):

parts = re.split(r'[:\-]', line, 1)

if len(parts) > 1:

data["Relation"] = f"{parts[0].strip()}: {parts[1].strip()}"

# Name

elif "Name" in line or "Name:" in line:

parts = re.split(r'[:\-]', line, 1)

if len(parts) > 1:

data["Name"] = parts[1].strip()

# Fallback Name (First valid line that isn't data)

elif not data["Name"] and len(line) > 3 and not re.search(r'\d', line):

# Ignore "Available" or "Deleted"

if "Avail" not in line and "Delet" not in line:

data["Name"] = line

  

data = clean_typos(data)

return data

  

# --- 4. MAIN PROCESS ---

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

  

gray, original_img = preprocess_page(img_pil)

img_h, img_w = original_img.shape[:2]

  

# --- THE SLICING STRATEGY ---

# Instead of finding grid lines, we blindly crop 3 columns

# Column 1: 5% to 33%

# Column 2: 33% to 66%

# Column 3: 66% to 95%

col_width = img_w // 3

# Define the 3 vertical strips

strips = [

original_img[0:img_h, 0:col_width], # Left

original_img[0:img_h, col_width:col_width*2], # Middle

original_img[0:img_h, col_width*2:img_w] # Right

]

for strip_idx, strip_img in enumerate(strips):

# Extract voters from this strip using ID Anchors

voters = extract_voters_from_column(strip_img)

all_voters.extend(voters)

return pd.DataFrame(all_voters)

  

# --- DEBUG ---

if __name__ == "__main__":

TEST_PDF = "goa.pdf" # Make sure this matches your filename

if os.path.exists(TEST_PDF):

print("🚀 Running Anchor Method (No Grid Lines)...")

df = process_pdf(TEST_PDF)

if not df.empty:

print(f"✅ Success! Extracted {len(df)} voters.")

print(df[["ID", "Name", "Age"]].head(10))

df.to_excel("final_anchor_output.xlsx", index=False)

else:

print("❌ No voters found. Tesseract might not be reading the IDs.")

else:

print("File not found.")