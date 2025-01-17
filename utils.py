import os
import json
import base64
import re
import duckdb
import datetime
from datetime import datetime, timedelta

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

# ------------------- Gmail API Authentication and Data Extraction -------------------

SCOPES = ['https://www.googleapis.com/auth/gmail.modify']

def authenticate_gmail():
    creds = None
    if os.path.exists('token.json'):
        creds = Credentials.from_authorized_user_file('token.json', SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file('credentials.json', SCOPES)
            creds = flow.run_local_server(port=0)
        with open('token.json', 'w') as token:
            token.write(creds.to_json())
    try:
        service = build('gmail', 'v1', credentials=creds)
    except Exception as e:
        print(f"ERROR: {e}")
    return service

def fetch_unread_emails(service):
    # Get today's date and yesterday's date
    # today = datetime.now().strftime('%Y/%m/%d')
    # yesterday = (datetime.now() - timedelta(2)).strftime('%Y/%m/%d')
    format_change='2021/07/21'
    # Modify the query to filter emails by date range
    query = f'after:{format_change} is:unread'
    
    # Replace 'Label_XXXXXXX' with your actual label ID for "Chase" folder
    try:
        results = service.users().messages().list(userId='me', labelIds=['Label_12'], q=query).execute()
    except Exception as e:
        print(f"ERROR: {e}")
    messages = results.get('messages', [])
    return messages

def get_email_data(service, message_id):
    message = service.users().messages().get(userId='me', id=message_id, format='full').execute()
    payload = message['payload']
    headers = payload.get('headers', [])

    # Extract subject line
    subject = next((header['value'] for header in headers if header['name'] == 'Subject'), None)

    # Regex to match the pattern 'Your $2.90 transaction with MTA*NYCT PAYGO'
    if subject:
        match = re.search(r'Your \$([\d,]+\.\d{2}) transaction with (.+)', subject)
        if not match:
            # Subject line does not match expected format
            print(f"Skipping email. Subject line does not match expected format: {subject}")
            mark_email_as_read(service, message_id)
            return None

        amount = match.group(1)
        description = match.group(2)
    else:
        # No subject line found
        print("Skipping email. No subject line found.")
        mark_email_as_read(service, message_id)
        return None

    # Extract date with time zone offset
    date_header = next((header['value'] for header in headers if header['name'] == 'Date'), None)
    if date_header:
        # Remove '(UTC)' and any other text in parentheses
        clean_date_header = re.sub(r'\s*\(.*\)', '', date_header)
        email_date = datetime.strptime(clean_date_header, '%a, %d %b %Y %H:%M:%S %z')
    else:
        email_date = None
    
    return {
        'date': email_date,
        'amount': amount,
        'description': description
    }

def mark_email_as_read(service, message_id):
    service.users().messages().modify(userId='me', id=message_id, body={'removeLabelIds': ['UNREAD']}).execute()

def list_labels(service):
    results = service.users().labels().list(userId='me').execute()
    labels = results.get('labels', [])
    for label in labels:
        print(f"Label name: {label['name']}, Label ID: {label['id']}")

# ------------------- Data Storage in DuckDB -------------------

def store_data_in_duckdb(data, category_map):
    conn = duckdb.connect('spend_data.db')
    
    # Load predefined categories
    categories = load_categories()
    
    # Apply category mapping
    category = 'Uncategorized'
    for keyword, cat in category_map.items():
        if data['description'] is not None and keyword.lower() in data['description'].lower():
            # Only use the mapped category if it exists in our predefined categories
            if cat in categories:
                category = cat
            break
    
    # Insert data into the table
    try:
        if data['date'] and data['amount']:
            amount_value = float(data['amount'].replace('$', '').replace(',', ''))
            conn.execute('''
                INSERT INTO transactions (date, amount, description, category)
                VALUES (?, ?, ?, ?)
            ''', [data['date'], amount_value, data['description'], category])
    except Exception as e:
        print(f"Error storing data: {e}")
    finally:
        conn.close()

# ------------------- Data Query and Visualization -------------------

def query_monthly_spend():
    conn = duckdb.connect('spend_data.db')
    result = conn.execute('''
        SELECT
            date_trunc('month', date) AS month,
            SUM(amount) AS total_amount
        FROM transactions
        GROUP BY month
        ORDER BY month
    ''').fetchall()
    conn.close()
    return result

def query_yearly_spend():
    conn = duckdb.connect('spend_data.db')
    result = conn.execute('''
        SELECT
            date_trunc('year', date) AS year,
            SUM(amount) AS total_amount
        FROM transactions
        GROUP BY year
        ORDER BY year
    ''').fetchall()
    conn.close()
    return result

def query_yearly_spend_by_cat():
    # curYear = datetime.now().year
    conn = get_connection()
    result = conn.execute('''
        SELECT
            date_part('year', date) AS year,
            category, 
            SUM(amount) AS total_amount
        FROM transactions
        WHERE category != 'Uncategorized'
        AND category != 'Coffee'
        GROUP BY year, category
    ''').fetch_df()
    conn.close()
    return result

def query_spend_by_hour():
    conn = get_connection()

    # Query to get the average spend by hour
    query = '''
    SELECT 
        CAST(strftime(date, '%H') AS INT) AS hour,
        AVG(CAST(amount AS FLOAT)) AS avg_spend
    FROM transactions
    GROUP BY hour
    ORDER BY hour
    '''
    # Execute the query and fetch the data
    df = conn.execute(query).fetch_df()
    conn.close()

    return df

# Connect to DuckDB
def get_connection():
    return duckdb.connect('spend_data.db')

# ------ init db ------
def _init_db():
    service = authenticate_gmail()
    messages = fetch_unread_emails(service)

    # Load category mapping
    with open('category_mapping.json') as f:
        category_map = json.load(f)
    
    # Process each email
    for msg in messages:
        email_data = get_email_data(service, msg['id'])
        if email_data is not None:
            try:
                store_data_in_duckdb(email_data, category_map)
            except Exception as e:
                print(f"{e}")
        mark_email_as_read(service, msg['id'])

# ---- update category column with new values 
def _load_csv_duckdb(csv_file_path, table_name, db_file_path=':memory:'):
    # Connect to the DuckDB database (default is in-memory)
    conn = duckdb.connect("spend_data.db")

    # Create the table and load the CSV file into the table
    query='''
        CREATE TABLE IF NOT EXISTS transactions (
            date TIMESTAMP,
            amount DOUBLE,
            description TEXT,
            category TEXT,
            notes TEXT,
            UNIQUE(date, description)
        )
    '''
    conn.execute(query)

    # Create the table and load the CSV file into the table
    query = f"""
    CREATE TABLE {table_name} AS 
    SELECT * FROM read_csv_auto('{csv_file_path}');
    """
    conn.execute(query)

    # Optionally: Verify the data is loaded
    result = conn.execute(f"SELECT * FROM {table_name} LIMIT 5").fetchall()
    print(f"First 5 rows from {table_name}:")
    for row in result:
        print(row)

    # Close the connection
    conn.close()



def query_current_year_spend_by_cat(year):
    con = get_connection()
    query = f"""
    SELECT category, amount
    FROM transactions
    WHERE date_part('year', date) = {year}
    """
    df = con.execute(query).fetchdf()
    con.close()
    return df

def get_current_year_stats(year):
    con = get_connection()
    query = f"""
    SELECT 
        SUM(amount) as total_spend,
        AVG(amount) as avg_transaction,
        COUNT(*) as transaction_count,
        MAX(amount) as max_transaction,
        (SELECT description FROM transactions WHERE amount = MAX(amount) AND date_part('year', date) = {year} LIMIT 1) as max_transaction_description
    FROM transactions
    WHERE date_part('year', date) = {year}
    """
    result = con.execute(query).fetchone()
    con.close()
    return {
        'total_spend': result[0],
        'avg_transaction': result[1],
        'transaction_count': result[2],
        'max_transaction': result[3],
        'max_transaction_description': result[4]
    }

def get_previous_years_avg(current_year):
    con = get_connection()
    query = f"""
    SELECT 
        AVG(yearly_total) as avg_yearly_spend,
        AVG(yearly_avg) as avg_transaction,
        AVG(yearly_count) as avg_transaction_count,
        AVG(yearly_max) as avg_max_transaction
    FROM (
        SELECT 
            date_part('year', date) as year,
            SUM(amount) as yearly_total,
            AVG(amount) as yearly_avg,
            COUNT(*) as yearly_count,
            MAX(amount) as yearly_max
        FROM transactions
        WHERE date_part('year', date) < {current_year}
        GROUP BY year
    )
    """
    result = con.execute(query).fetchone()
    con.close()
    return {
        'avg_yearly_spend': result[0],
        'avg_transaction': result[1],
        'avg_transaction_count': result[2],
        'avg_max_transaction': result[3]
    }

def get_category_spend(year):
    con = get_connection()
    query = f"""
    SELECT 
        category,
        SUM(amount) as total_spend
    FROM transactions
    WHERE date_part('year', date) = {year}
    GROUP BY category
    ORDER BY total_spend DESC
    """
    result = con.execute(query).fetchall()
    con.close()
    return {row[0]: row[1] for row in result}

def get_category_spend_avg(current_year):
    con = get_connection()
    query = f"""
    SELECT 
        category,
        AVG(yearly_total) as avg_spend
    FROM (
        SELECT 
            date_part('year', date) as year,
            category,
            SUM(amount) as yearly_total
        FROM transactions
        WHERE date_part('year', date) < {current_year}
        GROUP BY year, category
    )
    GROUP BY category
    """
    result = con.execute(query).fetchall()
    con.close()
    return {row[0]: row[1] for row in result}

def get_top_monthly_subscriptions(year):
    con = get_connection()
    query = f"""
    SELECT 
        description,
        SUM(amount) as total_amount,
        COUNT(*) as occurrence_count
    FROM transactions
    WHERE date_part('year', date) = {year}
    AND category = 'Monthly'
    GROUP BY description
    ORDER BY total_amount DESC
    LIMIT 5
    """
    result = con.execute(query).fetchall()
    con.close()
    return result

def query_transaction_details(year, category):
    con = get_connection()
    query = f"""
    SELECT date, description, amount
    FROM transactions
    WHERE date_part('year', date) = {year}
    AND category = '{category}'
    ORDER BY amount DESC
    """
    result = con.execute(query).fetchall()
    con.close()
    return [{'date': row[0].strftime('%Y-%m-%d'), 'description': row[1], 'amount': row[2]} for row in result]

def query_top_transactions_for_month(year_month):
    conn = get_connection()
    query = """
    SELECT date, description, amount
    FROM transactions
    WHERE strftime('%Y-%m', date) = ?
    ORDER BY amount DESC
    LIMIT 8
    """
    print(f"Executing query for {year_month}")
    result = conn.execute(query, [year_month]).fetchall()
    print(f"Query result: {result}")
    conn.close()
    return [{'date': row[0].strftime('%Y-%m-%d'), 'description': row[1], 'amount': float(row[2])} for row in result]

def load_categories():
    """Load categories from JSON file"""
    try:
        with open('categories.json', 'r') as f:
            data = json.load(f)
            return data['categories']
    except Exception as e:
        print(f"Error loading categories: {e}")
        return ["Uncategorized"]  # fallback category

def get_sankey_data(year):
    """Get salary and category spending data for Sankey diagram"""
    con = get_connection()
    
    # Get spending by category
    query = f"""
    SELECT 
        category,
        SUM(amount) as total_spend
    FROM transactions
    WHERE date_part('year', date) = {year}
    AND category != 'Investments'
    GROUP BY category
    """
    spend_data = con.execute(query).fetchall()
    con.close()

    # Get salary data
    try:
        with open('salary_map.json', 'r') as f:
            salary_data = json.load(f)
            salary = float(salary_data.get(str(year), 0))
    except Exception as e:
        print(f"Error loading salary data: {e}")
        salary = 0

    return salary, spend_data

def load_budget_data():
    """Load budget limits from JSON file"""
    try:
        with open('budget.json', 'r') as f:
            data = json.load(f)
            return data['monthly_budgets']
    except Exception as e:
        print(f"Error loading budget data: {e}")
        return {}

def get_current_month_spend_by_category():
    """Get current month's spending by category"""
    current_date = datetime.now()
    con = get_connection()
    query = """
    SELECT 
        category,
        SUM(amount) as total_spend
    FROM transactions
    WHERE date_part('year', date) = ?
    AND date_part('month', date) = ?
    AND category NOT IN ('Housing', 'Utilities')
    GROUP BY category
    """
    result = con.execute(query, [current_date.year, current_date.month]).fetchall()
    con.close()
    return {row[0]: float(row[1]) for row in result}

if __name__ == "__main__":
    ## init db
    _init_db()