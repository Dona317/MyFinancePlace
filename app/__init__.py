from flask import Flask, session
from config import config
from .routes.settings import DEFAULT_SETTINGS


def create_app(config_name="default"):
    app = Flask(__name__)
    app.config.from_object(config[config_name])

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

    # ── Settings context processor ─────────────────────────────────────────────
    # Makes `settings` available in every template automatically.
    # Priority: session (user has saved preferences) → defaults (all on).
    @app.context_processor
    def inject_settings():
        current = {**DEFAULT_SETTINGS}
        current.update(session.get("settings", {}))
        return {"settings": current}

    return app

