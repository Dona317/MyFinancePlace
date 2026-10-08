import os

from apiflask import APIFlask

from config import config

from .extensions import babel, db, login_manager, migrate
from .services.ui_settings import current_language


def create_app(config_name="default"):
    app = APIFlask(
        __name__,
        title="MyFinancePlace | API",
        version="1.0.0",
        docs_path="/swagger",
        instance_path=os.environ.get("MFP_INSTANCE_PATH") or None,  # the desktop app keeps it in the user's data folder
    )
    app.config.from_object(config[config_name])
    config[config_name].init_app(app)  # production: SECRET_KEY check, ProxyFix, logging to stdout
    app.config["DESCRIPTION"] = "REST API per MyFinancePlace."
    app.config["CONTACT"] = {"name": "MyFinancePlace", "email": "dennisturco@gmail.com"}

    # No limits on request size: large statements and previews with thousands of rows must go through.
    # (Newer Flask/Werkzeug versions default to 1000 form fields / 500 KB per form; switch those off.)
    class UnlimitedRequest(app.request_class):
        max_form_memory_size = None
        max_form_parts = None

    app.request_class = UnlimitedRequest

    db.init_app(app)
    # Absolute: the desktop app runs from anywhere, with the migrations bundled next to the app package
    migrate.init_app(app, db, directory=os.path.join(os.path.dirname(app.root_path), "migrations"))
    # Interface language (Settings → Visualizzazione): Italian is the source, English the translation
    app.config.setdefault("BABEL_DEFAULT_LOCALE", "it")
    babel.init_app(app, locale_selector=current_language)
    login_manager.init_app(app)

    from . import models  # noqa: F401 — registers the models with SQLAlchemy
    from .services import currency  # noqa: F401 — fills transactions.amount_base on save
    from .web.blueprints import register_blueprints
    from .web.context import register_context
    from .web.filters import register_filters
    from .web.hooks import register_hooks

    register_blueprints(app)
    register_filters(app)
    register_context(app)
    register_hooks(app)
    return app
