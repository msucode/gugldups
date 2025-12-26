import streamlit as st
import pandas as pd
from datetime import datetime
from utils import build_yearly_index, get_block_key
from matcher import find_best_match
from google_sheets import (
    authenticate_google_sheets, 
    get_sheet_by_url, 
    read_sheet_to_df,
    create_or_clear_sheet,
    write_df_to_sheet,
    delete_rows_by_indices
)
import config

st.title("Patient Duplicate Finder - Google Sheets Auto Update")

st.info("⚠️ This app requires Google Sheets API credentials. Upload your service account JSON file.")

uploaded_file = st.file_uploader("Upload Google Service Account JSON", type=['json'])

if uploaded_file:
    # Save uploaded file temporarily
    with open("credentials.json", "wb") as f:
        f.write(uploaded_file.getbuffer())
    
    st.success("✅ Credentials loaded")
    st.session_state['credentials_ready'] = True

if st.session_state.get('credentials_ready', False):
    yearly_url = st.text_input("Yearly Database Sheet URL")
    daily_url = st.text_input("Today's Daily Sheet URL (will be modified)")
    
    if st.button("Load Sheets"):
        if yearly_url and daily_url:
            try:
                client = authenticate_google_sheets("credentials.json")
                
                yearly_spreadsheet = get_sheet_by_url(client, yearly_url)
                daily_spreadsheet = get_sheet_by_url(client, daily_url)
                
                yearly_worksheet = yearly_spreadsheet.sheet1
                daily_worksheet = daily_spreadsheet.sheet1
                
                df_yearly = read_sheet_to_df(yearly_worksheet)
                df_daily = read_sheet_to_df(daily_worksheet)
                
                st.session_state['client'] = client
                st.session_state['daily_spreadsheet'] = daily_spreadsheet
                st.session_state['daily_worksheet'] = daily_worksheet
                st.session_state['df_yearly'] = df_yearly
                st.session_state['df_daily'] = df_daily
                st.session_state['files_ready'] = False
                
                st.success(f"✅ {len(df_yearly)} yearly, {len(df_daily)} daily")
                st.write("**Columns:**", list(df_daily.columns[:15]))
            except Exception as e:
                st.error(f"❌ {e}")

if 'df_yearly' in st.session_state:
    cols = list(st.session_state['df_daily'].columns)
    
    st.subheader("Select Columns")
    col1, col2 = st.columns(2)
    
    with col1:
        name_col = st.selectbox("Column 1 (Name)", cols, key='col1')
        mobile_col = st.selectbox("Column 2 (Mobile)", cols, key='col2')
    
    with col2:
        addr_col = st.selectbox("Column 3 (Address)", cols, key='col3')
        extra_col = st.selectbox("Column 4 (Extra)", cols, key='col4')
    
    if st.button("🔍 Find Duplicates & Update Sheets"):
        df_yearly = st.session_state['df_yearly']
        df_daily = st.session_state['df_daily']
        
        st.info("Building index...")
        yearly_blocks = build_yearly_index(df_yearly, mobile_col)
        
        st.info("Comparing...")
        
        perfect_duplicate_ids = set()
        all_match_results = []
        perfect_match_results = []
        
        for i, daily_row in df_daily.iterrows():
            block_key = get_block_key(daily_row[mobile_col])
            candidates = yearly_blocks.get(block_key, [])
            
            best_match = find_best_match(daily_row, candidates, name_col, mobile_col, addr_col, extra_col)
            
            if best_match and best_match['match_type'] == '🟢 PERFECT':
                perfect_duplicate_ids.add(i)
            
            if best_match:
                result = {
                    'Daily_Rec': i+1,
                    'Match_Type': best_match['match_type'],
                    'Score': best_match['score'],
                    'Daily_Col1': daily_row[name_col],
                    'Yearly_Col1': best_match['yearly_row'][name_col],
                    'Daily_Col2': daily_row[mobile_col],
                    'Yearly_Col2': best_match['yearly_row'][mobile_col],
                    'Daily_Col3': str(daily_row[addr_col])[:50],
                    'Yearly_Col3': str(best_match['yearly_row'][addr_col])[:50],
                    'Daily_Col4': str(daily_row[extra_col])[:50],
                    'Yearly_Col4': str(best_match['yearly_row'][extra_col])[:50],
                    'Daily_Patient Address': daily_row.get('Patient Address', ''),
                    'Yearly_Patient Address': best_match['yearly_row'].get('Patient Address', ''),
                    'Daily_Facility Name Lform': daily_row.get('Facility Name Lform', ''),
                    'Yearly_Facility Name Lform': best_match['yearly_row'].get('Facility Name Lform', ''),
                    'Daily_Date Of Onset': daily_row.get('Date Of Onset', ''),
                    'Yearly_Date Of Onset': best_match['yearly_row'].get('Date Of Onset', '')
                }
                
                if best_match['is_exact']:
                    result.update({
                        'Col1': '✅',
                        'Col2': '✅' if best_match['mobile_match'] else '❌',
                        'Col3': '✅' if best_match['addr_match'] else '❌',
                        'Col4': '✅' if best_match['extra_match'] else '❌'
                    })
                else:
                    result.update({
                        'Col1%': f"{int(best_match['col1_pct'])}%",
                        'Col2': '✅' if best_match['col2_match'] else '❌',
                        'Col3%': f"{int(best_match['col3_pct'])}%",
                        'Col4%': f"{int(best_match['col4_pct'])}%"
                    })
                
                all_match_results.append(result)
                
                if best_match['match_type'] == '🟢 PERFECT':
                    perfect_match_results.append(result)
        
        df_all_duplicates = pd.DataFrame(all_match_results) if all_match_results else pd.DataFrame()
        df_perfect_only = pd.DataFrame(perfect_match_results) if perfect_match_results else pd.DataFrame()
        
        st.success(f"✅ Found {len(perfect_duplicate_ids)} PERFECT duplicates | {len(all_match_results)} total matches")
        
        # Update Google Sheets
        try:
            daily_spreadsheet = st.session_state['daily_spreadsheet']
            
            st.info("Step 1: Creating 'Possible Duplicates' tab...")
            if not df_all_duplicates.empty:
                possible_dup_sheet = create_or_clear_sheet(daily_spreadsheet, "Possible Duplicates")
                write_df_to_sheet(possible_dup_sheet, df_all_duplicates)
                st.success(f"✅ Created 'Possible Duplicates' with {len(df_all_duplicates)} rows")
            
            st.info("Step 2: Creating 'Perfect Duplicates' tab...")
            if not df_perfect_only.empty:
                perfect_dup_sheet = create_or_clear_sheet(daily_spreadsheet, "Perfect Duplicates")
                write_df_to_sheet(perfect_dup_sheet, df_perfect_only)
                st.success(f"✅ Created 'Perfect Duplicates' with {len(df_perfect_only)} rows")
            
            st.info("Step 3: Deleting perfect duplicates from Daily sheet...")
            if perfect_duplicate_ids:
                daily_worksheet = st.session_state['daily_worksheet']
                delete_rows_by_indices(daily_worksheet, list(perfect_duplicate_ids))
                st.success(f"✅ Deleted {len(perfect_duplicate_ids)} perfect duplicates from Daily sheet")
            
            st.success("🎉 All updates completed successfully!")
            
        except Exception as e:
            st.error(f"❌ Error updating sheets: {e}")
        
        # Display preview
        if not df_all_duplicates.empty:
            with st.expander("📋 Preview: Possible Duplicates"):
                st.dataframe(df_all_duplicates.head(10), use_container_width=True)
        
        if not df_perfect_only.empty:
            with st.expander("🟢 Preview: Perfect Duplicates"):
                st.dataframe(df_perfect_only.head(10), use_container_width=True)
