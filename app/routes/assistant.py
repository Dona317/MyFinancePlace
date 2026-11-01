"""
The assistant on the user's data (F20): a question, an answer from the configured AI model, read only. It lives in
a small panel opened by a round button at the bottom right of every page (static/js/main.js, initAskPanel); the
page of its own stays for a link that opens it in full.
"""
from apiflask import APIBlueprint
from flask import jsonify, render_template, request

from app.services import assistant
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


@assistant_bp.route("/ask", methods=["POST"])
def ask():
    """The panel's question: {"question": "..."} → {"text", "links": [[label, url]]} or {"error"}."""
    data = request.get_json(silent=True) or {}
    try:
        answer = assistant.ask(str(data.get("question", "")))
    except AIExtractionError as exc:
        return jsonify(error=str(exc)), 400
    return jsonify(question=answer.question, text=answer.text, links=[list(link) for link in answer.links])
