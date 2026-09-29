from apiflask import APIFlask
from flask import render_template, request
from jinja2 import Undefined
from config import config
from .routes.settings import current_settings, module_setting
from .extensions import db, migrate


def create_app(config_name="default"):
    app = APIFlask(
        __name__,
        title='MyFinancePlace | API',
        version='1.0.0',
        docs_path='/swagger'
    )
    app.config.from_object(config[config_name])
    config[config_name].init_app(app)  # production: SECRET_KEY check, ProxyFix, logging to stdout

    # No limits on request size: large statements and previews with thousands of rows must go through.
    # (Newer Flask/Werkzeug versions default to 1000 form fields / 500 KB per form; switch those off.)
    class UnlimitedRequest(app.request_class):
        max_form_memory_size = None
        max_form_parts = None

    app.request_class = UnlimitedRequest

    db.init_app(app)
    migrate.init_app(app, db)

    from . import models  # noqa: F401 — ensures models are registered with SQLAlchemy
    from .services import currency  # noqa: F401 — fills transactions.amount_base on save
    from .services import display, notifications


    app.config["DESCRIPTION"] = """
    REST API per MyFinancePlace.
    """

    app.config["CONTACT"] = {
        "name": "MyFinancePlace",
        "email": "dennisturco@gmail.com"
    }

    # app.config["LICENSE"] = {
    #     "name": "Proprietary"
    # }


    # ── Register blueprints ────────────────────────────────────────────────────
    from .routes.auth import auth_bp
    from .routes.dashboard import dashboard_bp
    from .routes.accounting import accounting_bp
    from .routes.lifestyle import lifestyle_bp
    from .routes.transactions import transactions_bp
    from .routes.portfolio import portfolio_bp
    from .routes.debt import debt_bp
    from .routes.documents import documents_bp
    from .routes.snapshots import snapshots_bp
    from .routes.export import export_bp
    from .routes.settings import settings_bp
    from .routes.insurance import insurance_bp
    from .routes.forecast import forecast_bp
    from .routes.accounts import accounts_bp
    from .routes.notifications import notifications_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(dashboard_bp)
    app.register_blueprint(accounting_bp)
    app.register_blueprint(lifestyle_bp)
    app.register_blueprint(transactions_bp)
    app.register_blueprint(portfolio_bp)
    app.register_blueprint(debt_bp)
    app.register_blueprint(documents_bp)
    app.register_blueprint(snapshots_bp)
    app.register_blueprint(export_bp)
    app.register_blueprint(settings_bp)
    app.register_blueprint(insurance_bp)
    app.register_blueprint(forecast_bp)
    app.register_blueprint(accounts_bp)
    app.register_blueprint(notifications_bp)

    # ── Template filters ───────────────────────────────────────────────────────
    # Amounts, numbers and dates follow Settings → Visualizzazione (services.display)
    @app.template_filter("money")
    def money(value, symbol=None):
        """1234.5 → '€ 1.234,50' (base currency symbol unless one is given, number format from Settings)."""
        return display.money(value, symbol)

    @app.template_filter("number")
    def number(value, decimals=2):
        """Number with up to `decimals` decimals, trailing zeros dropped: 1234.5 → '1.234,5'."""
        return display.number(value, decimals, trim=True)

    @app.template_filter("plain")
    def plain(value):
        """A stored number as a form field value, Italian decimal comma, no trailing zeros: Decimal('10.500') → '10,5'."""
        if value is None or isinstance(value, Undefined):
            return ""
        text = format(value, "f")
        return (text.rstrip("0").rstrip(".") if "." in text else text).replace(".", ",")

    @app.template_filter("filesize")
    def filesize(size):
        size = float(size or 0)
        for unit in ("B", "KB", "MB", "GB"):
            if size < 1024 or unit == "GB":
                return f"{size:.0f} {unit}" if unit == "B" else f"{size:.1f} {unit}".replace(".", ",")
            size /= 1024

    @app.template_filter("it_date")
    def it_date(value):
        return display.day(value)

    @app.template_filter("tone")
    def tone(tx_type):
        """CSS class for an amount: red for expenses, green for income, neutral for transfers."""
        return {"expense": "negative", "income": "positive"}.get(tx_type, "")

    # ── Settings context processor ─────────────────────────────────────────────
    # Makes `settings` available in every template automatically.
    # The choices saved in the database (Settings page), over the defaults (all on).
    @app.context_processor
    def inject_settings():
        return {"settings": current_settings(), "notification_count": notification_count, "display": display.prefs()}

    def notification_count() -> int:
        """Reminders not yet seen, for the bell (never breaks a page)."""
        try:
            return len(notifications.collect())
        except Exception:  # noqa: BLE001 - a broken reminder source must not take the page down
            app.logger.exception("reminders unavailable")
            db.session.rollback()
            return 0

    # A module switched off in Settings disappears from the menu and its pages answer "not found"
    @app.before_request
    def block_disabled_modules():
        key = module_setting(request.blueprint, request.endpoint)
        if key and not current_settings().get(key, True):
            return render_template("module_disabled.html", setting=key), 404
        return None

    return app

