"""Command-line tools: `flask users ...` to get back in when every administrator's password is lost."""
import click
from flask.cli import AppGroup

from app.models.user import User
from app.services import users

users_cli = AppGroup("users", help="Manage who can sign in (the data is shared by every user).")


def _find(name: str) -> User:
    user = users.find(name)
    if user is None:
        raise click.ClickException(f"No user named {name!r}.")
    return user


@users_cli.command("create")
@click.argument("username")
@click.option("--admin", is_flag=True, help="Can add and remove users.")
@click.password_option()
def create(username, admin, password):
    """Add a user."""
    try:
        user = users.create(username, password, is_admin=admin)
    except ValueError as exc:
        raise click.ClickException(str(exc)) from exc
    click.echo(f"Created {user.username}{' (administrator)' if user.is_admin else ''}.")


@users_cli.command("reset-password")
@click.argument("username")
@click.password_option()
def reset_password(username, password):
    """Set a new password for a user."""
    user = _find(username)
    try:
        users.reset_password(user, password)
    except ValueError as exc:
        raise click.ClickException(str(exc)) from exc
    click.echo(f"New password set for {user.username}.")


@users_cli.command("list")
def list_users():
    """Show the users."""
    for user in User.query.order_by(User.username).all():
        click.echo(f"{user.username}\t{'admin' if user.is_admin else 'user'}\t{user.last_login or '-'}")


clients_cli = AppGroup("clients", help="The studio's clients, each with a database of its own (F11).")


@clients_cli.command("list")
def clients_list():
    """Show the clients and their databases."""
    from app.services import studio

    for client in studio.clients():
        click.echo(f"{client.id:4d}  {client.slug:30s}  {client.database or '(studio database)'}  {client.name}"
                   f"{'  [archived]' if client.archived else ''}")


@clients_cli.command("migrate")
def clients_migrate():
    """Bring every client's database to the current schema (after `flask db upgrade` on the studio)."""
    from app.services import studio

    done = studio.migrate_all()
    click.echo(f"Migrated {len(done)} client database(s){': ' + ', '.join(done) if done else ''}.")


@clients_cli.command("create")
@click.argument("name")
def clients_create(name):
    """Add a client with an empty archive of its own."""
    from app.services import studio

    try:
        client = studio.create(name)
    except studio.StudioError as exc:
        raise click.ClickException(str(exc)) from exc
    click.echo(f"Created {client.name} in database {client.database}.")


mcp_cli = AppGroup("mcp", help="Read-only access for an AI assistant on this computer (F22).")


@mcp_cli.command("serve")
@click.option("--client", "slug", default=None, help="The archive to read (slug, see `flask clients list`).")
def mcp_serve(slug):
    """Answer an MCP client (Claude Desktop…) on stdin/stdout, read only."""
    from flask import current_app

    from app.services import mcp_server

    try:
        client = mcp_server.find_client(slug)
    except ValueError as exc:
        raise click.ClickException(str(exc)) from exc
    mcp_server.serve(current_app._get_current_object(), client)


market_cli = AppGroup("market", help="The market data store: end-of-day closes shared by every archive (D10, F69).")


@market_cli.command("sync")
@click.argument("symbols", nargs=-1)
@click.option("--main", "main_funds", is_flag=True, help="The main funds and ETFs (and the benchmark indices).")
def market_sync(symbols, main_funds):
    """Read the daily closes from Yahoo Finance: everything the first time, then only what is new."""
    from app.services import market_data

    if not symbols and not main_funds:
        raise click.ClickException("Name the Yahoo symbols (VWCE.MI…) or use --main.")
    found = market_data.sync_main_funds() if main_funds else []
    found += [market_data.sync(symbol) for symbol in symbols]
    for item in found:
        click.echo(f"{item.symbol:<14} {'+' + str(item.added) + ' closes' if not item.error else 'ERROR ' + item.error}")
    if all(item.error for item in found):
        raise click.ClickException("Nothing read: is Yahoo Finance reachable from here?")


@market_cli.command("status")
def market_status():
    """What the store holds."""
    from app.services import market_data

    click.echo(f"{market_data.url()}  (schema {market_data.schema_version()})")
    for row in market_data.overview():
        click.echo(f"{row['symbol']:<14} {row['count']:>6} closes  {row['first_day'] or '-'} → {row['last_day'] or '-'}"
                   f"{'  ERROR ' + row['error'] if row['error'] else ''}")
