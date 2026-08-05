import streamlit as st
import pandas as pd
import numpy as np
import json
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
    """Clean single value: NA string → empty, NaN → empty"""
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

st.title("Patient Duplicate Finder - Google Sheets Auto Update")

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
                st.session_state['files_ready'] = False
                
                st.success(f"✅ {len(df_yearly)} yearly, {len(df_daily)} daily")
                st.write("**Columns:**", list(df_daily.columns[:15]))
            except Exception as e:
                st.error(f"❌ {e}")
    
    if 'df_yearly' in st.session_state:
        cols = ['None'] + list(st.session_state['df_daily'].columns)
        
        st.subheader("Select Columns (minimum 1 required)")
        col1, col2 = st.columns(2)
        with col1:
            name_col = st.selectbox("Column 1 (Name)", cols, key='col1')
            mobile_col = st.selectbox("Column 2 (Mobile)", cols, key='col2')
        with col2:
            addr_col = st.selectbox("Column 3 (Address)", cols, key='col3')
            extra_col = st.selectbox("Column 4 (Extra)", cols, key='col4')
        
        # Check at least one column selected
        selected_cols = [c for c in [name_col, mobile_col, addr_col, extra_col] if c != 'None']
        
        if len(selected_cols) == 0:
            st.warning("⚠️ Select at least 1 column to compare")
        else:
            if st.button("🔍 Find Duplicates & Update Sheets"):
                df_yearly = st.session_state['df_yearly']
                df_daily = st.session_state['df_daily']
                
                st.info("Building mobile index...")
                yearly_blocks = build_yearly_index(df_yearly, mobile_col if mobile_col != 'None' else None)
                
                st.info("Building name index...")
                name_blocks = build_name_index(df_yearly, name_col if name_col != 'None' else None)
                
                st.info("Comparing...")
                perfect_duplicate_ids = set()
                all_match_results = []
                perfect_match_results = []
                
                for i, daily_row in df_daily.iterrows():
                    # Try mobile blocking first if mobile column selected
                    candidates = []
                    if mobile_col != 'None':
                        block_key = get_block_key(daily_row[mobile_col])
                        candidates = yearly_blocks.get(block_key, [])
                    
                    # If no mobile match, try name blocking if name column selected
                    if len(candidates) == 0 and name_col != 'None':
                        name_key = normalize(daily_row[name_col])
                        candidates = name_blocks.get(name_key, [])
                    
                    # If still no candidates and no blocking columns selected, use all yearly records
                    if len(candidates) == 0 and mobile_col == 'None' and name_col == 'None':
                        candidates = [row for _, row in df_yearly.iterrows()]
                    
                    best_match = find_best_match(daily_row, candidates, name_col, mobile_col, addr_col, extra_col)
                    
                    if best_match and best_match['match_type'] == '🟢 PERFECT':
                        perfect_duplicate_ids.add(i)
                    
                    if best_match:
                        if best_match['is_exact']:
                            result = {
                                'Daily_Rec': i+1,
                                'Match_Type': best_match['match_type'],
                                'Score': best_match['score']
                            }
                            
                            # Add columns only if selected
                            if name_col != 'None':
                                result.update({
                                    'Daily_Col1': clean_value(daily_row[name_col]),
                                    'Yearly_Col1': clean_value(best_match['yearly_row'][name_col]),
                                    'Col1': '✅'
                                })
                            if mobile_col != 'None':
                                result.update({
                                    'Daily_Col2': clean_value(daily_row[mobile_col]),
                                    'Yearly_Col2': clean_value(best_match['yearly_row'][mobile_col]),
                                    'Col2': '✅' if best_match.get('mobile_match', False) else '❌'
                                })
                            if addr_col != 'None':
                                result.update({
                                    'Daily_Col3': str(clean_value(daily_row[addr_col]))[:50],
                                    'Yearly_Col3': str(clean_value(best_match['yearly_row'][addr_col]))[:50],
                                    'Col3': '✅' if best_match.get('addr_match', False) else '❌'
                                })
                            if extra_col != 'None':
                                result.update({
                                    'Daily_Col4': str(clean_value(daily_row[extra_col]))[:50],
                                    'Yearly_Col4': str(clean_value(best_match['yearly_row'][extra_col]))[:50],
                                    'Col4': '✅' if best_match.get('extra_match', False) else '❌'
                                })
                            
                            result.update({
                                'Daily_Patient Address': clean_value(daily_row.get('Patient Address', '')),
                                'Yearly_Patient Address': clean_value(best_match['yearly_row'].get('Patient Address', '')),
                                'Daily_Facility Name Lform': clean_value(daily_row.get('Facility Name Lform', '')),
                                'Yearly_Facility Name Lform': clean_value(best_match['yearly_row'].get('Facility Name Lform', '')),
                                'Daily_Date Of Onset': clean_value(daily_row.get('Date Of Onset', '')),
                                'Yearly_Date Of Onset': clean_value(best_match['yearly_row'].get('Date Of Onset', ''))
                            })
                        else:
                            # Fuzzy match
                            result = {
                                'Daily_Rec': i+1,
                                'Match_Type': best_match['match_type'],
                                'Score': best_match['score']
                            }
                            
                            if name_col != 'None':
                                col1_emoji = '✅' if best_match.get('col1_pct', 0) >= 80 else '❌'
                                result.update({
                                    'Daily_Col1': clean_value(daily_row[name_col]),
                                    'Yearly_Col1': clean_value(best_match['yearly_row'][name_col]),
                                    'Col1': f"{col1_emoji} {int(best_match.get('col1_pct', 0))}%"
                                })
                            if mobile_col != 'None':
                                result.update({
                                    'Daily_Col2': clean_value(daily_row[mobile_col]),
                                    'Yearly_Col2': clean_value(best_match['yearly_row'][mobile_col]),
                                    'Col2': '✅' if best_match.get('col2_match', False) else '❌'
                                })
                            if addr_col != 'None':
                                col3_emoji = '✅' if best_match.get('col3_pct', 0) >= 80 else '❌'
                                result.update({
                                    'Daily_Col3': str(clean_value(daily_row[addr_col]))[:50],
                                    'Yearly_Col3': str(clean_value(best_match['yearly_row'][addr_col]))[:50],
                                    'Col3': f"{col3_emoji} {int(best_match.get('col3_pct', 0))}%"
                                })
                            if extra_col != 'None':
                                col4_emoji = '✅' if best_match.get('col4_pct', 0) >= 80 else '❌'
                                result.update({
                                    'Daily_Col4': str(clean_value(daily_row[extra_col]))[:50],
                                    'Yearly_Col4': str(clean_value(best_match['yearly_row'][extra_col]))[:50],
                                    'Col4': f"{col4_emoji} {int(best_match.get('col4_pct', 0))}%"
                                })
                            
                            result.update({
                                'Daily_Patient Address': clean_value(daily_row.get('Patient Address', '')),
                                'Yearly_Patient Address': clean_value(best_match['yearly_row'].get('Patient Address', '')),
                                'Daily_Facility Name Lform': clean_value(daily_row.get('Facility Name Lform', '')),
                                'Yearly_Facility Name Lform': clean_value(best_match['yearly_row'].get('Facility Name Lform', '')),
                                'Daily_Date Of Onset': clean_value(daily_row.get('Date Of Onset', '')),
                                'Yearly_Date Of Onset': clean_value(best_match['yearly_row'].get('Date Of Onset', ''))
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
                
                # Display preview with cleaned data
                if not df_all_duplicates.empty:
                    with st.expander("📋 Preview: Possible Duplicates"):
                        st.dataframe(
                            clean_dataframe_for_display(df_all_duplicates.head(10)),
                            use_container_width=True,
                        )
                
                if not df_perfect_only.empty:
                    with st.expander("🟢 Preview: Perfect Duplicates"):
                        st.dataframe(
                            clean_dataframe_for_display(df_perfect_only.head(10)),
                            use_container_width=True,
                        )
