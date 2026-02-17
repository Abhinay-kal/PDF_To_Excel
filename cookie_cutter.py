 import cv2

import numpy as np

from pdf2image import convert_from_path

import pytesseract

import pandas as pd

import re

import os

  

# --- 1. PRE-PROCESSING (Standard) ---

def preprocess_page(image_pil):

img = cv2.cvtColor(np.array(image_pil), cv2.COLOR_RGB2BGR)

gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

# Use Adaptive Threshold to handle shadows/faint lines

thresh = cv2.adaptiveThreshold(

gray, 255,

cv2.ADAPTIVE_THRESH_GAUSSIAN_C,

cv2.THRESH_BINARY_INV,

15, 5

)

return thresh, img

  

# --- 2. THE COOKIE CUTTER (New Strategy) ---

# --- REPLACE THIS FUNCTION IN backend.py ---

  

def get_cookie_cutter_boxes(thresh_img, original_img):

"""

1. Finds the Top and Bottom horizontal lines of the grid.

2. Uses them as anchors to slice the table perfectly.

"""

img_h, img_w = original_img.shape[:2]

# A. Detect Horizontal Lines Only

# We want to find the top header line and bottom footer line

horizontal_scale = 30

h_len = img_w // horizontal_scale

hor_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (h_len, 1))

horizontal_lines = cv2.morphologyEx(thresh_img, cv2.MORPH_OPEN, hor_kernel, iterations=2)

# Get coordinates of all horizontal lines

contours, _ = cv2.findContours(horizontal_lines, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

# Sort them from Top to Bottom (by Y-coordinate)

line_y_coords = []

for c in contours:

x, y, w, h = cv2.boundingRect(c)

# Only count lines that are wide (at least 50% of page width)

if w > (img_w * 0.5):

line_y_coords.append(y)

line_y_coords.sort()

# B. Determine Table Boundaries

if len(line_y_coords) >= 2:

# Top of table is the first wide line found

table_top = line_y_coords[0]

# Bottom of table is the last wide line found

table_bottom = line_y_coords[-1]

else:

# Fallback if lines are broken (Manual override)

print("⚠️ Warning: Could not find clear grid lines. Using manual estimates.")

table_top = int(img_h * 0.13) # Default ~13% down

table_bottom = int(img_h * 0.95) # Default ~95% down

  

# C. Calculate Slice Dimensions

# A standard roll has 3 Columns and 10 Rows

table_height = table_bottom - table_top

table_width = int(img_w * 0.90) # Assume table takes 90% of page width

start_x = int(img_w * 0.05) # Start 5% from left edge

row_height = table_height // 10

col_width = table_width // 3

boxes = []

# D. Generate the Grid

for row in range(10):

for col in range(3):

# Calculate box coordinates

x = start_x + (col * col_width)

y = table_top + (row * row_height)

# Corrections:

# 1. Add small padding so we don't clip the text

# 2. Ensure we don't go off the page

w = col_width - 5

h = row_height - 5

boxes.append((x, y, w, h))

return boxes

  

# --- 3. PARSING & CLEANING (Kept from before) ---

def clean_typos(data):

gender = data["Gender"].lower().strip()

if gender in ["mala", "maie", "mle", "rnale", "male."]:

data["Gender"] = "Male"

elif gender in ["femala", "femaie", "fermale", "fernale", "female."]:

data["Gender"] = "Female"

if data["ID"]:

data["ID"] = data["ID"].replace(" ", "").replace("$", "S").replace("O", "0")

return data

  

def validate_entry(data):

status = []

if not data["Name"] or len(data["Name"]) < 3: status.append("Missing Name")

if not data["Age"]: status.append("Missing Age")

if not data["ID"]: status.append("Missing ID")

return "OK" if not status else "REVIEW: " + ", ".join(status)

  

def parse_voter_data(text):

text = text.replace("*", "").replace("?", "").replace("!", "").replace("'", "").replace('"', "")

text = text.replace("Narne", "Name").replace("Nare", "Name")

data = {"Name": "", "Relation": "", "HouseNo": "", "Age": "", "Gender": "", "ID": "", "Status": ""}

id_match = re.search(r'([A-Z]{3}\d{7})', text)

if id_match: data["ID"] = id_match.group(1)

  

hn_match = re.search(r'House\s*Number\s*[:\-\.]\s*([0-9A-Za-z\-/]+)', text, re.IGNORECASE)

if hn_match: data["HouseNo"] = hn_match.group(1)

  

age_match = re.search(r'Age\s*[:\-\.]\s*(\d+)', text, re.IGNORECASE)

if age_match: data["Age"] = age_match.group(1)

gender_match = re.search(r'Gender\s*[:\-\.]\s*([A-Za-z]+)', text, re.IGNORECASE)

if gender_match: data["Gender"] = gender_match.group(1)

  

lines = [line.strip() for line in text.split('\n') if line.strip()]

for line in lines:

if any(x in line for x in ["House Number", "Age:", "Gender:", "Photo", "Available", "Section"]):

continue

if any(x in line for x in ["Father", "Husband", "Mother", "Other"]):

parts = re.split(r'[:\-]', line, 1)

if len(parts) > 1:

data["Relation"] = f"{parts[0].strip()}: {parts[1].strip()}"

elif "Name" in line or "Name:" in line:

parts = re.split(r'[:\-]', line, 1)

if len(parts) > 1:

data["Name"] = parts[1].strip()

else:

if not data["Name"] and len(line) > 3 and not re.search(r'\d', line):

data["Name"] = line

  

data = clean_typos(data)

data["Status"] = validate_entry(data)

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

  

thresh, original_img = preprocess_page(img_pil)

# STRATEGY CHANGE: USE COOKIE CUTTER

boxes = get_cookie_cutter_boxes(thresh, original_img)

for box in boxes:

x, y, w, h = box

roi = original_img[y:y+h, x:x+w]

text = pytesseract.image_to_string(roi, config='--psm 6')

info = parse_voter_data(text)

# Save valid entries

if info["Name"] or info["ID"]:

all_voters.append(info)

return pd.DataFrame(all_voters)

  

# --- REPLACE THE BOTTOM BLOCK OF backend.py WITH THIS ---

  

if __name__ == "__main__":

# We use the new simple name

TEST_PDF = "goa.pdf"

print(f"📂 Current Folder: {os.getcwd()}")

print(f"🔍 Looking for: {TEST_PDF}")

if os.path.exists(TEST_PDF):

print("✅ File FOUND! Starting processing...")

# 1. Load PDF

pages = convert_from_path(TEST_PDF, first_page=1, last_page=1)

print(" - PDF Loaded.")

# 2. Preprocess

thresh, original_img = preprocess_page(pages[0])

print(" - Image Preprocessed.")

# 3. Get Cookie Cutter Boxes

boxes = get_cookie_cutter_boxes(thresh, original_img)

print(f" - Extracted {len(boxes)} regions (Target: 30)")

# 4. Draw Debug Image

debug_img = original_img.copy()

for i, box in enumerate(boxes):

x, y, w, h = box

# Draw Green Box

cv2.rectangle(debug_img, (x, y), (x+w, y+h), (0, 255, 0), 5)

# Draw Number

cv2.putText(debug_img, str(i+1), (x+10, y+50), cv2.FONT_HERSHEY_SIMPLEX, 2, (0,0,255), 3)

  

output_file = "debug_cookie_cutter.jpg"

cv2.imwrite(output_file, debug_img)

print(f"🎉 Success! Image saved as '{output_file}'")

print(" OPEN IT NOW to verify the grid.")

else:

print("\n❌ ERROR: File not found!")

print(" I see these files in your folder:")

# List all files so you can see what Python sees

for f in os.listdir():

if f.endswith(".pdf"):

print(f" - {f}")

print("\n👉 Please rename your PDF to 'goa.pdf' and try again.")