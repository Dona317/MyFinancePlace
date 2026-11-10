"""Saved import presets (F61): the columns of a mapped CSV / Excel file, saved from the preview and applied again to
the next file with the same layout; listed, renamed and deleted on the import page."""
import io
from decimal import Decimal
from pathlib import Path

from app.models.account import Account
from app.models.transaction import Transaction
from app.services import import_presets, settings_store
from tests.form_helper import form_data

SAMPLES = Path(__file__).resolve().parent.parent / "samples" / "bank_statements"
UNICREDIT = "unicredit_2026-08_2026-09.csv"
HEADERS = ["Data Registrazione", "Data valuta", "Descrizione", "Importo (EUR)"]


def _file(name: str = UNICREDIT):
    return io.BytesIO((SAMPLES / name).read_bytes()), name


def _columns(client, name: str = UNICREDIT) -> dict:
    return client.post("/export/import/columns", data={"file": _file(name)},
                       content_type="multipart/form-data").get_json()


def _preview(client, preset: str = "", **columns) -> str:
    data = {"file": _file(), "preset": preset, **{f"col_{k}": v for k, v in columns.items()}}
    return client.post("/export/import", data=data, content_type="multipart/form-data").get_data(as_text=True)


def _account(db) -> Account:
    account = Account(name="Unicredit carta", kind="current", opening_balance=Decimal("0"))
    db.session.add(account)
    db.session.commit()
    return account


def _save_from_import(client, db, name="Unicredit carta") -> dict:
    """Import the sample with the value date chosen by hand and tick «Salva come preset»."""
    account = _account(db)
    html = _preview(client, date="Data valuta", amount="Importo (EUR)", description="Descrizione")
    assert 'name="save_preset"' in html
    response = client.post("/export/bank/confirm", data=form_data(
        html, "preview-form", account_id=str(account.id), save_preset="1", preset_name=f"  {name} "))
    assert response.status_code == 302
    return import_presets.all_presets()[0]


def test_save_a_preset_when_confirming_a_mapped_import(client, db):
    preset = _save_from_import(client, db)
    assert Transaction.query.count() > 0
    assert preset["name"] == "Unicredit carta" and preset["kind"] == "bank"
    assert preset["signature"] == ["data registrazione", "data valuta", "descrizione", "importo eur"]
    assert preset["mapping"] == {"date": "Data valuta", "amount": "Importo (EUR)", "description": "Descrizione"}
    assert preset["options"]["account_id"] == Account.query.one().id and preset["options"]["header_line"] == 1
    with client.session_transaction() as session:
        assert any("Preset «Unicredit carta» salvato" in message for _, message in session["_flashes"])


def test_the_same_layout_gets_the_preset_back(client, db):
    assert _columns(client)["preset"] is None  # nothing saved yet: the guess
    preset = _save_from_import(client, db)
    columns = _columns(client)
    assert columns["preset"] == preset["id"] and columns["sure"]
    assert columns["guess"]["date"] == "Data valuta" != columns["auto"]["date"]
    assert [p["name"] for p in columns["presets"]] == ["Unicredit carta"]

    # the preview of a file mapped with the preset says so and proposes its account
    html = _preview(client, preset=preset["id"], **{k: v for k, v in columns["guess"].items() if v})
    assert "Preset «Unicredit carta» applicato" in html
    assert f'<option value="{preset["options"]["account_id"]}" selected' in html
    # confirming again without the tick changes nothing; with it, the preset is updated, not doubled
    client.post("/export/bank/confirm", data=form_data(html, "preview-form", save_preset=[]))
    assert len(import_presets.all_presets()) == 1


def test_a_preset_is_matched_by_layout_not_by_spelling(app):
    import_presets.save("Banca", "bank", HEADERS, {"date": "Data valuta", "amount": "Importo (EUR)"})
    other = ["DATA REGISTRAZIONE", "Data Valuta", "descrizione", "Importo EUR"]
    assert import_presets.match(other, "bank")["name"] == "Banca"
    assert import_presets.resolve(import_presets.match(other, "bank"), other) == {
        "date": "Data Valuta", "amount": "Importo EUR"}
    assert import_presets.match(HEADERS, "broker") is None
    assert import_presets.match(HEADERS[:3], "bank") is None
    # usable on another layout that still has its columns; not on one that lacks them
    assert [p["name"] for p in import_presets.usable([*HEADERS, "Saldo"], "bank")] == ["Banca"]
    assert import_presets.usable(["Data valuta", "Causale"], "bank") == []


def test_a_preset_for_another_layout_can_be_picked(client, db):
    import_presets.save("Solo valuta", "bank", ["Data valuta", "Importo (EUR)", "Descrizione"],
                        {"date": "Data valuta", "amount": "Importo (EUR)", "description": "Descrizione"})
    columns = _columns(client)
    assert columns["preset"] is None and [p["name"] for p in columns["presets"]] == ["Solo valuta"]
    assert columns["presets"][0]["mapping"]["date"] == "Data valuta"


def test_list_rename_and_delete(client, db):
    preset = _save_from_import(client, db)
    page = client.get("/export/import").get_data(as_text=True)
    assert 'id="import-presets"' in page and 'value="Unicredit carta"' in page

    client.post(f"/export/import/presets/{preset['id']}/rename", data={"name": "UniCredit conto"})
    assert import_presets.get(preset["id"])["name"] == "UniCredit conto"
    import_presets.save("Altro", "bank", ["A", "B"], {"date": "A"})
    response = client.post(f"/export/import/presets/{preset['id']}/rename", data={"name": "altro"})
    assert response.status_code == 302 and import_presets.get(preset["id"])["name"] == "UniCredit conto"
    assert client.post(f"/export/import/presets/{preset['id']}/rename", data={"name": " "}).status_code == 302
    assert client.post("/export/import/presets/nope/rename", data={"name": "X"}).status_code == 404

    client.post(f"/export/import/presets/{preset['id']}/delete")
    assert [p["name"] for p in import_presets.all_presets()] == ["Altro"]
    assert client.post(f"/export/import/presets/{preset['id']}/delete").status_code == 404
    assert "Nessun preset salvato" not in client.get("/export/import").get_data(as_text=True)


def test_saving_needs_a_name_and_replaces_by_name(client, db):
    account = _account(db)
    html = _preview(client, date="Data valuta", amount="Importo (EUR)", description="Descrizione")
    client.post("/export/bank/confirm", data=form_data(html, "preview-form", account_id=str(account.id),
                                                       save_preset="1", preset_name=""))
    assert import_presets.all_presets() == []
    first = import_presets.save("Carta", "bank", HEADERS, {"date": "Data valuta"})
    second = import_presets.save("carta", "bank", HEADERS, {"date": "Data Registrazione"})
    assert first["id"] == second["id"] and len(import_presets.all_presets("bank")) == 1
    assert import_presets.all_presets("broker") == []


def test_bad_values_are_refused_or_ignored(app):
    for name, kind in (("", "bank"), ("X", "fund")):
        try:
            import_presets.save(name, kind, HEADERS, {})
        except ValueError:
            continue
        raise AssertionError("saved")
    settings_store.set_json(import_presets.KEY, [{"name": "senza id"}, "rotto", {"id": "a", "name": "Buono"}])
    assert [p["name"] for p in import_presets.all_presets()] == ["Buono"]
    assert import_presets.get(None) is None and import_presets.delete("zzz") is False
