from rapidfuzz import fuzz
from utils import normalize, get_block_key
import config

def check_exact_match(daily_row, yearly_row, name_col, mobile_col, addr_col, extra_col):
    """Check if names match exactly and categorize by column matches"""
    # Handle None columns
    if name_col == 'None' or name_col is None:
        return None
    
    daily_name = normalize(daily_row[name_col])
    yearly_name = normalize(yearly_row[name_col])
    
    if daily_name != yearly_name or daily_name == "":
        return None
    
    # Count exact matches
    exact_col_count = 1  # Name always matches
    
    mobile_match = False
    if mobile_col != 'None' and mobile_col is not None:
        d_mob = normalize(daily_row[mobile_col])
        y_mob = normalize(yearly_row[mobile_col])
        # FIX: Only match if both are NOT empty
        if d_mob != "" and y_mob != "":
            mobile_match = (d_mob == y_mob)
        
        if mobile_match:
            exact_col_count += 1
    
    addr_match = False
    if addr_col != 'None' and addr_col is not None:
        addr_match = normalize(daily_row[addr_col]) == normalize(yearly_row[addr_col])
        if addr_match:
            exact_col_count += 1
    
    extra_match = False
    if extra_col != 'None' and extra_col is not None:
        extra_match = normalize(daily_row[extra_col]) == normalize(yearly_row[extra_col])
        if extra_match:
            exact_col_count += 1
    
    # Categorize based on how many columns were selected and matched
    selected_count = 1  # Name is always selected if we got here
    if mobile_col != 'None' and mobile_col is not None:
        selected_count += 1
    if addr_col != 'None' and addr_col is not None:
        selected_count += 1
    if extra_col != 'None' and extra_col is not None:
        selected_count += 1
    
    if exact_col_count == selected_count:
        match_category = '🟢 PERFECT'
    elif exact_col_count >= selected_count * 0.75:
        match_category = '🟢 STRONG'
    elif exact_col_count >= selected_count * 0.5:
        match_category = '🟢 PARTIAL'
    else:
        match_category = '🟢 WEAK'
    
    return {
        'score': 100,
        'match_type': match_category,
        'yearly_row': yearly_row,
        'mobile_match': mobile_match,
        'addr_match': addr_match,
        'extra_match': extra_match,
        'exact_col_count': exact_col_count,
        'is_exact': True
    }

def check_fuzzy_match(daily_row, yearly_row, name_col, mobile_col, addr_col, extra_col):
    """Calculate fuzzy match score with IDENTITY GATEKEEPER & EMPTY FIX"""
    score = 0
    total_weight = 0
    
    col1_pct = 0
    col2_match = False
    col3_pct = 0
    col4_pct = 0
    
    # --- STEP 1: CHECK IDENTITY COLUMNS (Name & Mobile) ---
    
    # Column 1 - Name
    if name_col != 'None' and name_col is not None:
        daily_name = normalize(daily_row[name_col])
        yearly_name = normalize(yearly_row[name_col])
        col1_pct = fuzz.token_sort_ratio(daily_name, yearly_name)
        
    # Column 2 - Mobile (exact match only)
    if mobile_col != 'None' and mobile_col is not None:
        daily_mobile = normalize(daily_row[mobile_col])
        yearly_mobile = normalize(yearly_row[mobile_col])
        
        # FIX: Only set True if both are NOT empty and match
        if daily_mobile != "" and yearly_mobile != "":
            col2_match = (daily_mobile == yearly_mobile)
        else:
            col2_match = False
    
    # --- KILLER LOGIC: GATEKEEPER ---
    # If Name is NOT similar (<50%) AND Mobile does NOT match...
    # STOP IMMEDIATELY. Do not check Address/Disease.
    if col1_pct < 50 and not col2_match:
        return None
    # --------------------------------
    
    # If we passed the gate, calculate the actual weights
    if name_col != 'None':
        score += (col1_pct / 100) * config.SCORE_COL1_WEIGHT
        total_weight += config.SCORE_COL1_WEIGHT
        
    if mobile_col != 'None':
        if col2_match:
            score += config.SCORE_COL2_WEIGHT
        total_weight += config.SCORE_COL2_WEIGHT

    # --- STEP 2: CHECK ATTRIBUTE COLUMNS (Address & Extra) ---
    
    # Column 3 - Address
    if addr_col != 'None' and addr_col is not None:
        daily_addr = normalize(daily_row[addr_col])
        yearly_addr = normalize(yearly_row[addr_col])
        col3_pct = fuzz.token_set_ratio(daily_addr, yearly_addr)
        score += (col3_pct / 100) * config.SCORE_COL3_WEIGHT
        total_weight += config.SCORE_COL3_WEIGHT
    
    # Column 4 - Extra
    if extra_col != 'None' and extra_col is not None:
        daily_extra = normalize(daily_row[extra_col])
        yearly_extra = normalize(yearly_row[extra_col])
        col4_pct = fuzz.token_set_ratio(daily_extra, yearly_extra)
        score += (col4_pct / 100) * config.SCORE_COL4_WEIGHT
        total_weight += config.SCORE_COL4_WEIGHT
    
    # Normalize score to 100 scale based on selected columns
    if total_weight > 0:
        score = (score / total_weight) * 100
    
    # Categorize
    if score >= config.THRESHOLD_HIGH:
        match_type = '🔴 HIGH'
    elif score >= config.THRESHOLD_MEDIUM:
        match_type = '🟡 MEDIUM'
    elif score >= config.THRESHOLD_LOW:
        match_type = '⚪ LOW'
    else:
        return None
    
    return {
        'score': round(score),
        'match_type': match_type,
        'yearly_row': yearly_row,
        'col1_pct': col1_pct,
        'col2_match': col2_match,
        'col3_pct': col3_pct,
        'col3_match': False,
        'col4_pct': col4_pct,
        'col4_match': False,
        'is_exact': False
    }

def find_all_matches(daily_row, candidates, name_col, mobile_col, addr_col, extra_col):
    """Find ALL matches from candidates that meet criteria"""
    matches = []
    
    for yearly_row in candidates:
        # Try exact match first
        exact = check_exact_match(daily_row, yearly_row, name_col, mobile_col, addr_col, extra_col)
        if exact:
            matches.append(exact)
            continue # If exact match found, skip fuzzy check for this specific row
        
        # Try fuzzy match
        fuzzy = check_fuzzy_match(daily_row, yearly_row, name_col, mobile_col, addr_col, extra_col)
        if fuzzy:
            matches.append(fuzzy)
    
    # Sort matches by score descending (best matches first)
    matches.sort(key=lambda x: x['score'], reverse=True)
    
    return matches
