"""SQLAlchemy models for the college event ticketing application."""

from datetime import datetime, timezone
from urllib.parse import urlparse
from uuid import uuid4

from flask_login import UserMixin
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import CheckConstraint, Index
from werkzeug.security import check_password_hash, generate_password_hash


db = SQLAlchemy()


def utcnow_naive() -> datetime:
    """Return the current UTC time as a naive datetime for SQLite storage."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


class User(UserMixin, db.Model):
    """A student or administrator account."""

    __tablename__ = "users"
    __table_args__ = (
        CheckConstraint("role IN ('student', 'admin')", name="ck_users_role"),
    )

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    email = db.Column(db.String(255), nullable=False, unique=True, index=True)
    password_hash = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(20), nullable=False, default="student")

    created_events = db.relationship("Event", back_populates="creator")
    tickets = db.relationship("Ticket", back_populates="user")

    def set_password(self, password: str) -> None:
        """Hash and store a plaintext password."""
        self.password_hash = generate_password_hash(password)

    def check_password(self, password: str) -> bool:
        """Return whether ``password`` matches the stored password hash."""
        return check_password_hash(self.password_hash, password)


class Event(db.Model):
    """A college event that students can register to attend."""

    __tablename__ = "events"

    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text, nullable=False, default="")
    department = db.Column(db.String(120), nullable=False)
    date_time = db.Column(db.DateTime(timezone=True), nullable=False)
    location = db.Column(db.String(200), nullable=False)
    location_url = db.Column(db.String(500), nullable=True)
    capacity = db.Column(db.Integer, nullable=False)
    image_filename = db.Column(db.String(255), nullable=True)
    created_by = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)

    creator = db.relationship("User", back_populates="created_events")
    tickets = db.relationship("Ticket", back_populates="event")

    @property
    def map_url(self) -> str | None:
        """Return the saved map URL, including links entered in legacy location data."""
        if self.location_url:
            return self.location_url
        parsed_location = urlparse(self.location)
        if parsed_location.scheme in {"http", "https"}:
            return self.location
        return None


class Ticket(db.Model):
    """An event registration with a unique QR verification token."""

    __tablename__ = "tickets"
    __table_args__ = (
        Index("uq_tickets_user_event", "user_id", "event_id", unique=True),
    )

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    event_id = db.Column(db.Integer, db.ForeignKey("events.id"), nullable=False)
    qr_token = db.Column(
        db.String(36), nullable=False, unique=True, default=lambda: str(uuid4())
    )
    is_checked_in = db.Column(db.Boolean, nullable=False, default=False)
    registered_at = db.Column(
        db.DateTime(timezone=True), nullable=False, default=utcnow_naive
    )
    checked_in_at = db.Column(db.DateTime(timezone=True), nullable=True)

    user = db.relationship("User", back_populates="tickets")
    event = db.relationship("Event", back_populates="tickets")
