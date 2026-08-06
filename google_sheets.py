import gspread
from google.oauth2.service_account import Credentials
import pandas as pd
import numpy as np
import time

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]


def authenticate_google_sheets(credentials_source):
    """Authenticate with Google Sheets API.

    credentials_source: path to a service-account JSON file, or a dict
    (e.g. from st.secrets / uploaded JSON).
    """
    if isinstance(credentials_source, dict):
        creds = Credentials.from_service_account_info(
            credentials_source, scopes=SCOPES
        )
    else:
        creds = Credentials.from_service_account_file(
            credentials_source, scopes=SCOPES
        )
    return gspread.authorize(creds)


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

    seen = {}
    unique_headers = []
    for h in headers:
        name = h if h else "Column"
        if name in seen:
            seen[name] += 1
            unique_headers.append(f"{name}_{seen[name]}")
        else:
            seen[name] = 0
            unique_headers.append(name)

    return pd.DataFrame(data_rows, columns=unique_headers)


def create_or_clear_sheet(spreadsheet, sheet_name):
    """Create new sheet or clear existing one"""
    try:
        worksheet = spreadsheet.worksheet(sheet_name)
        worksheet.clear()
        return worksheet
    except gspread.WorksheetNotFound:
        return spreadsheet.add_worksheet(title=sheet_name, rows=1000, cols=30)


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
