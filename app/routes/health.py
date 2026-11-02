"""Data health (F20): the checks on the archive, each with the way to fix what it found."""
from apiflask import APIBlueprint
from flask import render_template

from app.services import data_health

health_bp = APIBlueprint("health", __name__, url_prefix="/data-health", tag="Data health")


@health_bp.route("/")
def index():
    checks = data_health.run()
    return render_template("health/index.html", checks=checks,
                           problems=sum(1 for check in checks if check.count and check.level != "info"))
