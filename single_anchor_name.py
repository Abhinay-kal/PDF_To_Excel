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

st.set_page_config(

page_title="Voter Roll Digitizer",

page_icon="🗳️",

layout="wide"

)

  

# --- CSS FOR UI POLISH ---

st.markdown("""

<style>

.stButton>button {

width: 100%;

background-color: #FF4B4B;

color: white;

font-weight: bold;

}

</style>

""", unsafe_allow_html=True)

  

# ==========================================

# CORE LOGIC (THE BACKEND)

# ==========================================

  

def get_vertical_strips(image_pil):

"""Slices the image into 3 vertical strips."""

img = cv2.cvtColor(np.array(image_pil), cv2.COLOR_RGB2BGR)

gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

img_h, img_w = gray.shape

col_w = img_w // 3

# 3 strips with 10px overlap

strips = [

gray[0:img_h, 0 : col_w + 10],

gray[0:img_h, col_w - 10 : col_w * 2 + 10],

gray[0:img_h, col_w * 2 - 10 : img_w]

]

return strips

  

def clean_id(text):

"""Cleans Voter ID."""

text = text.upper()

clean = text.replace('$', 'S').replace('O', '0').replace('I', '1').replace('B', '8')

clean = re.sub(r'[^A-Z0-9]', '', clean)

return clean

  

def clean_typos(data):

"""Standardizes Gender."""

if data["Gender"]:

g = data["Gender"].lower()

if "fem" in g: data["Gender"] = "Female"

elif "mal" in g: data["Gender"] = "Male"

return data

  

def parse_strip_text(text):

"""State Machine: Reads line-by-line using 'Name:' as anchor."""

lines = [line.strip() for line in text.split('\n') if line.strip()]

voters = []

current_voter = {}

for i, line in enumerate(lines):

# ANCHOR: Detect "Name:", "Narne:", etc.

if re.match(r'(Name|Narne|Nane|Mame)[\W_]*[:\-\.|]', line, re.IGNORECASE):

# Save previous voter

if current_voter and current_voter.get("Name"):

current_voter = clean_typos(current_voter)

voters.append(current_voter)

# Reset

current_voter = {

"ID": "UNREAD_ID", "Name": "", "Relation": "",

"HouseNo": "", "Age": "", "Gender": ""

}

# Extract Name

parts = re.split(r'[:\-\.|]', line, maxsplit=1)

if len(parts) > 1:

current_voter["Name"] = parts[1].strip()

# LOOK BACKWARDS FOR ID (6 lines)

for back_idx in range(1, 7):

if i - back_idx >= 0:

prev_line = lines[i - back_idx]

if any(x in prev_line for x in ["Avail", "Delet", "Photo", "Sect", "Assem", "Part"]):

continue

clean_cand = clean_id(prev_line)

if 7 <= len(clean_cand) <= 12:

if re.match(r'^[A-Z]{3}', clean_cand):

current_voter["ID"] = clean_cand

break

  

# PARSE ATTRIBUTES

elif current_voter:

if any(x in line for x in ["Father", "Husband", "Mother", "Other"]):

parts = re.split(r'[:\-\.|]', line, maxsplit=1)

if len(parts) > 1:

current_voter["Relation"] = f"{parts[0].strip()}: {parts[1].strip()}"

elif "House Number" in line:

hn_match = re.search(r'Number\s*[:\-\.|]\s*([0-9A-Za-z\-/]+)', line, re.IGNORECASE)

if hn_match: current_voter["HouseNo"] = hn_match.group(1)

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

  

def process_pdf(pdf_path, progress_bar=None):

"""Main Logic Pipeline"""

all_voters = []

try:

images = convert_from_path(pdf_path, dpi=300)

except Exception as e:

st.error(f"Error reading PDF: {e}")

return pd.DataFrame()

  

total = len(images)

for i, img_pil in enumerate(images):

if progress_bar:

progress_bar.progress((i + 1) / total, text=f"Scanning Page {i+1}...")

strips = get_vertical_strips(img_pil)

for strip in strips:

text = pytesseract.image_to_string(strip, config='--psm 6')

voters = parse_strip_text(text)

all_voters.extend(voters)

return pd.DataFrame(all_voters)

  

# ==========================================

