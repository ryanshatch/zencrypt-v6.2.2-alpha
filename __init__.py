from flask import Flask
from .config import Config
from .db import init_db
from .auth import auth_bp
from .gate import gate_bp
from .crypto_routes import crypto_bp
from .solpay import billing_bp

def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)
    init_db(app)
    app.register_blueprint(auth_bp, url_prefix="/auth")
    app.register_blueprint(gate_bp, url_prefix="/gate")
    app.register_blueprint(crypto_bp, url_prefix="/api")
    app.register_blueprint(billing_bp, url_prefix="/billing")
    return app

# Render entrypoint:
app = create_app()
