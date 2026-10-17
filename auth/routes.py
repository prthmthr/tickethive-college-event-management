"""Server-rendered registration and authentication routes."""

from flask import Blueprint, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_user, logout_user
from sqlalchemy.exc import IntegrityError

from models import User, db


auth_blueprint = Blueprint("auth", __name__, url_prefix="/auth")


@auth_blueprint.route("/register", methods=["GET", "POST"])
def register():
    if current_user.is_authenticated:
        return redirect(url_for("dashboard"))

    if request.method == "POST":
        name = request.form.get("name", "").strip()
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        confirm_password = request.form.get("confirm_password", "")

        if not name or not email or not password:
            flash("Please fill in every field.", "danger")
        elif len(password) < 8:
            flash("Your password must be at least 8 characters long.", "danger")
        elif password != confirm_password:
            flash("The passwords do not match.", "danger")
        else:
            existing_user = db.session.execute(
                db.select(User).filter_by(email=email)
            ).scalar_one_or_none()
            if existing_user:
                flash("An account with that email already exists.", "danger")
            else:
                student = User(name=name, email=email, role="student")
                student.set_password(password)
                db.session.add(student)
                try:
                    db.session.commit()
                except IntegrityError:
                    db.session.rollback()
                    flash("An account with that email already exists.", "danger")
                else:
                    flash("Your account has been created. Please log in.", "success")
                    return redirect(url_for("auth.login"))

    return render_template("auth/register.html")


@auth_blueprint.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("dashboard"))

    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        user = db.session.execute(
            db.select(User).filter_by(email=email)
        ).scalar_one_or_none()

        if user is None or not user.check_password(password):
            flash("Email or password is incorrect.", "danger")
        else:
            login_user(user)
            flash(f"Welcome back, {user.name}.", "success")
            return redirect(url_for("dashboard"))

    return render_template("auth/login.html")


@auth_blueprint.post("/logout")
def logout():
    if current_user.is_authenticated:
        logout_user()
        flash("You have been logged out.", "info")
    return redirect(url_for("auth.login"))
