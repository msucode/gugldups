import gspread
from oauth2client.service_account import ServiceAccountCredentials
import pandas as pd
import numpy as np
import time

def authenticate_google_sheets(json_keyfile_path):
    """Authenticate with Google Sheets API"""
    scope = ['https://spreadsheets.google.com/feeds',
             'https://www.googleapis.com/auth/drive']
    
    creds = ServiceAccountCredentials.from_json_keyfile_name(json_keyfile_path, scope)
    client = gspread.authorize(creds)
    return client

def get_sheet_by_url(client, url):
    """Open sheet by URL"""
    return client.open_by_url(url)

def read_sheet_to_df(worksheet):
    """Read worksheet to pandas DataFrame - handles duplicate/empty headers"""
    raw_data = worksheet.get_all_values()
    
    if not raw_data:
        return pd.DataFrame()
        
    headers = raw_data[0]
    data_rows = raw_data[1:]
    
    return pd.DataFrame(data_rows, columns=headers)

def create_or_clear_sheet(spreadsheet, sheet_name):
    """Create new sheet or clear existing one"""
    try:
        worksheet = spreadsheet.worksheet(sheet_name)
        worksheet.clear()
        return worksheet
    except:
        worksheet = spreadsheet.add_worksheet(title=sheet_name, rows=1000, cols=30)
        return worksheet

def write_df_to_sheet(worksheet, df):
    """Write DataFrame to worksheet - handles NaN values"""
    df_clean = df.replace([np.nan, np.inf, -np.inf, None], '', regex=False)
    df_clean = df_clean.astype(str)
    df_clean = df_clean.replace('nan', '', regex=False)
    
    worksheet.update([df_clean.columns.values.tolist()] + df_clean.values.tolist())

def delete_rows_by_indices(worksheet, row_indices):
    """Delete specific rows from worksheet using a single batch API request"""
    if not row_indices:
        return
        
    # Deduplicate and sort in reverse to delete from bottom to top safely
    sorted_indices = sorted(list(set(row_indices)), reverse=True)
    
    requests = []
    for idx in sorted_indices:
        requests.append({
            "deleteDimension": {
                "range": {
                    "sheetId": worksheet.id,
                    "dimension": "ROWS",
                    "startIndex": idx + 1,
                    "endIndex": idx + 2
                }
            }
        })
        
    if requests:
        body = {"requests": requests}
        worksheet.spreadsheet.batch_update(body)
