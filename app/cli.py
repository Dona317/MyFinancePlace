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
