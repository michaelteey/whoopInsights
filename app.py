from flask import Flask

from config import Config
from db import close_db, init_db
from routes import auth, dashboard, strength


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

    return app


app = create_app()


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
