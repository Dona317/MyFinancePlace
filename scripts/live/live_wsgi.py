"""The production app for the live run, with its own instance folder (documents, backups): the real one is not touched."""

import os

from app import create_app

app = create_app("production")
app.instance_path = os.environ["LIVE_INSTANCE"]
