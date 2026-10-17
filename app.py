"""Application factory and command-line entry point."""

import os
from pathlib import Path

import click
from dotenv import load_dotenv
from flask import Flask, redirect, render_template, url_for
from flask_login import LoginManager, current_user, login_required
from flask_wtf.csrf import CSRFProtect
from sqlalchemy import inspect, text
from sqlalchemy.exc import IntegrityError

from models import User, db


load_dotenv()

login_manager = LoginManager()
csrf = CSRFProtect()


def create_app(test_config: dict | None = None) -> Flask:
    """Create and configure the Flask application."""
    app = Flask(__name__, instance_relative_config=True)
    Path(app.instance_path).mkdir(parents=True, exist_ok=True)
    database_path = Path(app.instance_path) / "ticketing.sqlite3"

    app.config.from_mapping(
        SECRET_KEY=os.environ.get("SECRET_KEY", "dev-only-change-this-secret"),
        SQLALCHEMY_DATABASE_URI=f"sqlite:///{database_path.as_posix()}",
        SQLALCHEMY_TRACK_MODIFICATIONS=False,
        MAX_CONTENT_LENGTH=5 * 1024 * 1024,
        UPLOAD_FOLDER=str(Path(app.static_folder) / "uploads"),
    )
    if test_config:
        app.config.update(test_config)

    Path(app.config["UPLOAD_FOLDER"]).mkdir(parents=True, exist_ok=True)

    db.init_app(app)
    login_manager.init_app(app)
    csrf.init_app(app)

    login_manager.login_view = "auth.login"
    login_manager.login_message = "Please log in to continue."
    login_manager.login_message_category = "warning"

    @login_manager.user_loader
    def load_user(user_id: str) -> User | None:
        try:
            return db.session.get(User, int(user_id))
        except (TypeError, ValueError):
            return None

    from auth.routes import auth_blueprint
    from admin.routes import admin_blueprint
    from events.routes import events_blueprint
    from scanner.routes import scanner_blueprint
    from tickets.routes import tickets_blueprint

    app.register_blueprint(auth_blueprint)
    app.register_blueprint(admin_blueprint)
    app.register_blueprint(events_blueprint)
    app.register_blueprint(scanner_blueprint)
    app.register_blueprint(tickets_blueprint)

    @app.get("/")
    def index():
        if current_user.is_authenticated:
            return redirect(url_for("dashboard"))
        return redirect(url_for("auth.login"))

    @app.get("/dashboard")
    @login_required
    def dashboard():
        return render_template("dashboard.html")

    @app.cli.command("create-admin")
    @click.option("--name", prompt=True, help="Administrator's display name.")
    @click.option("--email", prompt=True, help="Administrator's email address.")
    @click.password_option(prompt="Administrator password")
    def create_admin(name: str, email: str, password: str) -> None:
        """Create an administrator account from the command line."""
        name = name.strip()
        email = email.strip().lower()
        if not name or not email:
            raise click.ClickException("Name and email are required.")

        existing_user = db.session.execute(
            db.select(User).filter_by(email=email)
        ).scalar_one_or_none()
        if existing_user:
            raise click.ClickException("An account with that email already exists.")

        admin = User(name=name, email=email, role="admin")
        admin.set_password(password)
        db.session.add(admin)
        try:
            db.session.commit()
        except IntegrityError as error:
            db.session.rollback()
            raise click.ClickException("Could not create the administrator account.") from error

        click.echo(f"Administrator account created for {email}.")

    with app.app_context():
        db.create_all()
        event_columns = {column["name"] for column in inspect(db.engine).get_columns("events")}
        if "image_filename" not in event_columns:
            db.session.execute(text("ALTER TABLE events ADD COLUMN image_filename VARCHAR(255)"))
        if "location_url" not in event_columns:
            db.session.execute(text("ALTER TABLE events ADD COLUMN location_url VARCHAR(500)"))
        # create_all() does not add indexes to an existing SQLite table.
        # This also upgrades databases created before duplicate-ticket protection
        # was added to the Ticket model.
        db.session.execute(
            text(
                "CREATE UNIQUE INDEX IF NOT EXISTS uq_tickets_user_event "
                "ON tickets (user_id, event_id)"
            )
        )
        db.session.commit()

    return app


if __name__ == "__main__":
    create_app().run(debug=os.environ.get("FLASK_DEBUG", "0") == "1")
