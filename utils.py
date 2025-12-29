import pandas as pd
import re

def convert_to_csv_url(url):
    """Convert Google Sheet URL to CSV export URL"""
    sheet_id = re.search(r'/d/([a-zA-Z0-9-_]+)', url)
    if sheet_id:
        return f"https://docs.google.com/spreadsheets/d/{sheet_id.group(1)}/export?format=csv"
    return url

def normalize(text):
    """Normalize text for comparison"""
    if pd.isna(text):
        return ""
    return str(text).lower().strip()

def get_block_key(mobile):
    """Get blocking key from mobile number (last 4 digits)"""
    m = str(mobile).strip()[-4:] if mobile else "XXXX"
    return m

def build_yearly_index(df_yearly, mobile_col):
    """Build blocking index for faster search"""
    yearly_blocks = {}
    for idx, row in df_yearly.iterrows():
        key = get_block_key(row[mobile_col])
        if key not in yearly_blocks:
            yearly_blocks[key] = []
        yearly_blocks[key].append(row)
    return yearly_blocks

def build_name_index(df_yearly, name_col):
    """Build name-based blocking index"""
    name_blocks = {}
    for idx, row in df_yearly.iterrows():
        key = normalize(row[name_col])
        if key and key != "":
            if key not in name_blocks:
                name_blocks[key] = []
            name_blocks[key].append(row)
    return name_blocks
