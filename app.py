# app.py
import streamlit as st
import pandas as pd
import os
from backend import process_pdf # Import your function from Phase 2

# 1. Page Config
st.set_page_config(page_title="Voter Roll OCR", page_icon="🗳️")

st.title("🗳️ PDF to Excel Converter")
st.markdown("Upload a scanned Electoral Roll to extract voter data automatically.")

# 2. File Uploader
uploaded_file = st.file_uploader("Choose a PDF file", type="pdf")

if uploaded_file is not None:
    # Save the uploaded file temporarily because pdf2image needs a real path
    temp_path = f"temp_{uploaded_file.name}"
    with open(temp_path, "wb") as f:
        f.write(uploaded_file.getbuffer())

    st.success(f"File uploaded: {uploaded_file.name}")
    
    # 3. Process Button
    if st.button("Start Conversion"):
        with st.spinner("Scanning document... This may take a moment."):
            try:
                # Call the backend engine
                df_result = process_pdf(temp_path)
                
                # Check if we got data
                if isinstance(df_result, pd.DataFrame) and not df_result.empty:
                    st.success(f"Successfully extracted {len(df_result)} voters!")
                    
                    # 4. Preview Data
                    st.dataframe(df_result.head())
                    
                    # 5. Download Button
                    # Convert DF to Excel bytes
                    # (Requires 'openpyxl' installed)
                    excel_file = "voter_data.xlsx"
                    df_result.to_excel(excel_file, index=False)
                    
                    with open(excel_file, "rb") as f:
                        btn = st.download_button(
                            label="📥 Download Excel File",
                            data=f,
                            file_name="Converted_Voter_List.xlsx",
                            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                        )
                else:
                    st.warning("No data found. The PDF might not be readable or the grid detection failed.")
                    
            except Exception as e:
                st.error(f"An error occurred: {e}")
            finally:
                # Cleanup temp file
                if os.path.exists(temp_path):
                    os.remove(temp_path)