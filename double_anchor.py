import streamlit as st

import pandas as pd

import numpy as np

import cv2

import pytesseract

import re

import os

import io

from pdf2image import convert_from_path

  

# --- PAGE CONFIGURATION ---

st.set_page_config(page_title="Voter Roll Digitizer", page_icon="🗳️", layout="wide")

  

# --- UI STYLING ---

st.markdown("""

<style>

.stButton>button { width: 100%; background-color: #FF4B4B; color: white; font-weight: bold; }

</style>

""", unsafe_allow_html=True)

  

# ==========================================

# CORE LOGIC (BACKEND)

# ==========================================

  

def get_vertical_strips(image_pil):

"""

Slices image into 3 vertical strips with MASSIVE overlap

to handle skewed (crooked) scans.

"""

img = cv2.cvtColor(np.array(image_pil), cv2.COLOR_RGB2BGR)

gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

img_h, img_w = gray.shape

col_w = img_w // 3

# STRATEGY 1: WIDE OVERLAP

padding = int(col_w * 0.15)

strips = [

gray[0:img_h, 0 : col_w + padding],

gray[0:img_h, col_w - padding : col_w * 2 + padding],

gray[0:img_h, col_w * 2 - padding : img_w]

]

return strips

  

def clean_id(text):

text = text.upper()

# Fix common OCR confusions

clean = text.replace('$', 'S').replace('O', '0').replace('I', '1').replace('B', '8')

# FIX: Remove 'DELETED' artifacts from ID

clean = clean.replace("DELETE", "").replace("DELET", "")

clean = re.sub(r'[^A-Z0-9]', '', clean)

return clean

  

def clean_typos(data):

if data["Gender"]:

g = data["Gender"].lower()

if "fem" in g: data["Gender"] = "Female"

elif "mal" in g: data["Gender"] = "Male"

return data

  

def parse_strip_text(text):

"""

Dual-Anchor Parser: Catches voters by 'Name:' OR by 'ID Pattern'.

"""

lines = [line.strip() for line in text.split('\n') if line.strip()]

voters = []

current_voter = {}

for i, line in enumerate(lines):

# --- CLEANUP: Remove "Deleted" noise so we don't trip over it ---

clean_line = line.replace("Deleted", "").replace("DELETED", "").replace("Delet", "")

# --- TRIGGER 1: DETECT "NAME" ---

is_name_trigger = re.match(r'(Name|Narne|Nane|Mame)[\W_]*[:\-\.|]', clean_line, re.IGNORECASE)

# --- TRIGGER 2: DETECT "ID" DIRECTLY ---

# Looks for pattern like "SMV1234567" at start of line

clean_line_start = clean_id(clean_line.split(' ')[0])

is_id_trigger = (

len(clean_line_start) >= 7 and

re.match(r'^[A-Z]{2,}', clean_line_start) and

any(char.isdigit() for char in clean_line_start)

)

  

# --- NEW VOTER START ---

if is_name_trigger or is_id_trigger:

# Save previous voter if valid

if current_voter and (current_voter.get("Name") or current_voter.get("ID") != "UNREAD_ID"):

current_voter = clean_typos(current_voter)

if not any(v.get("ID") == current_voter["ID"] for v in voters if v.get("ID") != "UNREAD_ID"):

voters.append(current_voter)

# Reset

current_voter = {

"ID": "UNREAD_ID", "Name": "", "Relation": "",

"HouseNo": "", "Age": "", "Gender": ""

}

# HANDLE TRIGGERS

if is_name_trigger:

parts = re.split(r'[:\-\.|]', clean_line, maxsplit=1)

if len(parts) > 1: current_voter["Name"] = parts[1].strip()

# Look backward for ID

for back_idx in range(1, 6):

if i - back_idx >= 0:

prev = lines[i - back_idx]

# FIX: DO NOT SKIP 'DELETED' LINES ANYMORE

if any(x in prev for x in ["Avail", "Photo", "Sect", "Assem"]):

continue

# Clean the previous line before checking ID

clean_prev = clean_id(prev)

if 7 <= len(clean_prev) <= 12 and re.match(r'^[A-Z]{2}', clean_prev):

current_voter["ID"] = clean_prev

break

elif is_id_trigger:

current_voter["ID"] = clean_line_start

# The Name is likely on the NEXT line

if i + 1 < len(lines):

next_line = lines[i+1]

if "Name" in next_line:

parts = re.split(r'[:\-\.|]', next_line, maxsplit=1)

if len(parts) > 1: current_voter["Name"] = parts[1].strip()

else:

current_voter["Name"] = next_line

  

# --- ATTRIBUTES PARSING ---

elif current_voter:

# Clean the line here too

clean_line = line.replace("Deleted", "").replace("DELETED", "").replace("Delet", "")

if any(x in clean_line for x in ["Father", "Husband", "Mother", "Other"]):

parts = re.split(r'[:\-\.|]', clean_line, maxsplit=1)

if len(parts) > 1:

current_voter["Relation"] = f"{parts[0].strip()}: {parts[1].strip()}"

elif "House Number" in clean_line:

hn_match = re.search(r'Number\s*[:\-\.|]\s*([0-9A-Za-z\-/]+)', clean_line, re.IGNORECASE)

if hn_match: current_voter["HouseNo"] = hn_match.group(1)

elif "Age" in clean_line or "Gender" in clean_line:

age_match = re.search(r'Age\s*[:\-\.|]\s*(\d+)', clean_line, re.IGNORECASE)

if age_match: current_voter["Age"] = age_match.group(1)

gen_match = re.search(r'Gender\s*[:\-\.|]\s*([A-Za-z]+)', clean_line, re.IGNORECASE)

if gen_match: current_voter["Gender"] = gen_match.group(1)

  

# Save last

if current_voter and (current_voter.get("Name") or current_voter.get("ID") != "UNREAD_ID"):

current_voter = clean_typos(current_voter)

if not any(v.get("ID") == current_voter["ID"] for v in voters if v.get("ID") != "UNREAD_ID"):

voters.append(current_voter)

return voters

  

def process_pdf(pdf_path, progress_bar=None):

all_voters = []

try:

images = convert_from_path(pdf_path, dpi=400)

except Exception as e:

st.error(f"Error reading PDF: {e}")

return pd.DataFrame()

  

total = len(images)

for i, img_pil in enumerate(images):

if progress_bar: progress_bar.progress((i + 1) / total, text=f"Scanning Page {i+1}...")

strips = get_vertical_strips(img_pil)

for strip in strips:

text = pytesseract.image_to_string(strip, config='--psm 6')

voters = parse_strip_text(text)

all_voters.extend(voters)

# Final Deduplication

unique_voters = []

seen_ids = set()

for v in all_voters:

if v["ID"] != "UNREAD_ID":

if v["ID"] not in seen_ids:

seen_ids.add(v["ID"])

unique_voters.append(v)

else:

unique_voters.append(v)

return pd.DataFrame(unique_voters)

  

# ==========================================

