# MyFinancePlace

Personal finance management app — from household budgeting to investment portfolios.

## Features

| Module | Description |
|---|---|
| **Dashboard** | KPI cockpit — net worth, income, expenses, savings rate |
| **Accounting** | Balance Sheet, Income Statement, Cash Flow Statement |
| **Lifestyle** | Expenses by category, trends, personal goals |
| **Transactions** | Full CRUD with tags, categories, counterparties, recurring entries |
| **Portfolio** | Stocks, ETFs, crypto, bonds, savings accounts |
| **Debt** | Mortgages and loans with amortization schedules |
| **Documents** | Archive linked to transactions, with fiscal-year tagging |
| **Snapshots** | Point-in-time financial snapshots for historical comparison |
| **Export** | CSV, JSON, PDF, tax export by year, Excel import |

## Quick Start

```bash
# 1. Create and activate a virtual environment
python -m venv .venv
.venv\Scripts\activate        # Windows
source .venv/bin/activate     # macOS/Linux

# 2. Install dependencies
pip install -r requirements.txt

# 3. Set environment variables (optional)
cp .env.example .env         # edit SECRET_KEY

# 4. Run the development server
python run.py
```

Open `http://localhost:5000` in your browser.

## Project Structure

```
MyFinancePlace/
├── run.py                  # Entry point
├── config.py               # Environment configurations
├── requirements.txt
├── app/
│   ├── __init__.py         # App factory (create_app)
│   ├── routes/             # One Blueprint per module
│   ├── templates/          # Jinja2 HTML templates
│   └── static/
│       ├── css/
│       │   ├── theme.css   # ← All colors live here
│       │   └── main.css    # Layout and components
│       └── js/
│           ├── charts.js   # Chart.js helpers
│           └── main.js     # UI interactions
```

## Theming

All colors are CSS variables defined in **`app/static/css/theme.css`**.
To retheme the entire app, only edit that one file — no other file needs changing.

## Tech Stack

- **Backend**: Python / Flask
- **Templates**: Jinja2
- **Charts**: Chart.js 4 (CDN)
- **Icons**: Bootstrap Icons (CDN)
- **Fonts**: Inter (Google Fonts)
- **CSS**: Custom (no frameworks — pure CSS variables)
