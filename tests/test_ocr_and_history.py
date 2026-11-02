"""Scans read by the light OCR (AI as backup) and categories learned from the user's own history."""
import io
import json
from decimal import Decimal

from PIL import Image

from app.models.transaction import Transaction
from app.services import ai_classification, bank_import, history_classifier, ocr
from tests.conftest import make_tx
from tests.test_ai_classification import items  # noqa: F401 - fixtures
from tests.test_ai_classification import ollama as classify_ollama  # noqa: F401 - fixtures
from tests.test_ai_extraction import PHOTO, SAMPLES, SCAN, _upload, ollama, truth_movements  # noqa: F401

# ── Light OCR ──────────────────────────────────────────────────────────────────

def test_scan_is_read_by_ocr_without_ai(ocr_on, client, db):
    preview = bank_import.analyze_statement(SCAN, (SAMPLES / SCAN).read_bytes())
    truth = {(m["date"], Decimal(str(m["amount"])).quantize(Decimal("0.01"))) for m in truth_movements()}
    read = {(r.date, r.amount) for r in preview.rows}
    assert preview.ocr and not preview.ocr_doubtful and preview.ai_model is None
    assert len(read & truth) >= 0.9 * len(truth)  # 50 of 53 on this sample
    html = _upload(client, SCAN).get_data(as_text=True)  # no AI configured: straight to the preview
    assert "Movimenti letti con OCR dalla scansione" in html and "Rileggi con l" not in html


def test_ocr_offers_the_ai_as_backup(ocr_on, client, ollama):  # noqa: F811
    html = _upload(client, SCAN).get_data(as_text=True)
    assert "Movimenti letti con OCR" in html and "Rileggi con l" in html and ollama.calls == []
    # a photo the OCR reads badly (rows merged): straight to the AI question, saying why
    response = _upload(client, PHOTO)
    assert response.status_code == 302 and "/export/bank/ai/" in response.location
    assert "sembra averne persi o uniti alcuni" in client.get(response.location).get_data(as_text=True)


def test_doubtful_ocr_without_ai_still_shows_the_rows(ocr_on, client, db):
    html = _upload(client, PHOTO).get_data(as_text=True)
    assert "Alcune righe potrebbero mancare" in html


def test_blank_image_goes_to_the_ai_question(ocr_on, db):
    buffer = io.BytesIO()
    Image.new("RGB", (400, 300), "white").save(buffer, format="PNG")
    assert ocr.read(buffer.getvalue()) is None
    try:
        bank_import.analyze_statement("foto.png", buffer.getvalue())
    except bank_import.AIRequired as exc:
        assert exc.kind == "photo"
    else:
        raise AssertionError("a blank photo must ask about the AI reader")


def test_without_the_ocr_package_scans_ask_for_ai(db):
    assert not ocr.available()  # switched off for tests that don't ask for it
    try:
        bank_import.analyze_statement(SCAN, (SAMPLES / SCAN).read_bytes())
    except bank_import.AIRequired as exc:
        assert exc.kind == "scan"


# ── Categories from the history ────────────────────────────────────────────────

def _history(db):
    db.session.add_all(
        [make_tx(description=f"PAGAMENTO POS ESSELUNGA MILANO {n}", counterparty="Esselunga", category="Alimentari")
         for n in range(4)]
        + [make_tx(description="PAGAMENTO POS BAR SPORT", category="Ristoranti"),
           make_tx(description="PAGAMENTO POS BAR SPORT", category="Svago"),  # the user is not consistent here
           make_tx(description="Bonifico ACME SPA stipendio", category="Stipendio", type="income"),
           make_tx(description="Bonifico ACME SPA stipendio", category="Stipendio", type="income")]
        + [make_tx(description=f"PAGAMENTO POS NEGOZIO {w}", category="Shopping") for w in "ABCDEFGHIJ"]
    )
    db.session.commit()


def test_history_guesses_only_when_it_clearly_agrees(app, db):
    _history(db)
    with app.test_request_context():
        guessed = history_classifier.guess("POS ESSELUNGA VIA ROMA", income=False)
        assert (guessed.category, guessed.counterparty, guessed.confidence) == ("Alimentari", "Esselunga", "alta")
        assert history_classifier.guess("BAR SPORT", income=False) is None      # split between two categories
        assert history_classifier.guess("PAGAMENTO POS", income=False) is None  # only bank boilerplate
        assert history_classifier.guess("ACME SPA", income=True).category == "Stipendio"
        assert history_classifier.guess("ACME SPA", income=False) is None       # income and expenses apart
        assert history_classifier.guess("", income=False) is None


def test_import_uses_the_history(app, db):
    _history(db)
    with app.test_request_context():
        rows = bank_import.enrich([bank_import.StatementRow(date=Transaction.query.first().date,
                                                            description="POS ESSELUNGA CORSO COMO", amount=Decimal("-30"))],
                                  "generic")
    assert rows[0].category == "Alimentari"


def test_ai_gets_only_what_the_history_cannot_place(app, db, classify_ollama):  # noqa: F811
    _history(db)
    with app.test_request_context():
        result = ai_classification.classify(items("POS ESSELUNGA VIA ROMA", "NETFLIX.COM"), ["Alimentari", "Abbonamenti"])
    sent = json.loads(classify_ollama.calls[0]["messages"][1]["content"].split("movimenti:\n", 1)[1])
    assert [m["id"] for m in sent] == [2]  # Esselunga was known
    assert result[1].to_dict() == {"category": "Alimentari", "counterparty": "Esselunga", "confidence": "alta",
                                   "from_history": True}
    assert result[2].category == "Abbonamenti" and not result[2].from_history
