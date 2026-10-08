import hashlib
import os
import shutil
import sys
from pathlib import Path

from flask import Flask, jsonify, send_from_directory

import config as default_config
from money_manager.db.connection import close_db
from money_manager.db.migration import ensure_database


def installation_id():
    """Identify this installation without exposing its local path over HTTP."""
    folder = os.path.normcase(str(default_config.APP_DIR.resolve()))
    return hashlib.sha256(folder.encode("utf-8")).hexdigest()


def _resource_dir():
    return Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent.parent))


def _prepare_merchant_logos(resource_dir, target_dir):
    target_dir.mkdir(parents=True, exist_ok=True)
    bundled_dir = resource_dir / "static" / "uploads" / "merchants"
    if bundled_dir.resolve() == target_dir.resolve() or not bundled_dir.exists():
        return

    for source in bundled_dir.iterdir():
        target = target_dir / source.name
        if source.is_file() and not target.exists():
            shutil.copy2(source, target)


def create_app(config_object=default_config):
    resource_dir = _resource_dir()
    app = Flask(
        __name__,
        instance_relative_config=False,
        template_folder=str(resource_dir / "templates"),
        static_folder=str(resource_dir / "static"),
    )
    app.config.from_object(config_object)
    app.config.setdefault("MERCHANT_LOGO_DIR", resource_dir / "static" / "uploads" / "merchants")

    app.config["DATA_DIR"] = Path(app.config["DATA_DIR"])
    app.config["DATABASE"] = Path(app.config["DATABASE"])
    app.config["MERCHANT_LOGO_DIR"] = Path(app.config["MERCHANT_LOGO_DIR"])

    @app.template_filter("money")
    def format_money(value):
        return f"€{float(value or 0):,.2f}"

    @app.template_filter("display_date")
    def format_date(value, pattern="%d %b %Y"):
        from datetime import date
        try:
            return date.fromisoformat(str(value)[:10]).strftime(pattern)
        except (ValueError, TypeError):
            return value or ""

    @app.context_processor
    def profile_context():
        from money_manager.services.profile import local_profile
        return {"local_profile":local_profile()}

    @app.context_processor
    def asset_versions():
        return {"asset_version": lambda filename: (resource_dir / "static" / filename).stat().st_mtime_ns}

    @app.context_processor
    def quick_add_options():
        from money_manager.services.preferences import payment_accounts
        from money_manager.services.categories import list_categories
        from money_manager.services.merchants import list_merchants
        from money_manager.services.contacts import list_contacts
        from money_manager.utils.dates import today_iso
        return {"quick_accounts": payment_accounts(), "quick_categories": list_categories(), "quick_merchants": list_merchants(), "quick_contacts":list_contacts(), "today_iso": today_iso}

    app.config["DATA_DIR"].mkdir(parents=True, exist_ok=True)
    _prepare_merchant_logos(resource_dir, app.config["MERCHANT_LOGO_DIR"])
    app.teardown_appcontext(close_db)
    from money_manager.security import init_security
    init_security(app)
    with app.app_context():
        from money_manager.services.backup import create_snapshot
        create_snapshot()
    ensure_database(app)
    with app.app_context():
        from money_manager.services.scheduling import process_scheduled
        process_scheduled()
        from money_manager.services.history import capture_net_worth
        capture_net_worth()

    @app.cli.command("process-scheduled")
    def process_scheduled_command():
        process_scheduled()

    @app.get("/health")
    def health():
        response = jsonify(app="money-manager", status="ok")
        response.headers["X-Money-Manager-Installation"] = installation_id()
        return response

    @app.get("/static/uploads/merchants/<path:filename>")
    def merchant_logo(filename):
        return send_from_directory(app.config["MERCHANT_LOGO_DIR"], filename)

    from money_manager.routes.accounts import bp as accounts_bp
    from money_manager.routes.analytics import bp as analytics_bp
    from money_manager.routes.api import bp as api_bp
    from money_manager.routes.backup import bp as backup_bp
    from money_manager.routes.budgets import bp as budgets_bp
    from money_manager.routes.calendar import bp as calendar_bp
    from money_manager.routes.categories import bp as categories_bp
    from money_manager.routes.dashboard import bp as dashboard_bp
    from money_manager.routes.forecast import bp as forecast_bp
    from money_manager.routes.loans import bp as loans_bp
    from money_manager.routes.inbox import bp as inbox_bp
    from money_manager.routes.merchants import bp as merchants_bp
    from money_manager.routes.pending import bp as pending_bp
    from money_manager.routes.paypal_transfer import bp as paypal_transfer_bp
    from money_manager.routes.recurring import bp as recurring_bp
    from money_manager.routes.transactions import bp as transactions_bp
    from money_manager.routes.settings import bp as settings_bp
    from money_manager.routes.finance import bp as finance_bp

    app.register_blueprint(dashboard_bp)
    app.register_blueprint(transactions_bp)
    app.register_blueprint(accounts_bp)
    app.register_blueprint(categories_bp)
    app.register_blueprint(merchants_bp)
    app.register_blueprint(recurring_bp)
    app.register_blueprint(pending_bp)
    app.register_blueprint(paypal_transfer_bp)
    app.register_blueprint(analytics_bp)
    app.register_blueprint(forecast_bp)
    app.register_blueprint(loans_bp)
    app.register_blueprint(inbox_bp)
    app.register_blueprint(budgets_bp)
    app.register_blueprint(calendar_bp)
    app.register_blueprint(backup_bp)
    app.register_blueprint(api_bp)
    app.register_blueprint(settings_bp)
    app.register_blueprint(finance_bp)
    from money_manager.routes.plan import bp as plan_bp
    from money_manager.routes.profile import bp as profile_bp
    app.register_blueprint(plan_bp)
    app.register_blueprint(profile_bp)
    from money_manager.routes.contacts import bp as contacts_bp
    from money_manager.routes.taxes import bp as taxes_bp
    from money_manager.routes.debts import bp as debts_bp
    app.register_blueprint(contacts_bp)
    app.register_blueprint(taxes_bp)
    app.register_blueprint(debts_bp)

    return app
