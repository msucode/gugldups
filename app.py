import streamlit as st
import pandas as pd
from datetime import datetime
from utils import convert_to_csv_url, build_yearly_index, get_block_key
from matcher import find_best_match
import config

st.title("Patient Duplicate Finder")

yearly_url = st.text_input("Yearly Database Sheet URL")
daily_url = st.text_input("Today's Linelist URL")

if st.button("Load Sheets"):
    if yearly_url and daily_url:
        try:
            df_yearly = pd.read_csv(convert_to_csv_url(yearly_url))
            df_daily = pd.read_csv(convert_to_csv_url(daily_url))
            
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
    
    if st.button("🔍 Find Duplicates"):
        df_yearly = st.session_state['df_yearly']
        df_daily = st.session_state['df_daily']
        
        st.info("Building index...")
        yearly_blocks = build_yearly_index(df_yearly, mobile_col)
        
        st.info("Comparing...")
        
        perfect_duplicate_ids = set()
        all_match_results = []
        
        for i, daily_row in df_daily.iterrows():
            block_key = get_block_key(daily_row[mobile_col])
            candidates = yearly_blocks.get(block_key, [])
            
            best_match = find_best_match(daily_row, candidates, name_col, mobile_col, addr_col, extra_col)
            
            # Track PERFECT duplicates
            if best_match and best_match['match_type'] == '🟢 PERFECT':
                perfect_duplicate_ids.add(i)
            
            # Store ALL matches for duplicate file (comparison view)
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
        
        # DUPLICATE FILE: All match comparisons
        df_duplicate_comparisons = pd.DataFrame(all_match_results) if all_match_results else pd.DataFrame()
        
        # NEW RECORDS FILE: Original daily records EXCEPT perfect duplicates
        df_new_records = df_daily[~df_daily.index.isin(perfect_duplicate_ids)]
        
        # Store in session state
        st.session_state['df_duplicate_comparisons'] = df_duplicate_comparisons
        st.session_state['df_new_records'] = df_new_records
        st.session_state['perfect_count'] = len(perfect_duplicate_ids)
        st.session_state['files_ready'] = True
        
        st.success(f"✅ {len(perfect_duplicate_ids)} PERFECT duplicates excluded | {len(df_new_records)} records to upload")
        
        # Display results
        if not df_duplicate_comparisons.empty:
            perfect = df_duplicate_comparisons[df_duplicate_comparisons['Match_Type'] == '🟢 PERFECT']
            others = df_duplicate_comparisons[df_duplicate_comparisons['Match_Type'] != '🟢 PERFECT']
            
            if len(perfect) > 0:
                with st.expander(f"🟢 Perfect Duplicates - Excluded from Upload ({len(perfect)})"):
                    st.dataframe(perfect, use_container_width=True)
            
            if len(others) > 0:
                st.subheader(f"📋 Partial/Fuzzy Matches - Included in Upload ({len(others)})")
                st.dataframe(others, use_container_width=True)
        
        if len(df_new_records) > 0:
            with st.expander(f"✨ Records with No Match ({len(df_daily) - len(all_match_results)})"):
                st.write("These have no match in yearly database")

# Download buttons - always visible if files are ready
if st.session_state.get('files_ready', False):
    st.markdown("---")
    st.subheader("📂 Download Files")
    
    today = datetime.now()
    date_str = today.strftime("%d_%m_%Y")
    
    duplicates_filename = f"{date_str}_possibleDuplicate.csv"
    new_records_filename = f"{date_str}_DailyLinelist.csv"
    
    col_metrics = st.columns(3)
    with col_metrics[0]:
        st.metric("Perfect Duplicates", st.session_state.get('perfect_count', 0))
    with col_metrics[1]:
        st.metric("To Upload", len(st.session_state['df_new_records']))
    with col_metrics[2]:
        st.metric("Match Details", len(st.session_state['df_duplicate_comparisons']))
    
    col_btn = st.columns(2)
    
    with col_btn[0]:
        if not st.session_state['df_duplicate_comparisons'].empty:
            st.download_button(
                "📥 Download Match Details",
                st.session_state['df_duplicate_comparisons'].to_csv(index=False),
                duplicates_filename,
                key='dup',
                help="All matches for review (Perfect, Strong, Partial, Fuzzy)"
            )
        else:
            st.info("No matches to download")
    
    with col_btn[1]:
        if not st.session_state['df_new_records'].empty:
            st.download_button(
                "📥 Download New Records",
                st.session_state['df_new_records'].to_csv(index=False),
                new_records_filename,
                key='new',
                help="Records to upload (excludes only Perfect duplicates)"
            )
        else:
            st.info("No new records")
