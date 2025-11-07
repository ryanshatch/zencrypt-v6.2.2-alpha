from flask import Blueprint, jsonify, current_app, g
from .auth import require_auth
from .utils.solana import has_nft_ownership

gate_bp = Blueprint("gate", __name__)

@gate_bp.get("/check")
@require_auth
def check_gate():
    mint = current_app.config["GATING_MINT"]
    if not mint:
        return jsonify({"authorized": True, "reason":"no_gate_config"})
    helius = current_app.config["HELIUS_API_KEY"]
    ok = has_nft_ownership(helius, g.address, mint)
    return jsonify({"authorized": bool(ok)})
