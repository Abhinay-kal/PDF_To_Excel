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