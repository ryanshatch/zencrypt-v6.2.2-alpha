from flask import Blueprint, request, jsonify, g
from .auth import require_auth
from .models import Usage, Wallet, db

crypto_bp = Blueprint("crypto", __name__)

PLANS = {
    "free": {"ops": 10},
    "personal": {"ops": 500},
    "pro": {"ops": 5000},
    "team": {"ops": 25000},
}

def under_quota(addr: str, cost_ops=1) -> bool:
    w = Wallet.query.filter_by(address=addr).first()
    if not w: return False
    from datetime import datetime, timedelta
    start = datetime.utcnow().replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    used = db.session.query(Usage).filter(Usage.wallet_id==w.id, Usage.ts>=start).count()
    limit = PLANS.get(w.plan, PLANS["free"])["ops"]
    return used + cost_ops <= limit

@crypto_bp.post("/encrypt")
@require_auth
def encrypt():
    if not under_quota(g.address): return jsonify({"error":"quota"}), 402
    body = request.get_json(force=True)
    # Expect client-side crypto; server can passthrough if needed
    # For demo: echo back size
    pt = body.get("plaintext","")
    ct_len = len(pt.encode())
    w = Wallet.query.filter_by(address=g.address).first()
    db.session.add(Usage(wallet_id=w.id, op="encrypt", bytes=ct_len)); db.session.commit()
    return jsonify({"ok": True, "bytes": ct_len})

@crypto_bp.post("/decrypt")
@require_auth
def decrypt():
    if not under_quota(g.address): return jsonify({"error":"quota"}), 402
    body = request.get_json(force=True)
    ct_b64 = body.get("ciphertext","")
    size = len(ct_b64)
    w = Wallet.query.filter_by(address=g.address).first()
    db.session.add(Usage(wallet_id=w.id, op="decrypt", bytes=size)); db.session.commit()
    return jsonify({"ok": True, "bytes": size})
