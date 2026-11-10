"""
Broker import with a mapping screen and presets: a file whose columns are not all recognised asks for them, the
chosen columns build the preview, «Salva come preset» remembers them and the next file with the same columns gets them
on its own; the presets are listed with their kind on Esporta → Importa.
"""
import html as html_lib
import io
import re
from decimal import Decimal
from pathlib import Path

from app.models.account import Account
from app.models.wealth import Holding
from app.services import broker_import, import_presets
from tests.form_helper import form_data

SAMPLES = Path(__file__).resolve().parents[1] / "samples" / "dati_fittizi" / "broker"
GENERIC = (SAMPLES / "generico_operazioni.csv").read_bytes()
DEGIRO = (SAMPLES / "degiro_transazioni.csv").read_bytes()
# a broker with titles nothing recognises
ODD = ("Giorno;Verso;Codice strumento;Descrizione strumento;Pezzi;PMC;Spese\n"
       "03/03/2025;Acq;IT0003128367;Enel SpA;100;6,80;2,50\n"
       "10/04/2025;Ven;IT0003128367;Enel SpA;40;7,20;2,50\n").encode()
ODD_HEADERS = ODD.decode().splitlines()[0].split(";")
ODD_MAPPING = {"date": "Giorno", "side": "Verso", "isin": "Codice strumento", "name": "Descrizione strumento",
               "units": "Pezzi", "price": "PMC", "fee": "Spese"}


def _upload(client, raw: bytes, name: str = "strano.csv") -> str:
    return client.post("/portfolio/import", data={"file": (io.BytesIO(raw), name)},
                       content_type="multipart/form-data", follow_redirects=True).get_data(as_text=True)


def _submit(client, page: str, form_id: str, url: str = "/portfolio/import/columns", **overrides) -> str:
    data = form_data(page, form_id, **overrides)
    return client.post(url, data=data, follow_redirects=True).get_data(as_text=True)


def _map_odd(client) -> str:
    page = _upload(client, ODD)
    assert 'id="broker-columns-form"' in page and "Non trovo le colonne" in page
    return _submit(client, page, "broker-columns-form", **{f"col_{k}": v for k, v in ODD_MAPPING.items()})


def _confirm(client, page: str, **overrides) -> str:
    rows = re.findall(r'name="include" value="(\d+)"', page)
    return _submit(client, page, "broker-form", url="/portfolio/import/confirm", include=rows, **overrides)


def test_guess_missing_and_clean(app):
    headers = ["Giorno", "Pezzi", "Titolo", "PMC"]
    with app.test_request_context():
        guessed = broker_import.guess(headers)
        assert guessed["name"] == "Titolo" and guessed["date"] is None
        assert "data" in broker_import.missing(guessed)
        assert broker_import.missing({"date": "Giorno", "units": "Pezzi", "name": "Titolo", "price": "PMC"}) is None
    assert broker_import.clean(headers, {"date": "Giorno", "price": "Nope", "other": "Pezzi"}) == {
        **dict.fromkeys(broker_import.FIELDS), "date": "Giorno"}
    with app.test_request_context():
        found, guess, samples = broker_import.columns("strano.csv", ODD)
    assert found[0] == "Giorno" and samples["Pezzi"] == "100" and guess["date"] is None


def test_read_with_a_mapping(app, db):
    with app.test_request_context():
        preview = broker_import.read("strano.csv", ODD, ODD_MAPPING)
    assert [(r.units, r.price, r.fee, r.isin) for r in preview.rows] == [
        (Decimal(100), Decimal("6.80"), Decimal("2.50"), "IT0003128367"),
        (Decimal(-40), Decimal("7.20"), Decimal("2.50"), "IT0003128367")]
    assert preview.mapping["units"] == "Pezzi" and preview.headers[0] == "Giorno"


def test_mapping_screen_preview_and_preset(client, db):
    account = Account(name="Broker strano", kind="other")
    db.session.add(account)
    db.session.commit()
    page = _map_odd(client)
    assert "2 operazioni trovate" in page and "Enel SpA" in page and "Cambia colonne" in page
    done = _confirm(client, page, account_id=str(account.id), save_preset="1", preset_name="Broker strano")
    assert "2 operazioni importate" in done and "Preset «Broker strano» salvato" in done
    enel = Holding.query.filter_by(isin="IT0003128367").one()
    assert enel.quantity == 60
    preset = import_presets.all_presets("broker")[0]
    assert preset["mapping"]["units"] == "Pezzi" and preset["options"] == {"account_id": account.id}
    assert import_presets.all_presets("bank") == []

    # the same columns again: the preset is applied, no mapping screen, its account proposed
    again = _upload(client, ODD.replace(b"100;6,80", b"50;6,90"))
    assert "Preset «Broker strano» applicato" in again and 'id="broker-form"' in again
    assert f'value="{account.id}" selected' in again
    assert 'value="1" id="save-preset-check" checked' in again  # «Aggiorna il preset»

    # listed with its kind on the import page
    listing = client.get("/export/import").get_data(as_text=True)
    assert "Broker strano" in listing and ">Broker</td>" in listing


def test_choose_no_preset_and_change_columns(client, db):
    import_presets.save("Strano", "broker", ODD_HEADERS, ODD_MAPPING)
    page = _upload(client, ODD)
    assert "Preset «Strano» applicato" in page
    # «nessuno»: back to the guess, which cannot read the file → the mapping screen
    none = _submit(client, page, "broker-preset-form", preset="")
    assert 'id="broker-columns-form"' in none and "» applicato" not in none
    # «Cambia colonne»: the mapping screen prefilled with the columns in use
    edit = _submit(client, page, "broker-edit-form")
    assert 'id="broker-columns-form"' in edit and "Non trovo" not in edit
    assert '<option value="Pezzi" selected' in edit
    # dropping the price leaves the screen with the reason
    wrong = _submit(client, edit, "broker-columns-form", col_price="")
    assert "Non trovo il prezzo" in html_lib.unescape(wrong)


def test_recognised_files_go_straight_to_the_preview(client, db):
    page = _upload(client, GENERIC, "generico_operazioni.csv")
    assert 'id="broker-form"' in page and "4 operazioni trovate" in page and "» applicato" not in page
    edit = _submit(client, page, "broker-edit-form")
    assert '<option value="Quantità" selected' in edit
    back = _submit(client, edit, "broker-columns-form")
    assert "4 operazioni trovate" in back
    assert "formato Degiro" in _upload(client, DEGIRO, "degiro.csv")


def test_bad_token_and_unnamed_preset(client, db):
    page = client.post("/portfolio/import/columns", data={"file_token": "nope"}, follow_redirects=True)
    assert "Anteprima non valida" in page.get_data(as_text=True)
    preview = _map_odd(client)
    done = _confirm(client, preview, save_preset="1", preset_name=" ")
    assert "Preset non salvato" in done and import_presets.all_presets() == []
    # a forged mapping field is ignored
    rows = re.findall(r'name="include" value="(\d+)"', preview)
    data = form_data(preview, "broker-form", include=rows, save_preset="1", preset_name="X", mapped="bad")
    client.post("/portfolio/import/confirm", data=data)
    assert import_presets.all_presets() == []


def test_a_bank_preset_is_not_used_for_the_broker(client, db):
    bank = import_presets.save("Banca", "bank", ODD_HEADERS, ODD_MAPPING)
    page = _upload(client, ODD)
    assert 'id="broker-columns-form"' in page
    forged = client.post("/portfolio/import/columns", data={
        "file_token": re.search(r'name="file_token" value="([^"]+)"', page).group(1),
        "choose": "1", "preset": bank["id"]}).get_data(as_text=True)
    assert "» applicato" not in forged
    bad_file = _upload(client, b"", "vuoto.csv")
    assert "Analizza file" in bad_file
