import streamlit as st
import pandas as pd
import numpy as np
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

st.title("Patient Duplicate Finder - Google Sheets Auto Update")
st.info("⚠️ This app requires Google Sheets API credentials. Upload your service account JSON file.")

uploaded_file = st.file_uploader("Upload Google Service Account JSON", type=['json'])

if uploaded_file:
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
