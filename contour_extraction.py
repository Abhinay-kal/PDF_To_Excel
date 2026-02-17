# backend.py - PART 1: Pre-processing

import cv2

import numpy as np

from pdf2image import convert_from_path

import os

  

def preprocess_page(image_pil):

"""

Accepts a PIL image (from pdf2image), converts to OpenCV format,

and applies Grayscale -> Threshold -> Inversion.

Returns the processed binary image and the original OpenCV image.

"""

# 1. Convert PIL to OpenCV (BGR)

img = cv2.cvtColor(np.array(image_pil), cv2.COLOR_RGB2BGR)

  

# 2. Convert to Grayscale

# Purpose: Reduces file size and noise; color is irrelevant for structure.

gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

  

# 3. Binary Thresholding + Inversion

# cv2.THRESH_BINARY_INV: Turns the background BLACK and lines/text WHITE.

# cv2.THRESH_OTSU: Automatically finds the best "cutoff" point to separate ink from paper.

thresh = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)[1]

  

return thresh, img

  

# --- TESTING BLOCK (Run this file directly to check Step 1) ---

if __name__ == "__main__":

# Replace this with your actual PDF filename for testing

TEST_PDF = "temp_page 4 Goa.pdf"

print(f"🔄 Processing Step 1 for: {TEST_PDF}")

if os.path.exists(TEST_PDF):

# Convert just the first page for the test

pages = convert_from_path(TEST_PDF, first_page=1, last_page=1)

# Run the function

processed_img, original_img = preprocess_page(pages[0])

# Save the result so you can see it

output_filename = "debug_step1_inverted.jpg"

cv2.imwrite(output_filename, processed_img)

print(f"✅ Step 1 Complete! Check '{output_filename}'.")

print(" - You should see white lines/text on a purely black background.")

else:

print(f"❌ Error: File '{TEST_PDF}' not found in this folder.")

  

# --- ADD THIS TO backend.py ---

  

def detect_grid(thresh_img):

"""

Accepts the binary threshold image (white on black).

Uses morphological kernels to isolate horizontal and vertical lines.

Returns a clean 'grid mask' containing ONLY the table structure.

"""

# Define scale for the kernels.

# Div 35 is a good starting point (e.g. for width 2000px, kernel is ~57px long).

# If lines are missed, decrease 35 to 25. If text is detected as lines, increase to 50.

horizontal_scale = 35

vertical_scale = 35

# 1. Detect Vertical Lines

# Kernel shape: (1, height) -> A tall, thin stick.

v_len = thresh_img.shape[0] // vertical_scale

ver_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (1, v_len))

# Morph Open: Erodes noise, then Dilates what remains.

vertical_lines = cv2.morphologyEx(thresh_img, cv2.MORPH_OPEN, ver_kernel, iterations=2)

# 2. Detect Horizontal Lines

# Kernel shape: (width, 1) -> A long, flat stick.

h_len = thresh_img.shape[1] // horizontal_scale

hor_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (h_len, 1))

horizontal_lines = cv2.morphologyEx(thresh_img, cv2.MORPH_OPEN, hor_kernel, iterations=2)

# 3. Combine

# Simple addition: Vertical + Horizontal = Grid

grid_mask = cv2.addWeighted(vertical_lines, 0.5, horizontal_lines, 0.5, 0.0)

# 4. Refine (Optional but recommended)

# Apply a small dilation to close tiny gaps in the lines

kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (2, 2))

grid_mask = cv2.dilate(grid_mask, kernel, iterations=1)

# Threshold again to ensure strict binary (0 or 255)

_, grid_mask = cv2.threshold(grid_mask, 0, 255, cv2.THRESH_BINARY)

return grid_mask

  

# --- UPDATE THE TESTING BLOCK (At the bottom of backend.py) ---

if __name__ == "__main__":

TEST_PDF = "temp_page 4 Goa.pdf" # Use the same test PDF as before

print(f"🔄 Processing Step 2 for: {TEST_PDF}")

if os.path.exists(TEST_PDF):

pages = convert_from_path(TEST_PDF, first_page=1, last_page=1)

# Step 1: Preprocess

processed_img, original_img = preprocess_page(pages[0])

# Step 2: Detect Grid

grid_only = detect_grid(processed_img)

# Save results

cv2.imwrite("debug_step2_grid.jpg", grid_only)

print("✅ Step 2 Complete! Check 'debug_step2_grid.jpg'.")

print(" - You should see ONLY the table lines. No text.")

else:

print(f"❌ Error: File '{TEST_PDF}' not found.")

  
  

# --- ADD THIS TO backend.py ---

  

def sort_contours(contours, method="top-to-bottom"):

"""

Sorts contours Top-to-Bottom, then Left-to-Right.

Crucial for reading 3-column layouts correctly.

"""

# 1. Initialize

bounding_boxes = [cv2.boundingRect(c) for c in contours]

# If no contours found, return empty

if not contours:

return [], []

  

# 2. Initial Sort by "Y" (Top to Bottom)

# This puts all boxes in roughly the correct vertical order

cnts_boxes = zip(contours, bounding_boxes)

cnts_boxes = sorted(cnts_boxes, key=lambda b: b[1][1]) # Sort by Y

# 3. Fine-Tune Sort: "Row-by-Row" Logic

# We group boxes that are on the same "row" (within ~50 pixels of each other)

# and then sort those specific boxes Left-to-Right (by X).

final_sorted_contours = []

rows = []

current_row = []

last_y = 0

row_threshold = 50 # If y-difference is < 50px, consider it the same row

  

for i, (cnt, box) in enumerate(cnts_boxes):

x, y, w, h = box

if i == 0:

current_row.append((cnt, box))

last_y = y

else:

if abs(y - last_y) <= row_threshold:

# Same row -> Add to list

current_row.append((cnt, box))

else:

# New row detected -> Sort the old row by X (Left-to-Right)

current_row.sort(key=lambda b: b[1][0])

rows.append(current_row)

# Start new row

current_row = [(cnt, box)]

last_y = y

  

# Append the final row

if current_row:

current_row.sort(key=lambda b: b[1][0])

rows.append(current_row)

  

# Flatten the list back to a single list

for row in rows:

for item in row:

final_sorted_contours.append(item[0]) # Return only the contour

  

return final_sorted_contours

  

# --- ADD THIS TO backend.py ---

  

def sort_contours(contours, method="top-to-bottom"):

"""

Sorts contours Top-to-Bottom, then Left-to-Right.

Crucial for reading 3-column layouts correctly.

"""

# 1. Initialize

bounding_boxes = [cv2.boundingRect(c) for c in contours]

# If no contours found, return empty

if not contours:

return [], []

  

# 2. Initial Sort by "Y" (Top to Bottom)

# This puts all boxes in roughly the correct vertical order

cnts_boxes = zip(contours, bounding_boxes)

cnts_boxes = sorted(cnts_boxes, key=lambda b: b[1][1]) # Sort by Y

# 3. Fine-Tune Sort: "Row-by-Row" Logic

# We group boxes that are on the same "row" (within ~50 pixels of each other)

# and then sort those specific boxes Left-to-Right (by X).

final_sorted_contours = []

rows = []

current_row = []

last_y = 0

row_threshold = 50 # If y-difference is < 50px, consider it the same row

  

for i, (cnt, box) in enumerate(cnts_boxes):

x, y, w, h = box

if i == 0:

current_row.append((cnt, box))

last_y = y

else:

if abs(y - last_y) <= row_threshold:

# Same row -> Add to list

current_row.append((cnt, box))

else:

# New row detected -> Sort the old row by X (Left-to-Right)

current_row.sort(key=lambda b: b[1][0])

rows.append(current_row)

# Start new row

current_row = [(cnt, box)]

last_y = y

  

# Append the final row

if current_row:

current_row.sort(key=lambda b: b[1][0])

rows.append(current_row)

  

# Flatten the list back to a single list

for row in rows:

for item in row:

final_sorted_contours.append(item[0]) # Return only the contour

  

return final_sorted_contours

  

# --- REPLACE THIS FUNCTION IN backend.py ---

  

def get_voter_boxes(grid_mask, original_img_shape):

"""

Finds contours, filters out noise/nested boxes, and returns sorted valid boxes.

"""

# 1. Find Contours

# RETR_EXTERNAL tells OpenCV to only look for the outer-most shapes

# This helps avoid finding boxes inside boxes (like the Photo box)

contours, _ = cv2.findContours(grid_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

valid_contours = []

img_h, img_w = original_img_shape[:2]

  

# Calculate dynamic thresholds based on page size

# A voter column is roughly 1/3rd of the page width.

# A photo box is very small (maybe 1/10th).

# So we only keep boxes that are at least 1/5th (20%) of the page width.

min_width = img_w * 0.20

  

# 2. Filter Contours (Discard Noise, Photos, & Borders)

for c in contours:

x, y, w, h = cv2.boundingRect(c)

# Filter Logic:

# - Width > 20% of page (Removes 'Photo' boxes which are small)

# - Height > 50px (Removes flat lines)

# - Width < 90% of page (Removes the giant page border)

if w > min_width and h > 50 and w < (img_w * 0.9):

valid_contours.append(c)

# 3. Sort Contours (Top-Left to Bottom-Right)

sorted_cnts = sort_contours(valid_contours)

return sorted_cnts

  

# --- REPLACE THE TESTING BLOCK AT THE BOTTOM ---

if __name__ == "__main__":

TEST_PDF = "temp_page 4 Goa.pdf" # Use the same test PDF as before

print(f"🔄 Processing Step 3 (Revised) for: {TEST_PDF}")

if os.path.exists(TEST_PDF):

pages = convert_from_path(TEST_PDF, first_page=1, last_page=1)

# Steps 1 & 2

processed_img, original_img = preprocess_page(pages[0])

grid_only = detect_grid(processed_img)

# Step 3: Extract & Sort

sorted_boxes = get_voter_boxes(grid_only, original_img.shape)

# VISUALIZE: Draw BIG numbers to verify order

debug_img = original_img.copy()

# Dynamic font scale based on image width

font_scale = original_img.shape[1] // 500 # Will make text huge on high-res

thickness = 3

for i, c in enumerate(sorted_boxes):

x, y, w, h = cv2.boundingRect(c)

# Draw Green Box

cv2.rectangle(debug_img, (x, y), (x+w, y+h), (0, 255, 0), 4)

# Draw Order Number (Red Text, Big Font)

# Position: Top-Left corner of the box

cv2.putText(debug_img, str(i+1), (x + 20, y + 80),

cv2.FONT_HERSHEY_SIMPLEX, font_scale, (0, 0, 255), thickness)

output_file = "debug_step3_sorted_v2.jpg"

cv2.imwrite(output_file, debug_img)

print(f"✅ Step 3 Complete! Found {len(sorted_boxes)} boxes.")

print(f" - Open '{output_file}' and check the RED numbers.")

print(" - They should read: 1 (top-left), 2 (top-middle), 3 (top-right)...")

else:

print(f"❌ Error: File '{TEST_PDF}' not found.")