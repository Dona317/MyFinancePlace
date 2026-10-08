"""Every section of the app (a blueprint each) and the `flask` commands."""
from flask import Flask


def register_blueprints(app: Flask) -> None:
    from app.cli import clients_cli, users_cli
    from app.routes.accounting import accounting_bp
    from app.routes.accounts import accounts_bp
    from app.routes.auth import auth_bp
    from app.routes.clients import clients_bp
    from app.routes.dashboard import dashboard_bp
    from app.routes.debt import debt_bp
    from app.routes.documents import documents_bp
    from app.routes.export import export_bp
    from app.routes.forecast import forecast_bp
    from app.routes.insurance import insurance_bp
    from app.routes.lifestyle import lifestyle_bp
    from app.routes.notifications import notifications_bp
    from app.routes.portfolio import portfolio_bp
    from app.routes.reports import reports_bp
    from app.routes.settings import settings_bp
    from app.routes.snapshots import snapshots_bp
    from app.routes.subscriptions import subscriptions_bp
    from app.routes.tax import tax_bp
    from app.routes.transactions import transactions_bp

    for blueprint in (auth_bp, dashboard_bp, accounting_bp, lifestyle_bp, transactions_bp, portfolio_bp, debt_bp,
                      documents_bp, snapshots_bp, export_bp, settings_bp, insurance_bp, forecast_bp, accounts_bp,
                      notifications_bp, reports_bp, subscriptions_bp, clients_bp, tax_bp):
        app.register_blueprint(blueprint)
    app.cli.add_command(users_cli)
    app.cli.add_command(clients_cli)
