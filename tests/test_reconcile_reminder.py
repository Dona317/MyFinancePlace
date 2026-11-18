"""T11 (16 Nov 2026): after a reconciliation «remind me to do it again in…» makes a reminder in the Scadenzario that
opens the account; the account's page lists the differences its reconciliations recorded."""
from datetime import date, timedelta

from app.models.account import Account
from app.models.reminder import Reminder
from app.services import deadlines, notifications, periods
from tests.conftest import make_tx

TODAY = date.today()


def _account(db):
    account = Account(name="Conto Banca", kind="checking", opening_balance=1000)
    db.session.add(account)
    db.session.commit()
    db.session.add(make_tx(account_id=account.id, amount=100, date=TODAY - timedelta(days=5)))
    db.session.commit()
    return account


def test_after_a_reconciliation_the_window_asks_when_to_do_it_again(app, client, db):
    account = _account(db)
    page = client.post(f"/accounts/{account.id}/reconcile", data={"on": TODAY.isoformat(), "statement_balance": "850"}
                       ).get_data(as_text=True)
    assert "openModal('reconcile-reminder')" in page and 'value="1m" checked' in page  # shown, one month proposed
    rows = page[page.index('id="reconciliations"'):][:900]
    assert "text-negative" in rows and "50,00" in rows and "Vedi il movimento" in rows  # the difference, with its movement

    response = client.post(f"/accounts/{account.id}/reconcile/reminder", data={"when": "1m"})
    assert response.status_code == 302 and response.headers["Location"].endswith(f"/accounts/{account.id}#reconcile")
    reminder = Reminder.query.one()
    assert reminder.account_id == account.id and reminder.due == periods.add_months(TODAY, 1)
    assert reminder.title == "Riconcilia il conto Conto Banca" and reminder.notice_days == 0 and not reminder.done
    page = client.get(f"/accounts/{account.id}").get_data(as_text=True)
    assert "Prossima riconciliazione" in page and "openModal('reconcile-reminder'));" not in page  # not opened by itself

    client.post(f"/accounts/{account.id}/reconcile/reminder", data={"when": "3m"})  # asked again: moved, not doubled
    assert Reminder.query.one().due == periods.add_months(TODAY, 3)
    day = TODAY + timedelta(days=45)
    client.post(f"/accounts/{account.id}/reconcile/reminder", data={"when": "date", "on": day.isoformat()})
    assert Reminder.query.one().due == day
    for wrong in ({"when": "date", "on": TODAY.isoformat()}, {"when": "date", "on": ""}, {"when": "boh"}):
        client.post(f"/accounts/{account.id}/reconcile/reminder", data=wrong)
        assert Reminder.query.one().due == day  # today, no date, an unknown choice: nothing changes


def test_the_reminder_opens_the_account_and_a_reconciliation_closes_it(app, client, db):
    account = _account(db)
    with app.test_request_context():
        reminder = deadlines.remind_to_reconcile(account, TODAY)
        (found,) = [n for n in notifications.collect() if n.key.startswith(f"reminder-{reminder.id}-")]
        assert found.url == f"/accounts/{account.id}#reconcile" and "Conto Banca" in found.title
        (listed,) = [d for d in deadlines.between(TODAY, TODAY) if d.kind == "reminder"]
        assert listed.url == f"/accounts/{account.id}#reconcile"
        later = deadlines.remind_to_reconcile(Account.query.filter_by(name="Conto Banca").one(), TODAY)
        assert later.id == reminder.id
    client.post(f"/accounts/{account.id}/reconcile", data={"on": TODAY.isoformat(), "statement_balance": "900"})
    assert Reminder.query.one().done  # reconciled: the reminder that asked for it is done
    with app.test_request_context():
        assert deadlines.reconcile_reminder(account) is None
    other = Reminder(title="Bollo auto", due=TODAY, repeat="none")
    db.session.add(other)
    db.session.commit()
    with app.test_request_context():
        assert deadlines.reminder_url(other, TODAY).endswith(f"#reminder-{other.id}")  # the others stay in the Scadenzario
