import os
from datetime import datetime, timezone

from flask import Flask

from config import Config
from db import close_db, init_db
from routes import auth, dashboard, strength, workouts


SERVER_BOOT_AT = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def create_app() -> Flask:
    app = Flask(__name__)
    app.config.from_object(Config)
    app.secret_key = Config.SECRET_KEY

    init_db()

    if Config.USE_SAMPLE_DATA:
        from seed import seed_if_empty
        seed_if_empty()

    app.teardown_appcontext(close_db)

    app.register_blueprint(dashboard.bp)
    app.register_blueprint(auth.bp)
    app.register_blueprint(strength.bp)
    app.register_blueprint(workouts.bp)

    @app.context_processor
    def inject_build_info():
        sha = os.getenv("COMMIT_SHA", "dev")
        return {
            "build_sha": sha[:7] if sha and sha != "unknown" else "dev",
            "build_time": os.getenv("BUILD_TIME") or SERVER_BOOT_AT,
        }

    return app


app = create_app()


if __name__ == "__main__":
    import os
    port = int(os.getenv("PORT", "5050"))
    app.run(host="0.0.0.0", port=port, debug=True)
