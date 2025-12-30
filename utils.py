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
    if mobile is None:
        return "XXXX"
    m = str(mobile).strip()[-4:] if mobile else "XXXX"
    return m

def get_name_key(name):
    """Get blocking key from name (First Word Only)"""
    # This fixes the issue where spelling errors in last name caused 0 matches
    norm = normalize(name)
    if not norm:
        return ""
    # Split by space and take the first part (e.g. "shreeniwas")
    return norm.split()[0]

def build_yearly_index(df_yearly, mobile_col):
    """Build blocking index for faster search"""
    yearly_blocks = {}
    if mobile_col is None or mobile_col == 'None':
        return yearly_blocks
    
    for idx, row in df_yearly.iterrows():
        key = get_block_key(row[mobile_col])
        if key not in yearly_blocks:
            yearly_blocks[key] = []
        yearly_blocks[key].append(row)
    return yearly_blocks

def build_name_index(df_yearly, name_col):
    """Build name-based blocking index using FIRST WORD ONLY"""
    name_blocks = {}
    if name_col is None or name_col == 'None':
        return name_blocks
    
    for idx, row in df_yearly.iterrows():
        # Use the new helper to get first word
        key = get_name_key(row[name_col])
        
        if key and key != "":
            if key not in name_blocks:
                name_blocks[key] = []
            name_blocks[key].append(row)
    return name_blocks
