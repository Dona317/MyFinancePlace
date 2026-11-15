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

## 2. Project Structure

```bash
app/
├── __init__.py         # Application factory (create_app)
├── routes/             # HTTP layer — one file per module
│   ├── auth.py
│   ├── transactions.py
│   ├── portfolio.py
│   ├── accounting.py
│   └── ...
├── schemas/            # APIFlask input/output schemas — one file per module
│   ├── __init__.py
│   ├── common.py       # Shared schemas (SuccessOut, DeleteOut, ...)
│   ├── auth.py
│   ├── transaction.py
│   ├── portfolio.py
│   └── ...
├── services/           # Business logic (you create this)
├── models/             # ORM models (you create this)
├── repositories/       # DB access abstraction (optional)
├── static/
└── templates/
```

### Responsibility of each layer

| Layer | What goes here | What does NOT go here |
|---|---|---|
| `routes/` | Parse request, call service, return response | Business logic, DB queries |
| `schemas/` | Input validation, output serialization | Logic of any kind |
| `services/` | Calculations, rules, orchestration | HTTP concerns |
| `models/` | DB table definitions | Business rules |

### Example flow for "add a transaction":

```bash
POST /transactions/api
  → schemas/transaction.py    (APIFlask validates + deserializes the JSON body)
  → routes/transactions.py    (receives clean `body` dict, calls service)
  → services/transaction_service.py  (applies business rules)
  → models/transaction.py     (persists to DB)
  → schemas/transaction.py    (APIFlask serializes the response)
  → 201 JSON response
```

---

## 3. REST API Layer (APIFlask + Schemas)

This project uses **APIFlask**, which extends Flask with automatic input validation,
output serialization, and Swagger UI generation at `/swagger`.

### How it works

You define a **Schema** class with typed fields. Then you attach it to a route with
`@bp.input` (validates the request) or `@bp.output` (serializes the response).
APIFlask handles errors automatically — a bad request returns a 422 with a clear message.

```bash
Request JSON  →  @bp.input(MySchema)  →  validated dict injected as arg
                                          ↓
                                       route function runs
                                          ↓
Response dict  →  @bp.output(MySchema)  →  serialized JSON response
```

### Schema file: `app/schemas/common.py`

Schemas shared across multiple modules:

```python
from apiflask import Schema
from apiflask.fields import Boolean, String, Integer

class SuccessOut(Schema):
    success    = Boolean()
    message    = String()

class DeleteOut(Schema):
    success    = Boolean()
    deleted_id = Integer()
```

### Schema file: `app/schemas/transaction.py`

```python
from apiflask import Schema
from apiflask.fields import Boolean, String, Integer, Float, Date, List, Nested
from apiflask.validators import OneOf, Range

class TransactionIn(Schema):
    title    = String(required=True,  metadata={"example": "Grocery shopping"})
    amount   = Float(required=True,   validate=Range(min=0.01), metadata={"example": 49.99})
    date     = Date(required=True,    metadata={"example": "2026-06-15"})
    category = String(required=True,  metadata={"example": "Food"})
    type     = String(required=True,  validate=OneOf(["income", "expense"]))
    notes    = String(load_default="")

class TransactionOut(Schema):
    id       = Integer()
    title    = String()
    amount   = Float()
    date     = Date()
    category = String()
    type     = String()
    notes    = String()

class TransactionListOut(Schema):
    success      = Boolean()
    transactions = List(Nested(TransactionOut))
    total        = Integer()
```

### Route file: `app/routes/transactions.py`

There are **two separate sections** in each route file: HTML routes (for Jinja templates)
and REST API routes (for JSON). They coexist in the same Blueprint.

```python
from app.schemas.transaction import TransactionIn, TransactionOut, TransactionListOut
from app.schemas.common import DeleteOut

# ── HTML routes — no schemas, return render_template ──────────────────────────

@transactions_bp.route("/")
def index():
    return render_template("transactions/index.html", transactions=[])


# ── REST API routes — use @bp.input / @bp.output ──────────────────────────────

@transactions_bp.get("/api")
@transactions_bp.output(TransactionListOut)
def api_list():
    transactions = []  # TODO: fetch from DB
    return {"success": True, "transactions": transactions, "total": 0}


@transactions_bp.post("/api")
@transactions_bp.input(TransactionIn, arg_name="body")
@transactions_bp.output(TransactionOut, status_code=201)
def api_create(body):
    new_tx = {"id": 1, **body}  # TODO: save to DB
    return new_tx


@transactions_bp.get("/api/<int:tx_id>")
@transactions_bp.output(TransactionOut)
def api_get(tx_id):
    transaction = {}  # TODO: fetch from DB
    return transaction


@transactions_bp.put("/api/<int:tx_id>")
@transactions_bp.input(TransactionIn, arg_name="body")
@transactions_bp.output(TransactionOut)
def api_update(tx_id, body):
    updated_tx = {"id": tx_id, **body}  # TODO: update in DB
    return updated_tx


@transactions_bp.delete("/api/<int:tx_id>")
@transactions_bp.output(DeleteOut)
def api_delete(tx_id):
    return {"success": True, "deleted_id": tx_id}  # TODO: delete from DB
```

### URL convention

| Action | Method | URL |
|---|---|---|
| List all | GET | `/transactions/api` |
| Create | POST | `/transactions/api` |
| Get one | GET | `/transactions/api/<id>` |
| Update | PUT | `/transactions/api/<id>` |
| Delete | DELETE | `/transactions/api/<id>` |

### How to add a new module (e.g. portfolio)

1. Create `app/schemas/portfolio.py` with `PortfolioIn`, `PortfolioOut`, etc.
2. Open `app/routes/portfolio.py` and import from `app.schemas.portfolio`.
3. Add the `# REST API routes` block following the same pattern.
4. No changes needed in `app/__init__.py` — the Blueprint is already registered.
5. Visit `/swagger` to verify the new endpoints appear.

### Field types reference

| APIFlask field | Python type | Notes |
|---|---|---|
| `String()` | `str` | |
| `Integer()` | `int` | |
| `Float()` | `float` | |
| `Boolean()` | `bool` | |
| `Date()` | `datetime.date` | serializes to `"YYYY-MM-DD"` |
| `DateTime()` | `datetime.datetime` | serializes to ISO 8601 |
| `List(Nested(X))` | `list[dict]` | nested object list |

### Common validators

```python
from apiflask.validators import Length, Range, OneOf, Regexp

name  = String(validate=Length(min=1, max=100))
price = Float(validate=Range(min=0))
type  = String(validate=OneOf(["income", "expense"]))
```

---

## 4. Database — PostgreSQL via Docker

The project uses **PostgreSQL** running in Docker. The container is defined in `docker-compose.yml` at the project root.

### Connection details

| Parameter | Value |
|---|---|
| Host | `localhost` |
| Port | `5332` (mapped from container's 5432) |
| Database | `myfinanceplace` |
| User | `sa` |
| Password | `Pa55w0rd` |

### Start / stop the database

```powershell
# Start (detached)
docker compose up -d

# Stop
docker compose down

# Stop and delete the volume (wipes all data)
docker compose down -v
```

### Connect with psql (inside the container)

```powershell
# connect_to_postgres_db.ps1
docker compose exec db psql -U sa -d myfinanceplace
```

Or run the helper script directly:

```powershell
.\connect_to_postgres_db.ps1
```

### Connect from the Flask app

Dependencies are already in `requirements.txt` (`Flask-SQLAlchemy`, `Flask-Migrate`, `psycopg2-binary`). Just install them:

```bash
pip install -r requirements.txt
```

Add to `.env` (never commit this file):

```
DATABASE_URL=postgresql://sa:Pa55w0rd@localhost:5332/myfinanceplace
```

The `config.py` already reads `DATABASE_URL` and falls back to the local Docker instance:

```python
SQLALCHEMY_DATABASE_URI = os.environ.get("DATABASE_URL") or "postgresql://sa:Pa55w0rd@localhost:5332/myfinanceplace"
SQLALCHEMY_TRACK_MODIFICATIONS = False
```

### Architecture — avoiding circular imports

`db` and `migrate` live in `app/extensions.py` (not in `app/__init__.py`). This means models and routes can import `db` from `extensions` without triggering a circular import chain.

```
app/extensions.py   ← db, migrate created here
app/__init__.py     ← db.init_app(app), migrate.init_app(app, db)
app/models/*.py     ← from app.extensions import db
```

### Adding a model

Create a file in `app/models/`. Example — `app/models/transaction.py`:

```python
from app.extensions import db

class Transaction(db.Model):
    __tablename__ = "transactions"

    id           = db.Column(db.Integer,        primary_key=True)
    date         = db.Column(db.Date,           nullable=False)
    title        = db.Column(db.String(255),    nullable=False)
    amount       = db.Column(db.Numeric(12, 2), nullable=False)
    category     = db.Column(db.String(100))
    type         = db.Column(db.String(20))     # "income" | "expense"
    notes        = db.Column(db.Text)
    is_recurring = db.Column(db.Boolean,        default=False)
```

Then import it in `app/models/__init__.py` so SQLAlchemy registers it:

```python
from .transaction import Transaction
```

### Migration workflow

This is the daily workflow whenever you add or change a model.

```powershell
# One-time setup (already done — migrations/ folder already exists)
flask db init

# After every model change:
flask db migrate -m "describe what changed"   # generates a new file in migrations/versions/
flask db upgrade                               # applies it to the database
```

To roll back the last migration:

```powershell
flask db downgrade
```

To see which migration is currently applied:

```powershell
flask db current
```

To see the full migration history:

```powershell
flask db history
```

> **Important:** always commit the generated `migrations/versions/*.py` files to git. They are the source of truth for the database schema.

---

## 5. Authentication

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

## 6. Passing Data to Templates

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

## 7. Flash Messages

Use Flask's built-in flash system for user feedback:

```python
from flask import flash, redirect, url_for

flash("Transazione aggiunta con successo!", "success")  # categories: success, error, warning, info
return redirect(url_for("transactions.index"))
```

The `base.html` template already renders flash messages automatically.

---

## 8. Forms and CSRF Protection

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

> **Note:** Flask-WTF forms are for HTML form submissions. For JSON REST endpoints use
> APIFlask schemas (`@bp.input`) instead — they serve different purposes.

---

## 9. Coding Standards

- **Route files**: only HTTP concerns (parse request, call service, return response).
- **Schema files**: only field definitions and validators — no logic.
- **No business logic in templates** — compute everything in Python, pass results to the template.
- **No raw SQL in routes** — use a model or repository layer.
- **Comments**: only when the *why* is not obvious from the code itself.
- **Variable names**: English in code, Italian only in user-facing strings.
- **One Blueprint per module** — keep files small and focused.

---

## 10. Environment Variables

Create a `.env` file in the project root (never commit it):

```
SECRET_KEY=your-very-secret-key
DATABASE_URL=sqlite:///myfinanceplace.db
FLASK_ENV=development
```

Load with `python-dotenv` (already configured in `config.py`).

---

## 11. Running in Production

```bash
pip install gunicorn
gunicorn "app:create_app()" -w 4 -b 0.0.0.0:8000
```

Set `FLASK_ENV=production` and always use a real `SECRET_KEY`.
