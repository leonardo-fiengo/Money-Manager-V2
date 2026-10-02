import hmac
import secrets

from flask import abort, request, session


def init_security(app):
    app.config.setdefault("MAX_CONTENT_LENGTH", 32 * 1024 * 1024)
    if app.config["MAX_CONTENT_LENGTH"] is None:
        app.config["MAX_CONTENT_LENGTH"] = 32 * 1024 * 1024
    app.config.setdefault("CSRF_ENABLED", not app.testing)
    if not app.config.get("SECRET_KEY") or app.secret_key == "local-dev-secret-key":
        path = app.config["DATA_DIR"] / ".secret-key"
        try:
            with path.open("x", encoding="utf-8") as file:
                file.write(secrets.token_hex(32))
        except FileExistsError:
            pass
        app.secret_key = path.read_text(encoding="utf-8").strip()
        if len(app.secret_key) < 32:
            raise ValueError("The installation secret is invalid.")

    def csrf_token():
        if "csrf_token" not in session:
            session["csrf_token"] = secrets.token_urlsafe(32)
        return session["csrf_token"]

    app.jinja_env.globals["csrf_token"] = csrf_token

    @app.before_request
    def protect_writes():
        if app.config["CSRF_ENABLED"] and request.method not in {"GET", "HEAD", "OPTIONS"}:
            submitted = request.form.get("csrf_token") or request.headers.get("X-CSRF-Token") or ""
            expected = session.get("csrf_token") or ""
            if not expected or not hmac.compare_digest(submitted.encode("utf-8"), expected.encode("utf-8")):
                abort(400, description="Your form expired. Reload the page and try again.")

    @app.after_request
    def security_headers(response):
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "same-origin"
        if request.endpoint != "static":
            response.headers["Cache-Control"] = "no-store"
        return response
