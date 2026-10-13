"""The assistant on the user's data (F20): a question, an answer from the configured AI model, read only."""
from apiflask import APIBlueprint
from flask import render_template, request

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
