# Developer Guide — MyFinancePlace

This document explains how to work on this Flask project following clean architecture principles.

---

## 1. Flask Fundamentals

### Application Factory

`app/__init__.py` uses the **factory pattern** (`create_app()`). This means:
- You never import a global `app` object directly.
- You can create multiple app instances (useful for testing).
- Blueprints are registered inside the factory, keeping them decoupled.

```python
# run.py
from app import create_app
app = create_app()
```

### Blueprints

Each module (transactions, portfolio, etc.) lives in its own **Blueprint** under `app/routes/`.
A Blueprint is just a mini-application with its own routes. Register it in `create_app()`:

```python
from .routes.transactions import transactions_bp
app.register_blueprint(transactions_bp)
```

---

## 2. Recommended Project Layers

Follow this separation of concerns as you add Python logic:

```
app/
├── routes/         # HTTP layer — receive request, call service, return response
├── services/       # Business logic — calculations, rules (you create this)
├── models/         # Data models / ORM definitions (you create this)
└── repositories/   # Database access abstraction (optional but clean)
```

### Example flow for "add a transaction":

```
POST /transactions/new
  → routes/transactions.py   (parse form data, validate)
  → services/transaction_service.py  (apply business rules)
  → models/transaction.py    (persist to DB)
  → redirect to transaction list
```

---

## 3. Adding a Database

Install Flask-SQLAlchemy and Flask-Migrate:

```bash
pip install Flask-SQLAlchemy Flask-Migrate
```

Add to `config.py`:
```python
SQLALCHEMY_DATABASE_URI = os.environ.get("DATABASE_URL") or "sqlite:///myfinanceplace.db"
SQLALCHEMY_TRACK_MODIFICATIONS = False
```

Initialize in `app/__init__.py`:
```python
from flask_sqlalchemy import SQLAlchemy
db = SQLAlchemy()

def create_app():
    app = Flask(__name__)
    db.init_app(app)
    ...
```

Create your first model in `app/models/transaction.py`:
```python
from app import db

class Transaction(db.Model):
    id          = db.Column(db.Integer, primary_key=True)
    date        = db.Column(db.Date, nullable=False)
    description = db.Column(db.String(255), nullable=False)
    amount      = db.Column(db.Numeric(12, 2), nullable=False)
    category    = db.Column(db.String(100))
    tags        = db.Column(db.String(255))  # store as comma-separated or use a join table
    is_recurring = db.Column(db.Boolean, default=False)
```

Run migrations:
```bash
flask db init
flask db migrate -m "Initial tables"
flask db upgrade
```

---

## 4. Authentication

Install Flask-Login:
```bash
pip install Flask-Login
```

1. Create a `User` model with `is_authenticated`, `is_active`, `get_id()` (or inherit `UserMixin`).
2. Initialize `LoginManager` in `create_app()`.
3. Protect routes with `@login_required`.
4. Implement `auth.login` and `auth.logout` in `app/routes/auth.py` (stubs already exist).

```python
from flask_login import login_required

@transactions_bp.route("/")
@login_required
def index():
    ...
```

---

## 5. Passing Data to Templates

Routes pass data as keyword arguments to `render_template()`. The template receives them as variables:

```python
# route
return render_template("transactions/index.html", transactions=tx_list)
```

```html
<!-- template -->
{% for tx in transactions %}
  <tr>...</tr>
{% endfor %}
```

For charts, serialize Python data to JSON and pass it to JavaScript:
```python
import json
chart_data = json.dumps([{"label": "Gen", "value": 1200}, ...])
return render_template("dashboard/index.html", chart_data=chart_data)
```

```html
<script>
const data = {{ chart_data | safe }};
makeLineChart('myChart', data.map(d => d.label), [{ label:'Valore', data: data.map(d => d.value) }]);
</script>
```

---

## 6. Flash Messages

Use Flask's built-in flash system for user feedback:

```python
from flask import flash, redirect, url_for

flash("Transazione aggiunta con successo!", "success")  # categories: success, error, warning, info
return redirect(url_for("transactions.index"))
```

The `base.html` template already renders flash messages automatically.

---

## 7. Forms and CSRF Protection

Install Flask-WTF (already in `requirements.txt`):

```python
from flask_wtf import FlaskForm
from wtforms import StringField, DecimalField, DateField
from wtforms.validators import DataRequired

class TransactionForm(FlaskForm):
    description = StringField("Descrizione", validators=[DataRequired()])
    amount      = DecimalField("Importo",    validators=[DataRequired()])
    date        = DateField("Data",          validators=[DataRequired()])
```

In the route:
```python
form = TransactionForm()
if form.validate_on_submit():
    # save to DB
    pass
return render_template("transactions/form.html", form=form)
```

---

## 8. Coding Standards

- **Route files**: only HTTP concerns (parse request, call service, return response).
- **No business logic in templates** — compute everything in Python, pass results to the template.
- **No raw SQL in routes** — use a model or repository layer.
- **Comments**: only when the *why* is not obvious from the code itself.
- **Variable names**: English in code, Italian only in user-facing strings.
- **One Blueprint per module** — keep files small and focused.

---

## 9. Environment Variables

Create a `.env` file in the project root (never commit it):

```
SECRET_KEY=your-very-secret-key
DATABASE_URL=sqlite:///myfinanceplace.db
FLASK_ENV=development
```

Load with `python-dotenv` (already configured in `config.py`).

---

## 10. Running in Production

```bash
pip install gunicorn
gunicorn "app:create_app()" -w 4 -b 0.0.0.0:8000
```

Set `FLASK_ENV=production` and always use a real `SECRET_KEY`.
