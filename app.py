import streamlit as st
import pandas as pd
import numpy as np
import json
import time
from datetime import datetime
from utils import build_yearly_index, build_name_index, get_block_key, normalize
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

def clean_value(val):
    """Clean single value: NA string -> empty, NaN -> empty"""
    if pd.isna(val) or val == 'NA' or val == 'nan' or val == '':
        return ''
    return val

def clean_dataframe_for_display(df):
    """Clean DataFrame before display to avoid PyArrow errors"""
    df = df.copy()
    df = df.replace(['NA', 'nan', np.nan, np.inf, -np.inf, None], '')
    for col in df.columns:
        if df[col].dtype == 'object':
            df[col] = df[col].astype(str).replace('nan', '').replace('NA', '')
    return df

def load_credentials_from_secrets():
    """Load service-account dict from Streamlit secrets, if configured."""
    try:
        if "gcp_service_account" in st.secrets:
            return dict(st.secrets["gcp_service_account"])
    except Exception:
        # No secrets.toml / secrets not configured on Cloud
        pass
    return None

st.title("Patient Duplicate Finder (v3.0) - UI Updated")

# Prefer secrets; fall back to JSON upload (kept in memory, not written to disk)
if "gcp_credentials" not in st.session_state:
    secrets_creds = load_credentials_from_secrets()
    if secrets_creds:
        st.session_state["gcp_credentials"] = secrets_creds
        st.session_state["credentials_ready"] = True

if st.session_state.get("credentials_ready", False):
    st.success("✅ Credentials loaded")
else:
    st.info("⚠️ Upload your service account JSON file (or add `[gcp_service_account]` to Streamlit secrets)")
    uploaded_file = st.file_uploader("Upload Google Service Account JSON", type=["json"])

    if uploaded_file:
        try:
            st.session_state["gcp_credentials"] = json.loads(
                uploaded_file.getvalue().decode("utf-8")
            )
            st.session_state["credentials_ready"] = True
            st.success("✅ Credentials loaded")
            st.rerun()
        except Exception as e:
            st.error(f"❌ Invalid credentials JSON: {e}")

if st.session_state.get('credentials_ready', False):
    yearly_url = st.text_input("Yearly Database Sheet URL")
    daily_url = st.text_input("Today's Daily Sheet URL (will be modified)")
    
    if st.button("Load Sheets"):
        if yearly_url and daily_url:
            try:
                client = authenticate_google_sheets(st.session_state["gcp_credentials"])
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
                
                st.success(f"✅ {len(df_yearly)} yearly, {len(df_daily)} daily")
            except Exception as e:
                st.error(f"❌ Error loading sheets: {e}")
    
    if 'df_yearly' in st.session_state:
        daily_cols = ['None'] + list(st.session_state['df_daily'].columns)
        yearly_cols = ['None'] + list(st.session_state['df_yearly'].columns)
        
        # --- Section 1: Comparison Columns ---
        st.markdown("### 1. Map Comparison Columns (Daily Sheet)")
        col1, col2 = st.columns(2)
        with col1:
            name_col = st.selectbox("Column 1 (Name)", daily_cols, key='col1')
            mobile_col = st.selectbox("Column 2 (Mobile)", daily_cols, key='col2')
        with col2:
            addr_col = st.selectbox("Column 3 (Address)", daily_cols, key='col3')
            extra_col = st.selectbox("Column 4 (Extra)", daily_cols, key='col4')
            
        st.markdown("---")
        
        # --- Section 2: Age Columns ---
        st.markdown("### 2. Map Age Columns (For Report Only)")
        st.info("Select the column that contains 'Age' in each sheet.")
        age_col1, age_col2 = st.columns(2)
        with age_col1:
            daily_age_col = st.selectbox("Daily Sheet Age Column", daily_cols, key='daily_age')
        with age_col2:
            yearly_age_col = st.selectbox("Yearly Sheet Age Column", yearly_cols, key='yearly_age')
            
        st.markdown("---")
        
        selected_cols = [c for c in [name_col, mobile_col, addr_col, extra_col] if c != 'None']
        
        if len(selected_cols) == 0:
            st.warning("⚠️ Select at least 1 column to compare")
        else:
            if st.button("🔍 Find Duplicates & Update Sheets"):
                df_yearly = st.session_state['df_yearly']
                df_daily = st.session_state['df_daily']
                
                st.info("Building indexes...")
                yearly_blocks = build_yearly_index(df_yearly, mobile_col if mobile_col != 'None' else None)
                name_blocks = build_name_index(df_yearly, name_col if name_col != 'None' else None)
                
                st.info("Comparing Data...")
                perfect_duplicate_ids = set()
                possible_match_results = []
                perfect_match_results = []
                
                for i, daily_row in df_daily.iterrows():
                    candidates = []
                    if mobile_col != 'None':
                        block_key = get_block_key(daily_row[mobile_col])
                        candidates = yearly_blocks.get(block_key, [])
                    
                    if len(candidates) == 0 and name_col != 'None':
                        name_key = normalize(daily_row[name_col])
                        candidates = name_blocks.get(name_key, [])
                    
                    if len(candidates) == 0 and mobile_col == 'None' and name_col == 'None':
                        candidates = [row for _, row in df_yearly.iterrows()]
                    
                    best_match = find_best_match(daily_row, candidates, name_col, mobile_col, addr_col, extra_col)
                    
                    if best_match:
                        result = {
                            'Daily_Rec': i+1,
                            'Match_Type': best_match['match_type'],
                            'Score': best_match['score']
                        }
                        
                        if name_col != 'None':
                            col1_emoji = '✅' if best_match.get('col1_pct', 0) >= 80 or best_match['is_exact'] else '❌'
                            result.update({
                                'Daily_Col1': clean_value(daily_row[name_col]),
                                'Yearly_Col1': clean_value(best_match['yearly_row'][name_col]),
                                'Col1': f"{col1_emoji} {int(best_match.get('col1_pct', 100))}%" if not best_match['is_exact'] else '✅'
                            })
                        if mobile_col != 'None':
                            result.update({
                                'Daily_Col2': clean_value(daily_row[mobile_col]),
                                'Yearly_Col2': clean_value(best_match['yearly_row'][mobile_col]),
                                'Col2': '✅' if best_match.get('col2_match', False) or best_match.get('mobile_match', False) else '❌'
                            })
                        if addr_col != 'None':
                            col3_emoji = '✅' if best_match.get('col3_pct', 0) >= 80 or best_match['is_exact'] else '❌'
                            result.update({
                                'Daily_Col3': str(clean_value(daily_row[addr_col]))[:50],
                                'Yearly_Col3': str(clean_value(best_match['yearly_row'][addr_col]))[:50],
                                'Col3': f"{col3_emoji} {int(best_match.get('col3_pct', 100))}%" if not best_match['is_exact'] else ('✅' if best_match.get('addr_match') else '❌')
                            })
                        if extra_col != 'None':
                            col4_emoji = '✅' if best_match.get('col4_pct', 0) >= 80 or best_match['is_exact'] else '❌'
                            result.update({
                                'Daily_Col4': str(clean_value(daily_row[extra_col]))[:50],
                                'Yearly_Col4': str(clean_value(best_match['yearly_row'][extra_col]))[:50],
                                'Col4': f"{col4_emoji} {int(best_match.get('col4_pct', 100))}%" if not best_match['is_exact'] else ('✅' if best_match.get('extra_match') else '❌')
                            })
                        
                        # Fetch Age if mapped
                        if daily_age_col != 'None':
                            result['Daily_Age'] = clean_value(daily_row.get(daily_age_col, ''))
                        if yearly_age_col != 'None':
                            result['Yearly_Age'] = clean_value(best_match['yearly_row'].get(yearly_age_col, ''))

                        # Fetch Fixed Info (If it exists in sheet)
                        result.update({
                            'Daily_Patient Address': clean_value(daily_row.get('Patient Address', '')),
                            'Yearly_Patient Address': clean_value(best_match['yearly_row'].get('Patient Address', '')),
                            'Daily_Facility Name Lform': clean_value(daily_row.get('Facility Name Lform', '')),
                            'Yearly_Facility Name Lform': clean_value(best_match['yearly_row'].get('Facility Name Lform', '')),
                            'Daily_Date Of Onset': clean_value(daily_row.get('Date Of Onset', '')),
                            'Yearly_Date Of Onset': clean_value(best_match['yearly_row'].get('Date Of Onset', ''))
                        })
                        
                        if best_match['match_type'] == '🟢 PERFECT':
                            perfect_match_results.append(result)
                            perfect_duplicate_ids.add(i)
                        else:
                            possible_match_results.append(result)
                
                df_possible = pd.DataFrame(possible_match_results) if possible_match_results else pd.DataFrame()
                df_perfect = pd.DataFrame(perfect_match_results) if perfect_match_results else pd.DataFrame()
                
                st.success(f"✅ Found {len(perfect_duplicate_ids)} PERFECT duplicates | {len(possible_match_results)} POSSIBLE matches")
                
                try:
                    daily_spreadsheet = st.session_state['daily_spreadsheet']
                    
                    st.info("Step 1: Creating 'Possible Duplicates' tab...")
                    if not df_possible.empty:
                        possible_dup_sheet = create_or_clear_sheet(daily_spreadsheet, "Possible Duplicates")
                        write_df_to_sheet(possible_dup_sheet, df_possible)
                    
                    time.sleep(3)
                    
                    st.info("Step 2: Creating 'Perfect Duplicates' tab...")
                    if not df_perfect.empty:
                        perfect_dup_sheet = create_or_clear_sheet(daily_spreadsheet, "Perfect Duplicates")
                        write_df_to_sheet(perfect_dup_sheet, df_perfect)
                        
                    time.sleep(3)
                    
                    st.info("Step 3: Deleting perfect duplicates from Daily sheet...")
                    if perfect_duplicate_ids:
                        daily_worksheet = st.session_state['daily_worksheet']
                        delete_rows_by_indices(daily_worksheet, list(perfect_duplicate_ids))
                    
                    st.success("🎉 All updates completed successfully!")
                except Exception as e:
                    st.error(f"❌ Error updating sheets: {e}")
                
                if not df_possible.empty:
                    with st.expander("📋 Preview: Possible Duplicates"):
                        st.dataframe(clean_dataframe_for_display(df_possible.head(10)), width='stretch')
                
                if not df_perfect.empty:
                    with st.expander("🟢 Preview: Perfect Duplicates"):
                        st.dataframe(clean_dataframe_for_display(df_perfect.head(10)), width='stretch')
