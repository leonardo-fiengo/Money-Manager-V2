from pathlib import Path

from flask import Flask

from config import DATA_DIR
from money_manager.db.connection import close_db
from money_manager.db.migration import ensure_database


def create_app(config_object="config"):
    base_dir = Path(__file__).resolve().parent.parent
    app = Flask(
        __name__,
        instance_relative_config=False,
        template_folder=str(base_dir / "templates"),
        static_folder=str(base_dir / "static"),
    )
    app.config.from_object(config_object)
    app.config.setdefault("MERCHANT_LOGO_DIR", base_dir / "static" / "uploads" / "merchants")

    DATA_DIR.mkdir(exist_ok=True)
    app.config["MERCHANT_LOGO_DIR"].mkdir(parents=True, exist_ok=True)
    app.teardown_appcontext(close_db)
    ensure_database(app)

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
