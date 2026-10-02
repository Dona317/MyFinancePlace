from app.extensions import db


class AppSetting(db.Model):
    """Application-wide key/value settings persisted in the database (e.g. the active AI model)."""
    __tablename__ = "app_settings"

    key   = db.Column(db.String(100), primary_key=True)
    value = db.Column(db.Text)

    def __repr__(self):
        return f"<AppSetting {self.key}={self.value!r}>"
