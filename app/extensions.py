from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from flask_babel import Babel
from flask_login import LoginManager

db = SQLAlchemy()
migrate = Migrate()
babel = Babel()
login_manager = LoginManager()
