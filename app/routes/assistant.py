"""
The assistant on the user's data (F20): a question, an answer from the configured AI model, read only. It lives in
a small panel opened by a round button at the bottom right of every page (static/js/main.js, initAskPanel); the
page of its own stays for a link that opens it in full.
"""
from apiflask import APIBlueprint
from flask import jsonify, render_template, request
from flask_babel import gettext as _
from flask_login import current_user

from app.services import assistant, assistant_jobs, studio
from app.services.ai_extraction import AIExtractionError

assistant_bp = APIBlueprint("assistant", __name__, url_prefix="/assistant", tag="Assistant")

EXAMPLES = (
    "Quanto ho speso in ristoranti negli ultimi tre mesi?",
    "In quale categoria spendo di più quest'anno?",
    "Quanto mi rende il portafoglio e quanto pesa ogni titolo?",
    "Quanto mi manca per l'obiettivo più vicino?",
)


@assistant_bp.route("/", methods=["GET", "POST"])
def index():
    answer = error = None
    question = ""
    if request.method == "POST":
        question = request.form.get("question", "")
        try:
            answer = assistant.ask(question)
        except AIExtractionError as exc:
            error = str(exc)
    return render_template("assistant/index.html", answer=answer, error=error, question=question,
                           available=assistant.available(), cloud=assistant.leaves_computer(), examples=EXAMPLES)


@assistant_bp.route("/status")
def status():
    """What the panel shows before the first question: whether a model is set, where it runs, a few examples."""
    return jsonify(available=assistant.available(), cloud=assistant.leaves_computer(), examples=list(EXAMPLES))


def _owner() -> str:
    """Who asked: the user, in the archive open (a job is shown only to them)."""
    client = studio.current()
    return f"{current_user.get_id()}:{client.id if client is not None else ''}"


def _job_reply(job: dict):
    if job["state"] == "error":
        return jsonify(job), 400
    return jsonify(job)


@assistant_bp.route("/ask", methods=["POST"])
def ask():
    """The panel's question: {"question": "..."} → the job answering it in the background ({"id", "state": "running"};
    the page polls /assistant/job/<id>), or {"error"} for a question that cannot be asked."""
    data = request.get_json(silent=True) or {}
    question = str(data.get("question", "")).strip()
    if not question:
        return jsonify(error=_("Scrivi una domanda.")), 400
    return _job_reply(assistant_jobs.start(question, _owner()))


@assistant_bp.route("/job/<job_id>")
def job(job_id):
    """A question under way or answered: {"state": "running" | "done" | "error", "text", "links", "error"}."""
    found = assistant_jobs.get(job_id, _owner())
    if found is None:
        return jsonify(error=_("Domanda non più disponibile: chiedi di nuovo."), state="gone"), 404
    return _job_reply(found)
