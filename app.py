import streamlit as st
import pandas as pd
import os
import io
# Import the engine we built in previous steps
from backend import process_pdf 

# --- PAGE CONFIGURATION ---
st.set_page_config(
    page_title="Voter Roll Digitizer", 
    page_icon="🗳️",
    layout="centered"
)

# --- CSS FOR UI POLISH ---
st.markdown("""
<style>
    .stButton>button {
        width: 100%;
        background-color: #FF4B4B;
        color: white;
    }
    .success-box {
        padding: 1rem;
        border-radius: 0.5rem;
        background-color: #D4EDDA;
        color: #155724;
        margin-bottom: 1rem;
    }
</style>
""", unsafe_allow_html=True)

# --- HEADER ---
st.title("🗳️ Electoral Roll Converter")
st.markdown("""
Upload a **scanned PDF** of an Electoral Roll (Voter List). 
This AI will detect the grid, read the text, fix typos, and generate a clean Excel file.
""")

# --- STEP 1: UPLOAD ---
uploaded_file = st.file_uploader("Choose your PDF file", type=["pdf"])

if uploaded_file is not None:
    # Save the uploaded file temporarily
    # (pdf2image requires a physical file path to work)
    temp_path = f"temp_{uploaded_file.name}"
    with open(temp_path, "wb") as f:
        f.write(uploaded_file.getbuffer())

    st.info(f"📄 Loaded: {uploaded_file.name}")

    # --- STEP 2: PROCESS BUTTON ---
    if st.button("🚀 Start Extraction Engine"):
        # Progress bar
        progress_bar = st.progress(0, text="Initializing Computer Vision...")
        
        try:
            # CALL THE BACKEND (The function we built in Phase 3)
            df = process_pdf(temp_path, progress_bar)
            
            # --- STEP 3: OUTPUT & ASSEMBLY ---
            if not df.empty:
                # 1. Success Message
                st.markdown(f"""
                <div class="success-box">
                    ✅ <b>Success!</b> Processed {len(df)} voters successfully.
                </div>
                """, unsafe_allow_html=True)
                
                # 2. Statistics (Phase 4 Value Add)
                c1, c2, c3 = st.columns(3)
                c1.metric("Total Voters", len(df))
                c2.metric("Male", len(df[df['Gender'] == 'Male']))
                c3.metric("Female", len(df[df['Gender'] == 'Female']))
                
                # 3. Preview Data
                st.subheader("📝 Data Preview")
                st.dataframe(df.head(5))
                
                # 4. EXCEL CONSTRUCTION (In-Memory)
                # We use BytesIO to create the file in RAM, so we don't clutter the hard drive
                buffer = io.BytesIO()
                with pd.ExcelWriter(buffer, engine='xlsxwriter') as writer:
                    df.to_excel(writer, index=False, sheet_name='Voter Data')
                    
                    # Auto-adjust column width (Polish)
                    worksheet = writer.sheets['Voter Data']
                    for i, col in enumerate(df.columns):
                        max_len = max(df[col].astype(str).map(len).max(), len(col)) + 2
                        worksheet.set_column(i, i, max_len)
                        
                # Reset buffer position
                buffer.seek(0)
                
                # 5. DOWNLOAD BUTTON
                st.download_button(
                    label="📥 Download Final Excel File",
                    data=buffer,
                    file_name="Converted_Voter_List.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                )
                
            else:
                st.error("❌ No voters found. The grid detection might have failed (check image quality).")
                
        except Exception as e:
            st.error(f"An error occurred: {e}")
            
        finally:
            # Cleanup: Remove the temp PDF
            if os.path.exists(temp_path):
                os.remove(temp_path)