import pytesseract
from pdf2image import convert_from_path
import cv2

print("✅ OpenCV Version:", cv2.__version__)

try:
    # Check if Tesseract is found
    # Mac M-series Homebrew usually puts it here:
    pytesseract.pytesseract.tesseract_cmd = r'/opt/homebrew/bin/tesseract'
    version = pytesseract.get_tesseract_version()
    print(f"✅ Tesseract Version: {version}")
except Exception as e:
    print("❌ Tesseract Error:", e)

try:
    # Check if Poppler is found
    # We just test by importing; usually doesn't need explicit path if brew installed it
    print("✅ pdf2image is imported successfully")
except Exception as e:
    print("❌ Poppler/pdf2image Error:", e)