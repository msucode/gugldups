from rapidfuzz import fuzz
from utils import normalize, get_block_key
import config

def check_exact_match(daily_row, yearly_row, name_col, mobile_col, addr_col, extra_col):
    """Check if names match exactly and categorize by column matches"""
    daily_name = normalize(daily_row[name_col])
    yearly_name = normalize(yearly_row[name_col])
    
    if daily_name != yearly_name or daily_name == "":
        return None
    
    # Count exact matches
    mobile_match = normalize(daily_row[mobile_col]) == normalize(yearly_row[mobile_col])
    addr_match = normalize(daily_row[addr_col]) == normalize(yearly_row[addr_col])
    extra_match = normalize(daily_row[extra_col]) == normalize(yearly_row[extra_col])
    
    exact_col_count = 1  # Name always matches
    if mobile_match:
        exact_col_count += 1
    if addr_match:
        exact_col_count += 1
    if extra_match:
        exact_col_count += 1
    
    # Categorize
    if exact_col_count == 4:
        match_category = '🟢 PERFECT'
    elif exact_col_count == 3:
        match_category = '🎃 STRONG'
    elif exact_col_count == 2:
        match_category = '🤖 PARTIAL'
    else:
        match_category = '💀 WEAK'
    
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
    """Calculate fuzzy match score"""
    daily_name = normalize(daily_row[name_col])
    daily_mobile = normalize(daily_row[mobile_col])
    daily_addr = normalize(daily_row[addr_col])
    daily_extra = normalize(daily_row[extra_col])
    
    yearly_name = normalize(yearly_row[name_col])
    yearly_mobile = normalize(yearly_row[mobile_col])
    yearly_addr = normalize(yearly_row[addr_col])
    yearly_extra = normalize(yearly_row[extra_col])
    
    # Calculate similarities
    col1_pct = fuzz.token_sort_ratio(daily_name, yearly_name)
    col2_match = (daily_mobile == yearly_mobile)
    col3_pct = fuzz.token_set_ratio(daily_addr, yearly_addr)
    col3_match = (daily_addr == yearly_addr)
    col4_pct = fuzz.token_set_ratio(daily_extra, yearly_extra)
    col4_match = (daily_extra == yearly_extra)
    
    # Calculate score
    score = 0
    if col2_match:
        score += config.SCORE_COL2_WEIGHT
    score += (col1_pct / 100) * config.SCORE_COL1_WEIGHT
    score += (col3_pct / 100) * config.SCORE_COL3_WEIGHT
    score += (col4_pct / 100) * config.SCORE_COL4_WEIGHT
    
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
        'col3_match': col3_match,
        'col4_pct': col4_pct,
        'col4_match': col4_match,
        'is_exact': False
    }

def find_best_match(daily_row, candidates, name_col, mobile_col, addr_col, extra_col):
    """Find best match from candidates"""
    best_match = None
    best_score = 0
    
    for yearly_row in candidates:
        # Try exact match first
        exact = check_exact_match(daily_row, yearly_row, name_col, mobile_col, addr_col, extra_col)
        if exact and exact['score'] > best_score:
            best_match = exact
            best_score = exact['score']
            continue
        
        # Try fuzzy match
        fuzzy = check_fuzzy_match(daily_row, yearly_row, name_col, mobile_col, addr_col, extra_col)
        if fuzzy and fuzzy['score'] > best_score:
            best_match = fuzzy
            best_score = fuzzy['score']
    
    return best_match
