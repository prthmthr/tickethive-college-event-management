"""Admin analytics dashboard and attendance CSV export."""

import csv
from datetime import timezone
from functools import wraps
from io import BytesIO, StringIO

from flask import Blueprint, abort, render_template, send_file
from flask_login import current_user, login_required
from sqlalchemy import case, func
from sqlalchemy.orm import joinedload
from werkzeug.utils import secure_filename

from models import Event, Ticket, db


admin_blueprint = Blueprint("admin", __name__, url_prefix="/admin")


def admin_required(view):
    """Require an authenticated administrator account."""
    @wraps(view)
    @login_required
    def wrapped(*args, **kwargs):
        if current_user.role != "admin":
            abort(403)
        return view(*args, **kwargs)

    return wrapped


def _csv_safe(value) -> str:
    """Neutralize spreadsheet formulas in user-controlled CSV values."""
    value = "" if value is None else str(value)
    if value.startswith(("=", "+", "-", "@", "\t", "\r")):
        return "'" + value
    return value


def _format_utc(value) -> str:
    if value.tzinfo is not None:
        value = value.astimezone(timezone.utc).replace(tzinfo=None)
    return value.strftime("%Y-%m-%d %H:%M:%S UTC")


@admin_blueprint.get("/dashboard")
@admin_required
def dashboard():
    """Show event totals and per-event live attendance counts."""
    checked_in_expression = func.coalesce(
        func.sum(case((Ticket.is_checked_in.is_(True), 1), else_=0)), 0
    )
    event_rows = db.session.execute(
        db.select(
            Event,
            func.count(Ticket.id).label("registrations"),
            checked_in_expression.label("checked_in"),
        )
        .outerjoin(Ticket, Ticket.event_id == Event.id)
        .group_by(Event.id)
        .order_by(Event.date_time.desc(), Event.id.desc())
    ).all()

    events = []
    total_registrations = 0
    total_checked_in = 0
    for event, registrations, checked_in in event_rows:
        registrations = int(registrations or 0)
        checked_in = int(checked_in or 0)
        remaining = max(registrations - checked_in, 0)
        progress = round((checked_in / registrations) * 100, 1) if registrations else 0
        events.append(
            {
                "event": event,
                "registrations": registrations,
                "checked_in": checked_in,
                "remaining": remaining,
                "progress": progress,
            }
        )
        total_registrations += registrations
        total_checked_in += checked_in

    return render_template(
        "admin_dashboard.html",
        events=events,
        chart_data=[
            {
                "title": item["event"].title,
                "registrations": item["registrations"],
                "checked_in": item["checked_in"],
            }
            for item in events
        ],
        total_events=len(events),
        total_registrations=total_registrations,
        total_checked_in=total_checked_in,
        total_remaining=max(total_registrations - total_checked_in, 0),
    )


@admin_blueprint.get("/export-attendance/<int:event_id>")
@admin_required
def export_attendance(event_id: int):
    """Download the ticket roster for one event as a CSV file."""
    event = db.session.get(Event, event_id)
    if event is None:
        abort(404)

    tickets = db.session.execute(
        db.select(Ticket)
        .options(joinedload(Ticket.user))
        .where(Ticket.event_id == event.id)
        .order_by(Ticket.registered_at, Ticket.id)
    ).scalars().all()

    csv_text = StringIO(newline="")
    writer = csv.writer(csv_text)
    writer.writerow(("Student Name", "Email", "Registration Time", "Check-in Status"))
    for ticket in tickets:
        writer.writerow(
            (
                _csv_safe(ticket.user.name),
                _csv_safe(ticket.user.email),
                _format_utc(ticket.registered_at),
                "Checked In" if ticket.is_checked_in else "Not Checked In",
            )
        )

    event_slug = secure_filename(event.title) or f"event-{event.id}"
    csv_bytes = BytesIO(("\ufeff" + csv_text.getvalue()).encode("utf-8"))
    return send_file(
        csv_bytes,
        mimetype="text/csv; charset=utf-8",
        as_attachment=True,
        download_name=f"{event_slug}-attendance.csv",
        max_age=0,
    )
