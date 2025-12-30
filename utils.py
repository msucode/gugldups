import pandas as pd
import re

def convert_to_csv_url(url):
    """Convert Google Sheet URL to CSV export URL"""
    sheet_id = re.search(r'/d/([a-zA-Z0-9-_]+)', url)
    if sheet_id:
        return f"https://docs.google.com/spreadsheets/d/{sheet_id.group(1)}/export?format=csv"
    return url

def normalize(text):
    """Normalize text for comparison - AGGRESSIVE CLEANING"""
    if pd.isna(text):
        return ""
    
    s = str(text).lower().strip()
    
    # Kill common garbage strings that cause false matches
    if s in ['nan', 'na', 'none', 'null', '0', '']:
        return ""
        
    return s

def get_block_key(mobile):
    """Get blocking key from mobile (last 4 digits) - IGNORES BAD NUMBERS"""
    m = normalize(mobile)
    
    # If mobile is empty or too short, return None (Do not block/group by this)
    if not m or len(m) < 4:
        return None
        
    return m[-4:]

def get_name_key(name):
    """Get blocking key from name (First Word Only)"""
    norm = normalize(name)
    if not norm:
        return None
    # Split by space and take the first part
    return norm.split()[0]

def build_yearly_index(df_yearly, mobile_col):
    """Build blocking index for faster search"""
    yearly_blocks = {}
    if mobile_col is None or mobile_col == 'None':
        return yearly_blocks
    
    for idx, row in df_yearly.iterrows():
        key = get_block_key(row[mobile_col])
        
        # FIX: Only index if we have a valid key
        if key:
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
        key = get_name_key(row[name_col])
        
        # FIX: Only index if we have a valid key
        if key:
            if key not in name_blocks:
                name_blocks[key] = []
            name_blocks[key].append(row)
    return name_blocks
