"""F23: warranties and documents that expire — the page, the reminders, the deadlines calendar."""
from datetime import date, timedelta

from app.models.wealth import Document
from app.services import deadlines, document_expiry, notifications
from tests.conftest import make_tx


def _doc(db, name, **values):
    doc = Document(filename=name, stored_name=f"x-{name}", size=1, **values)
    db.session.add(doc)
    db.session.commit()
    return doc


def test_warranties_expiring_and_reminders(app, db):
    today = date.today()
    tx = make_tx(date=date(2025, 3, 10), description="MediaWorld lavatrice", amount=499)
    db.session.add(tx)
    db.session.commit()
    receipt = _doc(db, "scontrino.pdf", subject="Lavatrice Bosch", transaction_id=tx.id,
                   warranty_until=today + timedelta(days=20))
    _doc(db, "vecchio.pdf", warranty_until=today - timedelta(days=1))
    later = _doc(db, "tv.pdf", warranty_until=today + timedelta(days=400))
    card = _doc(db, "ci.jpg", subject="Carta d'identità", expires_on=today + timedelta(days=45))
    passport = _doc(db, "passaporto.pdf", expires_on=today - timedelta(days=3))
    _doc(db, "patente.pdf", expires_on=today + timedelta(days=300))
    assert document_expiry.suggested_warranty(receipt) == date(2027, 3, 10)
    assert document_expiry.suggested_warranty(later) is None
    assert document_expiry.warranties(today) == [receipt, later]
    assert document_expiry.expiring(today) == [passport, card]
    assert document_expiry.label(card) == "Carta d'identità" and document_expiry.label(passport) == "passaporto.pdf"
    assert [(d.id, kind) for d, kind, _ in document_expiry.reminders(today)] == [
        (passport.id, "expiry"), (receipt.id, "warranty"), (card.id, "expiry")]
    with app.test_request_context():
        found = {n.key: n for n in notifications.collect() if n.key.startswith("doc-")}
        assert found[f"doc-{passport.id}-expiry-{passport.expires_on}"].title == "Documento scaduto: passaporto.pdf"
        assert found[f"doc-{card.id}-expiry-{card.expires_on}"].title == "Documento in scadenza: Carta d'identità"
        assert found[f"doc-{receipt.id}-warranty-{receipt.warranty_until}"].title == "Garanzia in scadenza: Lavatrice Bosch"
        items = deadlines.between(today, today + timedelta(days=60))
    assert {d.title for d in items if d.kind in ("warranty", "document")} == {
        "Fine garanzia: Lavatrice Bosch", "Scade: Carta d'identità"}


def test_form_and_page(client, db):
    tx = make_tx(date=date(2026, 3, 10), description="MediaWorld lavatrice", amount=499)
    db.session.add(tx)
    db.session.commit()
    doc = _doc(db, "scontrino.pdf", transaction_id=tx.id)
    form = client.get(f"/documents/{doc.id}/edit").get_data(as_text=True)
    assert "10/03/2028" in form and 'data-value="2028-03-10"' in form
    client.post(f"/documents/{doc.id}/edit", data={"filename": "scontrino.pdf", "subject": "Lavatrice Bosch",
                                                   "warranty_until": "2028-03-10", "expires_on": "",
                                                   "transaction_id": str(tx.id), "doc_type": "Garanzia"})
    db.session.refresh(doc)
    assert doc.subject == "Lavatrice Bosch" and doc.warranty_until == date(2028, 3, 10) and doc.doc_type == "Garanzia"
    bad = client.post(f"/documents/{doc.id}/edit", data={"filename": "scontrino.pdf", "expires_on": "domani"},
                      follow_redirects=True).get_data(as_text=True)
    assert "non è una data valida" in bad
    page = client.get("/documents/expiring").get_data(as_text=True)
    assert "Lavatrice Bosch" in page and "Garanzie attive" in page and "Niente in scadenza" in page
    assert "garanzia fino al 10/03/2028" in client.get("/documents/").get_data(as_text=True)
