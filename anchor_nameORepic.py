import streamlit as st

import pandas as pd

import numpy as np

import cv2

import pytesseract

import re

import os

import io

from pdf2image import convert_from_path

  

# --- CONFIG ---

st.set_page_config(page_title="Voter Roll Digitizer (Dual Anchor)", page_icon="🧬", layout="wide")

st.markdown("""<style>.stButton>button { width: 100%; background-color: #28a745; color: white; }</style>""", unsafe_allow_html=True)

  

# ==========================================

# CORE LOGIC: DUAL ANCHOR

# ==========================================

  

def get_vertical_strips(image_pil):

# Standard Preprocessing

img = cv2.cvtColor(np.array(image_pil), cv2.COLOR_RGB2BGR)

gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

img_h, img_w = gray.shape

col_w = img_w // 3

padding = int(col_w * 0.15) # Wide overlap

strips = [

gray[0:img_h, 0 : col_w + padding],

gray[0:img_h, col_w - padding : col_w * 2 + padding],

gray[0:img_h, col_w * 2 - padding : img_w]

]

return strips

  

def clean_text_line(line):

# Remove the "Deleted" watermark which kills OCR

return re.sub(r'(DELETED|Delet|Avail|Photo|Sect|Assem)', '', line, flags=re.IGNORECASE).strip()

  

def clean_id(text):

text = text.upper()

text = text.replace('$', 'S').replace('O', '0').replace('I', '1').replace('B', '8')

return re.sub(r'[^A-Z0-9]', '', text)

  

def extract_attributes(lines, start_index):

# Scans a window of lines to find attributes (House, Age, Gender)

data = {"Relation": "", "HouseNo": "", "Age": "", "Gender": ""}

# Look 3 lines forward and 3 lines back

window = lines[max(0, start_index-3) : min(len(lines), start_index+5)]

for line in window:

line = clean_text_line(line)

# House No

if "Number" in line:

match = re.search(r'Number\s*[:\-\.]\s*([0-9A-Za-z\-/]+)', line, re.IGNORECASE)

if match: data["HouseNo"] = match.group(1)

# Age/Gender

if "Age" in line or "Gender" in line:

age = re.search(r'Age\s*[:\-\.]\s*(\d+)', line, re.IGNORECASE)

if age: data["Age"] = age.group(1)

gen = re.search(r'Gender\s*[:\-\.]\s*([A-Za-z]+)', line, re.IGNORECASE)

if gen:

g = gen.group(1).lower()

data["Gender"] = "Male" if "mal" in g else "Female"

# Relation

if any(x in line for x in ["Father", "Husband", "Mother"]):

parts = re.split(r'[:\-]', line, 1)

if len(parts) > 1:

data["Relation"] = f"{parts[0].strip()}: {parts[1].strip()}"

return data

  

def parse_strip_dual_pass(text):

lines = [clean_text_line(line) for line in text.split('\n') if len(line) > 3]

raw_candidates = []

# --- PASS 1: FIND EVERYTHING ---

for i, line in enumerate(lines):

# CHECK 1: IS IT AN ID?

# Logic: Starts with 2+ letters, has digits, length 7-12

clean_first_word = clean_id(line.split(' ')[0])

is_id = (len(clean_first_word) >= 7 and

re.match(r'^[A-Z]{2,}', clean_first_word) and

any(c.isdigit() for c in clean_first_word))

# CHECK 2: IS IT A NAME?

is_name = re.match(r'(Name|Narne|Nane)[\W_]*[:\-\.|]', line, re.IGNORECASE)

if is_id or is_name:

# We found a "Signal". Let's capture the context.

candidate = {

"LineIndex": i,

"ID": clean_first_word if is_id else "UNREAD",

"Name": "",

"RawLine": line

}

# If it's a Name trigger, extract the name

if is_name:

parts = re.split(r'[:\-\.|]', line, maxsplit=1)

if len(parts) > 1: candidate["Name"] = parts[1].strip()

# If it's an ID trigger, assume Name is on next line

elif is_id and i+1 < len(lines):

next_line = lines[i+1]

if "Name" in next_line:

parts = re.split(r'[:\-\.|]', next_line, maxsplit=1)

if len(parts) > 1: candidate["Name"] = parts[1].strip()

else:

candidate["Name"] = next_line # Fallback

# Extract other details from surroundings

attrs = extract_attributes(lines, i)

candidate.update(attrs)

raw_candidates.append(candidate)

  

# --- PASS 2: MERGE & DEDUPLICATE ---

final_voters = []

if not raw_candidates: return []

# Start with the first candidate

current = raw_candidates[0]

for next_cand in raw_candidates[1:]:

# LOGIC: ARE THEY THE SAME PERSON?

# Condition 1: Lines are very close (within 2 lines of each other)

# Condition 2: They have the same House Number (strongest link)

is_close = (next_cand["LineIndex"] - current["LineIndex"]) <= 2

same_house = (current["HouseNo"] and next_cand["HouseNo"]

and current["HouseNo"] == next_cand["HouseNo"])

if is_close or same_house:

# MERGE THEM

# Pick the valid ID

if current["ID"] == "UNREAD" and next_cand["ID"] != "UNREAD":

current["ID"] = next_cand["ID"]

# Pick the longer name (usually more accurate)

if len(next_cand["Name"]) > len(current["Name"]):

current["Name"] = next_cand["Name"]

# Fill missing attributes

if not current["Age"]: current["Age"] = next_cand["Age"]

if not current["Gender"]: current["Gender"] = next_cand["Gender"]

else:

# They are different. Save current and move to next.

final_voters.append(current)

current = next_cand

# Append the last one

final_voters.append(current)

return final_voters

  

def process_pdf(pdf_path, progress_bar=None):

all_voters = []

try:

images = convert_from_path(pdf_path, dpi=400) # High DPI

except Exception as e:

st.error(f"Error: {e}")

return pd.DataFrame()

  

for i, img_pil in enumerate(images):

if progress_bar: progress_bar.progress((i+1)/len(images), f"Scanning Page {i+1}...")

strips = get_vertical_strips(img_pil)

for strip in strips:

text = pytesseract.image_to_string(strip, config='--psm 6')

voters = parse_strip_dual_pass(text)

all_voters.extend(voters)

# FINAL CLEANUP: Remove duplicates by ID

unique = {}

for v in all_voters:

# Create a unique key. If ID exists, use it. Else use Name+HouseNo

if v["ID"] != "UNREAD":

key = v["ID"]

else:

key = f"{v['Name']}_{v['HouseNo']}"

# Overwrite only if new entry has more data

if key not in unique:

unique[key] = v

else:

# If we already have this person, keeps the one with more info

old = unique[key]

if len(v["Name"]) > len(old["Name"]): unique[key] = v

return pd.DataFrame(list(unique.values()))

  

# ==========================================

# UI

# ==========================================

  

st.title("🧬 Dual-Anchor Extraction Engine")

st.markdown("### Strategy: Duplicate & Merge")

st.info("Scans for IDs and Names independently, creating duplicate candidates, then intelligently merges them based on spatial proximity.")

  

uploaded_file = st.file_uploader("Upload PDF", type=["pdf"])

  

if uploaded_file:

temp_path = f"temp_{uploaded_file.name}"

with open(temp_path, "wb") as f: f.write(uploaded_file.getbuffer())

if st.button("🚀 Run Dual-Core Extraction"):

bar = st.progress(0, "Starting...")

df = process_pdf(temp_path, bar)

bar.empty()

os.remove(temp_path)

if not df.empty:

st.success(f"✅ Extracted {len(df)} Unique Voters")

c1, c2, c3 = st.columns(3)

c1.metric("Total", len(df))

c2.metric("Valid IDs", len(df[df['ID'] != 'UNREAD']))

c3.metric("Missing IDs", len(df[df['ID'] == 'UNREAD']))

st.dataframe(df.head(10), use_container_width=True)

buffer = io.BytesIO()

with pd.ExcelWriter(buffer, engine='xlsxwriter') as writer:

df.to_excel(writer, index=False)

buffer.seek(0)

st.download_button("📥 Download Excel", buffer, "Dual_Anchor_Output.xlsx")

else:

st.error("No data found.")