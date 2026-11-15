"""F23: the automatic encrypted backup — keys, files, rotation, schedule, restore, reminders, pages."""
import io
from datetime import datetime, timedelta

import pytest

from app.models.account import Account
from app.services import backup, encrypted_backup, notifications
from desktop import main


@pytest.fixture(autouse=True)
def fast_scrypt(monkeypatch):
    monkeypatch.setattr(encrypted_backup, "SCRYPT_LOG_N", 10)  # the real 2^15 is slow on purpose


def test_encrypt_decrypt_wrong_password_and_tampering():
    key = encrypted_backup.make_key("correct horse")
    assert set(key) == {"salt", "log_n", "public"} and "correct" not in str(key)
    assert encrypted_backup.check_password(key, "correct horse") and not encrypted_backup.check_password(key, "nope")
    assert not encrypted_backup.check_password({}, "x")
    blob = encrypted_backup.encrypt(b"PK the archive", key)
    assert encrypted_backup.is_encrypted(blob) and b"archive" not in blob
    assert encrypted_backup.encrypt(b"PK the archive", key) != blob  # a fresh key and nonce each time
    assert encrypted_backup.decrypt(blob, "correct horse") == b"PK the archive"
    with pytest.raises(encrypted_backup.EncryptedBackupError, match="Password sbagliata"):
        encrypted_backup.decrypt(blob, "wrong password")
    for at in (9, 30, len(blob) - 1):  # salt, ephemeral key, tag: any change is noticed
        changed = bytearray(blob)
        changed[at] ^= 1
        with pytest.raises(encrypted_backup.EncryptedBackupError):
            encrypted_backup.decrypt(bytes(changed), "correct horse")
    with pytest.raises(encrypted_backup.EncryptedBackupError, match="scrivi la password"):
        encrypted_backup.decrypt(blob, "")
    with pytest.raises(encrypted_backup.EncryptedBackupError, match="Non è un backup"):
        encrypted_backup.decrypt(b"PK zip", "x")
    broken = bytearray(blob)
    broken[len(encrypted_backup.MAGIC) + 16] = 40
    with pytest.raises(encrypted_backup.EncryptedBackupError, match="danneggiato"):
        encrypted_backup.decrypt(bytes(broken), "correct horse")
    with pytest.raises(encrypted_backup.EncryptedBackupError, match="almeno 8"):
        encrypted_backup.make_key("short")


def test_configure_run_rotate_and_schedule(app, db, tmp_path):
    with pytest.raises(backup.BackupError, match="cartella"):
        encrypted_backup.configure("", "weekly", 3, "password1")
    with pytest.raises(backup.BackupError, match="percorso completo"):
        encrypted_backup.configure("relative/dir", "weekly", 3, "password1")
    with pytest.raises(backup.BackupError, match="ogni quanto"):
        encrypted_backup.configure(str(tmp_path), "hourly", 3, "password1")
    with pytest.raises(backup.BackupError, match="da 1 a 100"):
        encrypted_backup.configure(str(tmp_path), "weekly", 0, "password1")
    with pytest.raises(backup.BackupError, match="Scegli una password"):
        encrypted_backup.configure(str(tmp_path), "weekly", 3, None)
    with pytest.raises(backup.BackupError, match="non è impostato"):
        encrypted_backup.run()
    assert not encrypted_backup.due() and encrypted_backup.run_if_due() is None
    folder = tmp_path / "OneDrive" / "Backup"
    encrypted_backup.configure(str(folder), "weekly", 2, "password1")
    db.session.add(Account(name="Banca"))
    db.session.commit()
    start = datetime(2026, 10, 1, 9, 0)
    assert encrypted_backup.due(start)
    first = encrypted_backup.run(start)
    assert first.name == "myfinanceplace_principale_2026-10-01_090000.mfpbackup" and first.parent == folder
    data, _ = backup.read_upload(encrypted_backup.decrypt(first.read_bytes(), "password1"))
    assert [a["name"] for a in data["tables"]["accounts"]] == ["Banca"]
    assert not encrypted_backup.due(start + timedelta(days=3)) and encrypted_backup.due(start + timedelta(days=7))
    (folder / "nota.txt").write_text("not ours")
    for days in (7, 14):
        encrypted_backup.run_if_due(start + timedelta(days=days))
    assert sorted(p.name for p in folder.iterdir()) == ["myfinanceplace_principale_2026-10-08_090000.mfpbackup",
                                                       "myfinanceplace_principale_2026-10-15_090000.mfpbackup", "nota.txt"]
    state = encrypted_backup.status(start + timedelta(days=15))
    assert state.enabled and not state.overdue and state.last_file.endswith("10-15_090000.mfpbackup")
    assert encrypted_backup.status(start + timedelta(days=30)).overdue  # two weeks without a backup
    # a new password needs the current one; the old files keep the old one
    with pytest.raises(backup.BackupError, match="attuale"):
        encrypted_backup.configure(str(folder), "weekly", 2, "password2", "wrong")
    encrypted_backup.configure(str(folder), "daily", 2, "password2", "password1")
    assert encrypted_backup.check_password(encrypted_backup.config(), "password2")
    encrypted_backup.configure(str(folder), "daily", 2, None)  # keeps the password
    assert encrypted_backup.config()["frequency"] == "daily"
    encrypted_backup.disable()
    assert not encrypted_backup.status().enabled and not encrypted_backup.due()


def test_failure_is_kept_and_reminded(app, db, tmp_path):
    blocker = tmp_path / "file"
    blocker.write_text("x")
    encrypted_backup.configure(str(blocker / "sub"), "daily", 3, "password1")
    now = datetime(2026, 10, 1, 9, 0)
    assert encrypted_backup.run_if_due(now) is None
    state = encrypted_backup.status(now)
    assert state.last_error.startswith("Cartella non scrivibile") and state.overdue and state.last_ok is None
    assert not encrypted_backup.due(now + timedelta(minutes=30)) and encrypted_backup.due(now + timedelta(hours=1))
    with app.test_request_context():
        found = [n for n in notifications.collect() if n.key.startswith("backup-")]
    assert len(found) == 1 and "Cartella non scrivibile" in found[0].detail


def test_background_desktop_and_archives(app, db, tmp_path, monkeypatch):
    encrypted_backup.configure(str(tmp_path), "daily", 3, "password1")
    db.session.commit()

    class Now:
        def __init__(self, target, args, **kwargs):
            self.target, self.args = target, args

        def start(self):
            self.target(*self.args)
    monkeypatch.setattr(encrypted_backup.threading, "Thread", Now)
    with app.test_request_context("/"):
        encrypted_backup.run_in_background()
        encrypted_backup.run_in_background()  # not due any more
    assert len(list(tmp_path.glob("*.mfpbackup"))) == 1
    encrypted_backup._running.add(None)
    try:
        encrypted_backup.config()  # a run already going for this archive: nothing more starts
        encrypted_backup.settings_store.set_json(encrypted_backup.SETTING, encrypted_backup.config() | {"last_try": None, "last_ok": None})
        db.session.commit()
        with app.test_request_context("/"):
            encrypted_backup.run_in_background()
        assert len(list(tmp_path.glob("*.mfpbackup"))) == 1
    finally:
        encrypted_backup._running.discard(None)
    monkeypatch.setattr(encrypted_backup, "run_if_due", lambda: (_ for _ in ()).throw(RuntimeError("boom")))
    with app.test_request_context("/"):
        encrypted_backup.run_in_background()  # logged, the running mark cleared
    assert None not in encrypted_backup._running
    monkeypatch.setattr(encrypted_backup, "run_all_archives", lambda: 2)
    assert main.write_backups(app) == 2


def test_pages_and_restore(client, db, tmp_path):
    page = client.get("/export/").get_data(as_text=True)
    assert "Backup automatico cifrato" in page and "Esegui ora" not in page
    html = client.post("/export/backup/encrypted", data={"folder": str(tmp_path), "frequency": "weekly", "keep": "4",
                                                         "password": "password1"}, follow_redirects=True).get_data(as_text=True)
    assert "Backup cifrato salvato" in html and "Esegui ora" in html and "Ultimo backup riuscito" in html
    files = list(tmp_path.glob("*.mfpbackup"))
    assert len(files) == 1
    html = client.post("/export/backup/encrypted", data={"folder": str(tmp_path), "frequency": "weekly", "keep": "4"},
                       follow_redirects=True).get_data(as_text=True)
    assert "Backup automatico impostato" in html
    client.post("/export/backup/encrypted", data={"folder": str(tmp_path), "frequency": "weekly", "keep": "4", "action": "now"})
    assert len(list(tmp_path.glob("*.mfpbackup"))) >= 1
    assert "almeno 8" in client.post("/export/backup/encrypted", data={"folder": str(tmp_path), "frequency": "weekly",
                                                                      "keep": "4", "password": "x", "current_password": "password1"},
                                     follow_redirects=True).get_data(as_text=True)
    db.session.add(Account(name="Dopo il backup"))
    db.session.commit()
    raw = files[0].read_bytes()
    wrong = client.post("/export/restore", data={"file": (io.BytesIO(raw), "b.mfpbackup"), "password": "nope",
                                                 "confirm": "1"}, content_type="multipart/form-data", follow_redirects=True)
    assert "Password sbagliata" in wrong.get_data(as_text=True)
    done = client.post("/export/restore", data={"file": (io.BytesIO(raw), "b.mfpbackup"), "password": "password1",
                                                "confirm": "1"}, content_type="multipart/form-data", follow_redirects=True)
    assert "Backup ripristinato" in done.get_data(as_text=True)
    assert Account.query.filter_by(name="Dopo il backup").count() == 0
    html = client.post("/export/backup/encrypted", data={"action": "off"}, follow_redirects=True).get_data(as_text=True)
    assert "Backup automatico spento" in html


def test_every_archive_when_due(app, db, tmp_path):
    with app.test_request_context():
        assert encrypted_backup.run_all_archives() == 0  # not set up
        encrypted_backup.configure(str(tmp_path), "daily", 3, "password1")
        db.session.commit()
        assert encrypted_backup.run_all_archives() == 1
        assert encrypted_backup.run_all_archives() == 0  # done for today
    assert len(list(tmp_path.glob("*.mfpbackup"))) == 1


def test_the_key_of_the_encrypted_data_travels_inside_the_encrypted_backup(client, app, db, tmp_path, monkeypatch):
    """F84: the encrypted backup carries the key of the card numbers; restored on «another computer» (another key),
    the password alone makes them readable again. The plain .zip never carries it."""
    import zipfile

    from app.models.card import Card
    from app.services import cards, field_crypto

    monkeypatch.delenv("MFP_DATA_KEY", raising=False)
    app.instance_path = str(tmp_path / "pc1")
    assert "Scarica backup cifrato" not in client.get("/export/").get_data(as_text=True)
    page = client.post("/export/backup/encrypted/download", follow_redirects=True).get_data(as_text=True)
    assert "Imposta prima la password" in page
    client.post("/export/backup/encrypted", data={"folder": str(tmp_path / "copie"), "frequency": "weekly",
                                                  "keep": "4", "password": "password1"})
    with app.test_request_context():
        card, _whole = cards.save(None, cards.CardInput(
            name="Visa", kind="credit", network="visa", number="4111 1111 1111 4821", expiry="08/28", holder=None,
            account_id=None, credit_limit=None, statement_day=None, contactless=True, notes=None))
        db.session.commit()
        first_key = field_crypto.key_text()
    plain = client.get("/export/backup").data
    with zipfile.ZipFile(io.BytesIO(plain)) as archive:
        assert backup.KEY_ENTRY not in archive.namelist()  # never in the plain .zip
    assert "Scarica backup cifrato" in client.get("/export/").get_data(as_text=True)
    sealed = client.post("/export/backup/encrypted/download")
    assert sealed.headers["Content-Disposition"].endswith('.mfpbackup"')
    with app.test_request_context():
        assert backup.key_in(encrypted_backup.decrypt(sealed.data, "password1")) == first_key
        assert backup.key_in(b"not a zip") is None
    # «another computer»: a new data folder, so a new key
    app.instance_path = str(tmp_path / "pc2")
    with app.test_request_context():
        assert field_crypto.key_text() != first_key
    page = client.post("/export/restore", data={"file": (io.BytesIO(sealed.data), "b.mfpbackup"),
                                                "password": "password1", "confirm": "1"},
                       content_type="multipart/form-data", follow_redirects=True).get_data(as_text=True)
    assert "Anche la chiave dei dati cifrati era nel backup" in page and "cifrati con la chiave di un altro computer" not in page
    with app.test_request_context():
        assert field_crypto.key_text() == first_key
        assert cards.full_number(Card.query.one()) == "4111 1111 1111 4821"
    # the plain .zip on yet another computer: the numbers stay unreadable, the app says what to do
    app.instance_path = str(tmp_path / "pc3")
    page = client.post("/export/restore", data={"file": (io.BytesIO(plain), "b.zip"), "confirm": "1"},
                       content_type="multipart/form-data", follow_redirects=True).get_data(as_text=True)
    assert "cifrati con la chiave di un altro computer" in page
