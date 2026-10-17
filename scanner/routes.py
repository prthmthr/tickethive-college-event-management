"""Organizer scanner page and QR ticket verification API."""

from flask import Blueprint, abort, current_app, jsonify, render_template, request
from flask_login import current_user, login_required
from sqlalchemy import update
from sqlalchemy.orm import joinedload

from models import Event, Ticket, db, utcnow_naive


scanner_blueprint = Blueprint("scanner", __name__)


def _already_used_response(ticket: Ticket):
    checked_in_at = ticket.checked_in_at
    scanned_at = (
        checked_in_at.strftime("%Y-%m-%d %H:%M:%S UTC")
        if checked_in_at
        else "an unknown time"
    )
    return jsonify(
        status="warning",
        message=f"TICKET ALREADY USED! Scanned at {scanned_at}",
    ), 409


@scanner_blueprint.get("/scanner/<int:event_id>")
@login_required
def scanner_page(event_id: int):
    """Render the staff scanner for an event."""
    if current_user.role != "admin":
        abort(403)

    event = db.session.get(Event, event_id)
    if event is None:
        abort(404)
    return render_template("scanner.html", event=event)


@scanner_blueprint.post("/api/verify-ticket")
def verify_ticket():
    """Validate and check in a scanned ticket."""
    if not current_user.is_authenticated:
        return jsonify(status="error", message="Please log in to verify tickets."), 401
    if current_user.role != "admin":
        return jsonify(status="error", message="Organizer access is required."), 403

    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return jsonify(status="error", message="A JSON request body is required."), 400

    qr_token = payload.get("qr_token")
    event_id = payload.get("event_id")
    if not isinstance(qr_token, str) or not isinstance(event_id, int) or isinstance(event_id, bool):
        return jsonify(status="error", message="Invalid request data."), 400

    qr_token = qr_token.strip()
    ticket = db.session.execute(
        db.select(Ticket)
        .options(joinedload(Ticket.user))
        .where(Ticket.qr_token == qr_token)
    ).scalar_one_or_none()
    if ticket is None or ticket.event_id != event_id or db.session.get(Event, event_id) is None:
        return jsonify(status="error", message="Invalid Ticket Token!"), 404

    if ticket.is_checked_in:
        return _already_used_response(ticket)

    ticket_id = ticket.id
    student_name = ticket.user.name
    checkin_time = utcnow_naive()
    try:
        # Conditional update prevents two scanners from both accepting the same
        # ticket if they scan it at nearly the same time.
        result = db.session.execute(
            update(Ticket)
            .where(Ticket.id == ticket_id, Ticket.is_checked_in.is_(False))
            .values(is_checked_in=True, checked_in_at=checkin_time)
            .execution_options(synchronize_session=False)
        )
        if result.rowcount != 1:
            db.session.rollback()
            latest_ticket = db.session.get(Ticket, ticket_id)
            if latest_ticket is not None and latest_ticket.is_checked_in:
                return _already_used_response(latest_ticket)
            return jsonify(status="error", message="Invalid Ticket Token!"), 404

        db.session.commit()
    except Exception:
        db.session.rollback()
        current_app.logger.exception("Ticket check-in failed for ticket %s", ticket_id)
        return jsonify(status="error", message="Ticket verification failed. Please try again."), 500

    return jsonify(
        status="success",
        message=f"Check-in Successful! Welcome {student_name}",
    )
