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

- Open `http://localhost:5000` in your browser.
- The API swagger documentation: `http://localhost:5000/swagger`

## How to Commit Changes to the Project

1. Before starting a new task, you need to switch to the main branch (located at the bottom left) and pull (download) the latest version of the main branch.
2. Select “main” at the bottom left of the VS Code window; a prompt will appear at the top. Select “+ Create new Branch.”
3. In the “+ Create new Branch” window, enter the branch name (a title representing the task).
4. I navigate to the tree view section (similar to the Git icon), the third one at the top left, and commit the changes by entering a description of the modifications made, e g., “Code Refactoring,” “Update Class ...”
5. When the task is complete, proceed to publish the branch
6. Create the “Pull Request”
7. Request approval for the “Pull Request”
8. Once approved, click “Merge”

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
