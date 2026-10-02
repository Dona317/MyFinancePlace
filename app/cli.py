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
