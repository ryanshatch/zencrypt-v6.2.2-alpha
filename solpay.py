import os, secrets
from flask import Blueprint, request, jsonify, current_app
from .models import Wallet, Invoice, db

billing_bp = Blueprint("billing", __name__)

@billing_bp.post("/solana-pay/create")
def create_invoice():
    body = request.get_json(force=True)
    plan = body.get("plan","personal")
    lamports = {"personal": 50_000_000, "pro": 150_000_000, "team": 1_000_000_000}.get(plan, 50_000_000)
    reference = secrets.token_urlsafe(44)[:44]  # stand-in; use a real Pubkey generator in client
    addr = body.get("address")
    w = Wallet.query.filter_by(address=addr).first()
    if not w: return jsonify({"error":"unknown_wallet"}), 400
    inv = Invoice(wallet_id=w.id, amount_lamports=lamports, reference=reference, status="pending")
    db.session.add(inv); db.session.commit()
    return jsonify({
        "recipient": current_app.config["MERCHANT_WALLET"],
        "amount": lamports,
        "reference": reference,
        "label": f"Zencrypt {plan}",
        "message": "Thank you for supporting Zencrypt"
    })

@billing_bp.post("/solana-pay/confirm")
def confirm_invoice():
    body = request.get_json(force=True)
    reference = body.get("reference")
    addr = body.get("address")
    # Minimal confirmation: caller proves signature id they observed on-chain; in production,
    # query RPC for a transaction including reference and recipient, amount match, finality "confirmed".
    inv = Invoice.query.filter_by(reference=reference, status="pending").first()
    if not inv: return jsonify({"error":"not_found"}), 404
    # Assume paid; set plan. Replace with real RPC check.
    w = Wallet.query.get(inv.wallet_id)
    w.plan = body.get("plan","personal")
    inv.status = "paid"
    db.session.commit()
    return jsonify({"ok": True})
