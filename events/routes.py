"""Public event listing and administrator event creation routes."""

from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse
from uuid import uuid4

from flask import Blueprint, abort, current_app, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required
from PIL import Image, UnidentifiedImageError
from sqlalchemy import func, or_
from sqlalchemy.exc import SQLAlchemyError
from werkzeug.utils import secure_filename

from models import Event, Ticket, db


events_blueprint = Blueprint("events", __name__)
ALLOWED_IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".gif"}


def save_event_image(upload):
    """Validate and save one optional event cover image."""
    if not upload or not upload.filename:
        return None, None

    extension = Path(secure_filename(upload.filename)).suffix.lower()
    if extension not in ALLOWED_IMAGE_EXTENSIONS:
        return None, "Upload a JPG, PNG, WEBP, or GIF image."

    try:
        image = Image.open(upload.stream)
        image.verify()
        upload.stream.seek(0)
    except (UnidentifiedImageError, OSError):
        return None, "The uploaded file is not a valid image."

    filename = f"{uuid4().hex}{extension}"
    upload.save(Path(current_app.config["UPLOAD_FOLDER"]) / filename)
    return filename, None


def remove_event_image(filename: str | None) -> None:
    """Delete an event image only when it is one of this app's saved files."""
    if not filename or Path(filename).name != filename:
        return
    try:
        (Path(current_app.config["UPLOAD_FOLDER"]) / filename).unlink(missing_ok=True)
    except OSError:
        current_app.logger.warning("Could not remove event image %s", filename)


def valid_map_url(value: str) -> bool:
    """Allow HTTPS Google Maps links, including Google Maps short links."""
    parsed_url = urlparse(value)
    host = (parsed_url.hostname or "").lower()
    return (
        parsed_url.scheme == "https"
        and (
            host == "google.com"
            or host.endswith(".google.com")
            or host == "maps.app.goo.gl"
        )
    )


@events_blueprint.get("/events")
def event_list():
    """List events with search and date/department filters."""
    search_query = request.args.get("q", "").strip()
    selected_department = request.args.get("department", "").strip()
    selected_status = request.args.get("status", "all")
    if selected_status not in {"all", "upcoming", "past"}:
        selected_status = "all"

    filters = []
    if search_query:
        search_pattern = f"%{search_query.lower()}%"
        filters.append(
            or_(
                func.lower(Event.title).like(search_pattern),
                func.lower(Event.description).like(search_pattern),
            )
        )
    if selected_department:
        filters.append(Event.department == selected_department)
    if selected_status == "upcoming":
        filters.append(Event.date_time >= datetime.now())
    elif selected_status == "past":
        filters.append(Event.date_time < datetime.now())

    statement = (
        db.select(Event, func.count(Ticket.id).label("registrations"))
        .outerjoin(Ticket, Ticket.event_id == Event.id)
        .group_by(Event.id)
        .order_by(Event.date_time.asc(), Event.id.asc())
    )
    if filters:
        statement = statement.where(*filters)
    rows = db.session.execute(statement).all()

    departments = db.session.execute(
        db.select(Event.department).distinct().order_by(Event.department)
    ).scalars().all()

    registered_event_ids = set()
    if current_user.is_authenticated and current_user.role == "student":
        registered_event_ids = set(
            db.session.execute(
                db.select(Ticket.event_id).where(Ticket.user_id == current_user.id)
            ).scalars()
        )

    events = [
        {"event": event, "registrations": int(registrations or 0)}
        for event, registrations in rows
    ]
    return render_template(
        "events.html",
        events=events,
        registered_event_ids=registered_event_ids,
        departments=departments,
        search_query=search_query,
        selected_department=selected_department,
        selected_status=selected_status,
    )


@events_blueprint.get("/events/<int:event_id>")
def event_detail(event_id: int):
    """Show full event information and registration state."""
    event = db.session.get(Event, event_id)
    if event is None:
        abort(404)

    registrations = db.session.scalar(
        db.select(func.count(Ticket.id)).where(Ticket.event_id == event.id)
    ) or 0
    ticket = None
    if current_user.is_authenticated and current_user.role == "student":
        ticket = db.session.execute(
            db.select(Ticket).filter_by(user_id=current_user.id, event_id=event.id)
        ).scalar_one_or_none()

    return render_template(
        "event_detail.html",
        event=event,
        registrations=registrations,
        ticket=ticket,
        is_full=registrations >= event.capacity,
    )


def _event_form_values():
    """Read, validate, and normalize submitted event form values."""
    title = request.form.get("title", "").strip()
    description = request.form.get("description", "").strip()
    department = request.form.get("department", "").strip()
    date_time_value = request.form.get("date_time", "").strip()
    location = request.form.get("location", "").strip()
    location_url = request.form.get("location_url", "").strip()
    capacity_value = request.form.get("capacity", "").strip()
    errors = []

    # Supports older use of the Location field for a Google Maps link.
    if valid_map_url(location) and not location_url:
        location_url = location
        location = "Google Maps location"
    if not title or len(title) > 200:
        errors.append("Enter an event title of up to 200 characters.")
    if not department or len(department) > 120:
        errors.append("Enter a department of up to 120 characters.")
    if not location or len(location) > 200:
        errors.append("Enter a location of up to 200 characters.")
    if location_url and (len(location_url) > 500 or not valid_map_url(location_url)):
        errors.append("Enter a valid HTTPS Google Maps link.")

    try:
        event_date_time = datetime.fromisoformat(date_time_value)
    except ValueError:
        event_date_time = None
        errors.append("Enter a valid event date and time.")

    try:
        capacity = int(capacity_value)
        if capacity < 1:
            errors.append("Capacity must be at least 1.")
    except ValueError:
        capacity = 0
        errors.append("Enter a whole-number capacity of at least 1.")

    return {
        "title": title,
        "description": description,
        "department": department,
        "date_time": event_date_time,
        "location": location,
        "location_url": location_url or None,
        "capacity": capacity,
    }, errors


def _render_event_form(event=None):
    return render_template("event_form.html", event=event)


@events_blueprint.route("/admin/events/new", methods=["GET", "POST"])
@login_required
def create_event():
    """Let an administrator create an event."""
    if current_user.role != "admin":
        abort(403)
    if request.method == "GET":
        return _render_event_form()

    values, errors = _event_form_values()
    image_filename, image_error = save_event_image(request.files.get("image"))
    if image_error:
        errors.append(image_error)
    if errors:
        remove_event_image(image_filename)
        for error in errors:
            flash(error, "danger")
        return _render_event_form()

    event = Event(**values, image_filename=image_filename, created_by=current_user.id)
    db.session.add(event)
    try:
        db.session.commit()
    except SQLAlchemyError:
        db.session.rollback()
        remove_event_image(image_filename)
        flash("The event could not be saved. Please try again.", "danger")
        return _render_event_form()

    flash(f"{event.title} has been created.", "success")
    return redirect(url_for("events.event_detail", event_id=event.id))


@events_blueprint.route("/admin/events/<int:event_id>/edit", methods=["GET", "POST"])
@login_required
def edit_event(event_id: int):
    """Let an administrator update event details without losing attendees."""
    if current_user.role != "admin":
        abort(403)
    event = db.session.get(Event, event_id)
    if event is None:
        abort(404)
    if request.method == "GET":
        return _render_event_form(event)

    values, errors = _event_form_values()
    registrations = db.session.scalar(
        db.select(func.count(Ticket.id)).where(Ticket.event_id == event.id)
    ) or 0
    if values["capacity"] < registrations:
        errors.append(f"Capacity cannot be lower than the {registrations} existing registrations.")

    new_image_filename, image_error = save_event_image(request.files.get("image"))
    if image_error:
        errors.append(image_error)
    if errors:
        remove_event_image(new_image_filename)
        for error in errors:
            flash(error, "danger")
        return _render_event_form(event)

    old_image_filename = event.image_filename
    for field, value in values.items():
        setattr(event, field, value)
    if new_image_filename:
        event.image_filename = new_image_filename
    elif request.form.get("remove_image") == "on":
        event.image_filename = None

    try:
        db.session.commit()
    except SQLAlchemyError:
        db.session.rollback()
        remove_event_image(new_image_filename)
        flash("The event could not be updated. Please try again.", "danger")
        return _render_event_form(event)

    if event.image_filename != old_image_filename:
        remove_event_image(old_image_filename)
    flash(f"{event.title} has been updated.", "success")
    return redirect(url_for("events.event_detail", event_id=event.id))


@events_blueprint.post("/admin/events/<int:event_id>/delete")
@login_required
def delete_event(event_id: int):
    """Remove an event and all tickets registered for it."""
    if current_user.role != "admin":
        abort(403)

    event = db.session.get(Event, event_id)
    if event is None:
        abort(404)

    event_title = event.title
    image_filename = event.image_filename
    try:
        db.session.execute(db.delete(Ticket).where(Ticket.event_id == event.id))
        db.session.delete(event)
        db.session.commit()
    except SQLAlchemyError:
        db.session.rollback()
        flash("The event could not be removed. Please try again.", "danger")
    else:
        remove_event_image(image_filename)
        flash(f"{event_title} and its ticket records have been removed.", "success")

    return redirect(url_for("events.event_list"))
