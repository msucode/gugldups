import gspread
from oauth2client.service_account import ServiceAccountCredentials
import pandas as pd

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
    """Read worksheet to pandas DataFrame"""
    data = worksheet.get_all_records()
    return pd.DataFrame(data)

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
    """Write DataFrame to worksheet"""
    worksheet.update([df.columns.values.tolist()] + df.values.tolist())

def delete_rows_by_indices(worksheet, row_indices):
    """Delete specific rows from worksheet"""
    # Sort in reverse to delete from bottom to top
    sorted_indices = sorted(row_indices, reverse=True)
    
    for idx in sorted_indices:
        # +2 because: +1 for header row, +1 for 1-based indexing
        worksheet.delete_rows(idx + 2)
