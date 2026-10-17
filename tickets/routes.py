"""Student event registration and ticket listing routes."""

from uuid import uuid4

from flask import Blueprint, abort, current_app, flash, redirect, render_template, url_for
from flask_login import current_user, login_required
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import joinedload

from models import Event, Ticket, db
from tickets.qr import generate_qr_code_base64


tickets_blueprint = Blueprint("tickets", __name__)


@tickets_blueprint.post("/register-event/<int:event_id>")
@login_required
def register_event(event_id: int):
    """Register the logged-in student for an event and issue a ticket."""
    if current_user.role != "student":
        abort(403)

    event = db.session.get(Event, event_id)
    if event is None:
        abort(404)

    existing_ticket = db.session.execute(
        db.select(Ticket).filter_by(user_id=current_user.id, event_id=event.id)
    ).scalar_one_or_none()
    if existing_ticket:
        flash("You are already registered for this event.", "info")
        return redirect(url_for("tickets.my_tickets"))

    registration_count = db.session.scalar(
        db.select(func.count(Ticket.id)).where(Ticket.event_id == event.id)
    ) or 0
    if registration_count >= event.capacity:
        flash("This event has reached its registration capacity.", "warning")
        return redirect(url_for("events.event_list"))

    ticket = Ticket(
        user_id=current_user.id,
        event_id=event.id,
        qr_token=str(uuid4()),
    )
    db.session.add(ticket)
    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        # The unique user/event index closes the race between simultaneous
        # registration requests.
        existing_ticket = db.session.execute(
            db.select(Ticket).filter_by(user_id=current_user.id, event_id=event.id)
        ).scalar_one_or_none()
        if existing_ticket:
            flash("You are already registered for this event.", "info")
        else:
            current_app.logger.exception("Could not issue ticket for event %s", event.id)
            flash("We could not register you for this event. Please try again.", "danger")
        return redirect(url_for("tickets.my_tickets"))

    flash(f"You are registered for {event.title}.", "success")
    return redirect(url_for("tickets.my_tickets"))


@tickets_blueprint.get("/my-tickets")
@login_required
def my_tickets():
    """Show the logged-in student's event passes."""
    if current_user.role != "student":
        abort(403)

    tickets = db.session.execute(
        db.select(Ticket)
        .options(joinedload(Ticket.event))
        .where(Ticket.user_id == current_user.id)
        .order_by(Ticket.registered_at.desc())
    ).scalars().all()
    qr_codes = {
        ticket.id: generate_qr_code_base64(ticket.qr_token) for ticket in tickets
    }
    return render_template("ticket_pass.html", tickets=tickets, qr_codes=qr_codes)


@tickets_blueprint.post("/tickets/<int:ticket_id>/cancel")
@login_required
def cancel_ticket(ticket_id: int):
    """Allow a student to cancel an unused registration."""
    if current_user.role != "student":
        abort(403)

    ticket = db.session.execute(
        db.select(Ticket)
        .options(joinedload(Ticket.event))
        .where(Ticket.id == ticket_id, Ticket.user_id == current_user.id)
    ).scalar_one_or_none()
    if ticket is None:
        abort(404)
    if ticket.is_checked_in:
        flash("A checked-in ticket cannot be cancelled.", "warning")
        return redirect(url_for("tickets.my_tickets"))

    event_title = ticket.event.title
    db.session.delete(ticket)
    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        flash("Your registration could not be cancelled. Please try again.", "danger")
    else:
        flash(f"Your registration for {event_title} has been cancelled.", "success")
    return redirect(url_for("tickets.my_tickets"))
