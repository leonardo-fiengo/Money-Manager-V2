import shutil
import sys
from pathlib import Path

from flask import Flask, jsonify, send_from_directory

import config as default_config
from money_manager.db.connection import close_db
from money_manager.db.migration import ensure_database


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

    @app.context_processor
    def asset_versions():
        return {"asset_version": lambda filename: (resource_dir / "static" / filename).stat().st_mtime_ns}

    app.config["DATA_DIR"].mkdir(parents=True, exist_ok=True)
    _prepare_merchant_logos(resource_dir, app.config["MERCHANT_LOGO_DIR"])
    app.teardown_appcontext(close_db)
    ensure_database(app)

    @app.get("/health")
    def health():
        return jsonify(app="money-manager", status="ok")

    @app.get("/static/uploads/merchants/<path:filename>")
    def merchant_logo(filename):
        return send_from_directory(app.config["MERCHANT_LOGO_DIR"], filename)

    from money_manager.routes.accounts import bp as accounts_bp
    from money_manager.routes.analytics import bp as analytics_bp
    from money_manager.routes.api import bp as api_bp
    from money_manager.routes.backup import bp as backup_bp
    from money_manager.routes.budgets import bp as budgets_bp
    from money_manager.routes.categories import bp as categories_bp
    from money_manager.routes.dashboard import bp as dashboard_bp
    from money_manager.routes.forecast import bp as forecast_bp
    from money_manager.routes.loans import bp as loans_bp
    from money_manager.routes.merchants import bp as merchants_bp
    from money_manager.routes.pending import bp as pending_bp
    from money_manager.routes.paypal_transfer import bp as paypal_transfer_bp
    from money_manager.routes.recurring import bp as recurring_bp
    from money_manager.routes.transactions import bp as transactions_bp

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
    app.register_blueprint(budgets_bp)
    app.register_blueprint(backup_bp)
    app.register_blueprint(api_bp)

    return app
