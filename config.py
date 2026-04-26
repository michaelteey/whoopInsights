import os
from dotenv import load_dotenv

load_dotenv()


class Config:
    SECRET_KEY = os.getenv("FLASK_SECRET_KEY", "dev-only-not-for-production")
    DATABASE_PATH = os.getenv("DATABASE_PATH", "instance/whoop.db")

    WHOOP_CLIENT_ID = os.getenv("WHOOP_CLIENT_ID", "")
    WHOOP_CLIENT_SECRET = os.getenv("WHOOP_CLIENT_SECRET", "")
    WHOOP_REDIRECT_URI = os.getenv("WHOOP_REDIRECT_URI", "http://localhost:5000/auth/callback")

    WHOOP_AUTH_URL = "https://api.prod.whoop.com/oauth/oauth2/auth"
    WHOOP_TOKEN_URL = "https://api.prod.whoop.com/oauth/oauth2/token"
    WHOOP_API_BASE = "https://api.prod.whoop.com/developer"

    WHOOP_SCOPES = [
        "read:cycles",
        "read:recovery",
        "read:sleep",
        "read:workout",
        "read:profile",
        "read:body_measurement",
        "offline",
    ]

    USE_SAMPLE_DATA = os.getenv("USE_SAMPLE_DATA", "true").lower() == "true"

    @classmethod
    def has_whoop_credentials(cls) -> bool:
        return bool(cls.WHOOP_CLIENT_ID and cls.WHOOP_CLIENT_SECRET)
