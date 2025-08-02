# Budget Tracker

A Flask-based web application that automatically tracks expenses by processing Chase bank transaction emails and provides interactive visualizations of spending patterns.

## Features

- **Automated Email Processing**: Connects to Gmail API to fetch and parse Chase transaction emails
- **Interactive Dashboard**: Visualizes spending data with dynamic charts using Plotly
- **Category Mapping**: Automatically categorizes transactions based on merchant patterns
- **Weekly Spending Analysis**: Track weekly spending trends with stacked bar charts
- **Manual Transaction Entry**: Add transactions manually through the web interface
- **Data Export**: Export transaction data for external analysis

## Technology Stack

- **Backend**: Flask 3.0.3, Python 3.10+
- **Database**: DuckDB 1.0.0 (local SQL database)
- **Email Processing**: Gmail API with OAuth2 authentication
- **Visualizations**: Plotly 5.24.0 for interactive charts
- **Frontend**: Bootstrap 5.3.0, HTML/CSS/JavaScript

## Setup Instructions

### 1. Prerequisites

- Python 3.10 or higher
- Gmail account with API access enabled
- Google Cloud Console project with Gmail API enabled

### 2. Installation

```bash
# Clone the repository
git clone <repository-url>
cd budget_tracker

# Install dependencies
pip install -r requirements.txt
```

### 3. Google API Configuration

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Create a new project or select existing one
3. Enable Gmail API
4. Assign the gmail API/modify role to be able to read and update emails to "unread"
5. Create OAuth 2.0 credentials (Desktop application)
6. Download credentials as `credentials.json` and place in project root

### 4. Database Setup

```bash
# Initialize the database (Windows)
run_flask_app.bat

# Or manually run:
python app.py
```

### 5. Configuration Files

The application will create several JSON configuration files:

- `token.json`: OAuth tokens for Gmail API
- `categories.json`: Expense categories configuration
- `category_mapping.json`: Merchant to category mappings
- `budget.json`: Budget limits per category
- `settings.json`: Application settings
- `last_fetched_date.json`: Tracks last email processing date

## Usage

### Starting the Application

```bash
# Windows
run_flask_app.bat

# Manual start
python app.py
```

The application will be available at `http://localhost:5000`

### Processing Emails

1. Visit the dashboard at `http://localhost:5000`
2. Click "Fetch Transactions" to process new Chase emails
3. Review and categorize transactions as needed

### Manual Transaction Entry

1. Navigate to "Add Transaction" page
2. Enter transaction details (amount, merchant, category, date)
3. Submit to add to database

## Project Structure

```
budget_tracker/
├── app.py                     # Main Flask application
├── utils.py                   # Email processing and database utilities
├── requirements.txt           # Python dependencies
├── _init_db.sql              # Database schema
├── templates/
│   ├── index.html            # Main dashboard
│   ├── insert.html           # Add transaction form
│   └── update.html           # Update transaction form
├── static/                   # CSS, JS, and other static files
├── *.json                    # Configuration files
└── spend_data.db            # DuckDB database file
```

## API Endpoints

- `GET /` - Main dashboard with charts
- `POST /fetch_transactions` - Process Chase emails
- `GET /insert` - Add transaction form
- `POST /insert` - Submit new transaction
- `GET /api/weekly_category_data` - Weekly spending data API
- `GET /api/category_totals` - Category totals API

## Configuration

### Categories

Edit `categories.json` to customize expense categories:

```json
{
  "Food": ["Restaurant", "Grocery"],
  "Transportation": ["Gas", "Parking"],
  "Shopping": ["Retail", "Online"]
}
```

### Merchant Mapping

Edit `category_mapping.json` to map merchants to categories:

```json
{
  "WALMART": "Grocery",
  "SHELL": "Gas",
  "AMAZON": "Shopping"
}
```

## Troubleshooting

### Gmail API Issues

- Ensure Gmail API is enabled in Google Cloud Console
- Check that `credentials.json` is properly configured
- Re-authorize if token expires

### Database Issues

- Delete `spend_data.db` and restart to recreate database
- Check file permissions in project directory

### Chart Display Issues

- Ensure all required JavaScript libraries are loading
- Check browser console for errors
- Verify API endpoints are returning data

## Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Test thoroughly
5. Submit a pull request

## License

This project is for personal use. Please respect Gmail API terms of service and data privacy considerations.

## Security Notes

- Keep `credentials.json` and `token.json` secure and never commit to version control
- The application processes financial data - ensure proper security measures in production
- Consider encrypting sensitive configuration files for production use
