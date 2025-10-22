import os
from dotenv import load_dotenv


load_dotenv()

MY_DOMAIN="https://video-call-92hl.onrender.com"


DATABASE_URL =os.getenv("DATABASE_URL")

MAIL_USERNAME = os.getenv("MAIL_USERNAME")
MAIL_PASSWORD = os.getenv("MAIL_PASSWORD")
MAIL_FROM = os.getenv("MAIL_FROM")
MAIL_PORT = int(os.getenv("MAIL_PORT", 587))
MAIL_SERVER = os.getenv("MAIL_SERVER")
MAIL_STARTTLS = os.getenv("MAIL_STARTTLS", "True").lower() == "true"
MAIL_SSL_TLS = os.getenv("MAIL_SSL_TLS", "False").lower() == "true"
MAIL_FROM_NAME = os.getenv("MAIL_FROM_NAME", "")
USE_CREDENTIALS = os.getenv("USE_CREDENTIALS", "True").lower() == "true"
SECRET_KEY = os.getenv("SECRET_KEY")

MAIL_CONFIG = {
    "MAIL_USERNAME": MAIL_USERNAME,
    "MAIL_PASSWORD": MAIL_PASSWORD,
    "MAIL_FROM": MAIL_FROM,
    "MAIL_PORT": MAIL_PORT,
    "MAIL_SERVER": MAIL_SERVER,
    "MAIL_STARTTLS": MAIL_STARTTLS,     # ✅ replaces MAIL_TLS
    "MAIL_SSL_TLS": MAIL_SSL_TLS,       # ✅ replaces MAIL_SSL
    "MAIL_FROM_NAME": MAIL_FROM_NAME,
    "USE_CREDENTIALS": USE_CREDENTIALS, # ✅ must be True usually
}
