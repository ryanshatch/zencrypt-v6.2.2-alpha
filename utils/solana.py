import base64, json, requests, os
from nacl.signing import VerifyKey
from nacl.exceptions import BadSignatureError

def verify_ed25519(message: bytes, address_base58: str, signature_base64: str) -> bool:
    # Phantom/Solflare give raw ed25519 signature base64; message is raw bytes
    try:
        sig = base64.b64decode(signature_base64)
        # Address is a base58 ed25519 pubkey; Solana uses ed25519 keys directly.
        # We verify against raw 32-byte pubkey.
        from base58 import b58decode
        pubkey = b58decode(address_base58)
        VerifyKey(pubkey).verify(message, sig)
        return True
    except (BadSignatureError, Exception):
        return False

def has_nft_ownership(helius_key: str, owner: str, mint: str) -> bool:
    # Minimal DAS ownership check
    url = f"https://mainnet.helius-rpc.com/?api-key={helius_key}"
    payload = {
        "jsonrpc":"2.0","id":"zencrypt","method":"getAsset","params":{
            "id": mint
        }
    }
    # fallback simple: use getTokenAccountsByOwner if needed
    r = requests.post(url, json=payload, timeout=10)
    # For simplicity, use token accounts API instead:
    rpc = os.environ.get("RPC_URL")
    req = {"jsonrpc":"2.0","id":1,"method":"getTokenAccountsByOwner",
           "params":[owner, {"mint": mint}, {"encoding":"jsonParsed"}]}
    rr = requests.post(rpc, json=req, timeout=10).json()
    try:
        return len(rr["result"]["value"]) > 0 and int(rr["result"]["value"][0]["account"]["data"]["parsed"]["info"]["tokenAmount"]["amount"]) > 0
    except Exception:
        return False
