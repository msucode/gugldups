import gspread
from oauth2client.service_account import ServiceAccountCredentials
import pandas as pd
import numpy as np

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
    # Fetch all raw data to bypass get_all_records() strictness
    raw_data = worksheet.get_all_values()
    
    # Check if the sheet is empty
    if not raw_data:
        return pd.DataFrame()
        
    # The first row is the header, the rest is the actual data
    headers = raw_data[0]
    data_rows = raw_data[1:]
    
    # Create and return a Pandas DataFrame
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
    # Replace NaN, None, inf with empty string
    df_clean = df.replace([np.nan, np.inf, -np.inf, None], '', regex=False)
    
    # Convert all values to strings to avoid JSON issues
    df_clean = df_clean.astype(str)
    
    # Replace 'nan' strings with empty strings
    df_clean = df_clean.replace('nan', '', regex=False)
    
    # Write to sheet
    worksheet.update([df_clean.columns.values.tolist()] + df_clean.values.tolist())

def delete_rows_by_indices(worksheet, row_indices):
    """Delete specific rows from worksheet using a single batch API request to avoid 429 Quota errors"""
    if not row_indices:
        return
        
    # Sort in reverse to delete from bottom to top safely
    sorted_indices = sorted(row_indices, reverse=True)
    
    requests = []
    for idx in sorted_indices:
        # Google Sheets API uses 0-based indexing for dimensions.
        # df index 0 is row 2 in the sheet. In 0-based dimension indexing, row 2 is index 1.
        # So start index is idx + 1, end index is idx + 2 (exclusive).
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
