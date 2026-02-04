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
        print("   - You should see white lines/text on a purely black background.")
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
    TEST_PDF = "temp_page 4 Goa.pdf"  # Use the same test PDF as before
    
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
        print("   - You should see ONLY the table lines. No text.")
    else:
        print(f"❌ Error: File '{TEST_PDF}' not found.")