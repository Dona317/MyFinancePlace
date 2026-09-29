from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from flask_babel import Babel

db = SQLAlchemy()
migrate = Migrate()
babel = Babel()
