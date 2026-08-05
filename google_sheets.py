import gspread
from google.oauth2.service_account import Credentials
import pandas as pd
import numpy as np

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
    """Read worksheet to pandas DataFrame"""
    values = worksheet.get_all_values()
    if not values:
        return pd.DataFrame()

    headers = values[0]
    # Deduplicate headers so get_all_records-style frames don't break
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

    rows = values[1:]
    return pd.DataFrame(rows, columns=unique_headers)


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
    df_clean = df.replace([np.nan, np.inf, -np.inf, None], "", regex=False)
    df_clean = df_clean.astype(str)
    df_clean = df_clean.replace("nan", "", regex=False)
    worksheet.update(
        [df_clean.columns.values.tolist()] + df_clean.values.tolist()
    )


def delete_rows_by_indices(worksheet, row_indices):
    """Delete specific rows from worksheet"""
    sorted_indices = sorted(row_indices, reverse=True)

    for idx in sorted_indices:
        # +2 because: +1 for header row, +1 for 1-based indexing
        worksheet.delete_rows(idx + 2)
