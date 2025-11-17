import os, time, secrets, hmac, json
from flask import Blueprint, request, jsonify, current_app, g
import jwt
from .utils.solana import verify_ed25519
from .models import Wallet, db

auth_bp = Blueprint("auth", __name__)
_NONCES = {}

@auth_bp.post("/nonce")
def nonce():
    n = secrets.token_urlsafe(24)
    _NONCES[n] = int(time.time()) + 600
    return jsonify({"nonce": n})

@auth_bp.post("/verify")
def verify():
    data = request.get_json(force=True)
    addr = data.get("address")
    sigb64 = data.get("signature")
    nonce = data.get("nonce","").encode()
    if not addr or not sigb64 or not nonce:
        return jsonify({"error":"bad_request"}), 400
    if nonce.decode() not in _NONCES or _NONCES[nonce.decode()] < time.time():
        return jsonify({"error":"nonce_expired"}), 401
    ok = verify_ed25519(nonce, addr, sigb64)
    if not ok:
        return jsonify({"error":"verify_failed"}), 401
    # upsert wallet
    w = Wallet.query.filter_by(address=addr).first()
    if not w:
        w = Wallet(address=addr); db.session.add(w); db.session.commit()
    token = jwt.encode(
        {"sub": addr, "iat": int(time.time()), "exp": int(time.time())+600},
        current_app.config["JWT_SECRET"], algorithm="HS256")
    return jsonify({"token": token, "address": addr})

def require_auth(f):
    from functools import wraps
    @wraps(f)
    def wrapper(*args, **kwargs):
        auth = request.headers.get("Authorization","")
        if not auth.startswith("Bearer "):
            return jsonify({"error":"unauthorized"}), 401
        token = auth.split(" ",1)[1]
        try:
            payload = jwt.decode(token, current_app.config["JWT_SECRET"], algorithms=["HS256"])
            g.address = payload["sub"]
        except Exception:
            return jsonify({"error":"unauthorized"}), 401
        return f(*args, **kwargs)
    return wrapper
