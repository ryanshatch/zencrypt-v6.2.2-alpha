# Zencrypt Wallet Authentication Setup Guide

## Overview

This guide explains how the Solana wallet authentication system works in Zencrypt and how to test it end-to-end.

## What Was Implemented

### 1. **Database Model Updates** (`models.py`)
- Added `wallet_address` field to the `User` model (Solana base58-encoded public key)
- Made `email` and `password_hash` nullable to support wallet-only accounts
- Users can now authenticate via either:
  - Email + Password (traditional)
  - Solana Wallet (Phantom, Solflare, etc.)

### 2. **Authentication Endpoints** (`webapp.py`)

#### `/auth/nonce` (GET)
- Generates a random nonce and stores it in the session
- Returns JSON: `{ "nonce": "<random_hex_string>" }`
- **Client workflow:** Request nonce before asking user to sign

#### `/auth/verify` (POST)
- Verifies Ed25519 signature using the wallet's public key
- Expected JSON payload:
  ```json
  {
    "public_key": "<base58_encoded_public_key>",
    "signature_b64": "<base64_encoded_signature>",
    "nonce": "<nonce_from_/auth/nonce>"
  }
  ```
- Creates or retrieves user by wallet address
- Returns JSON: `{ "success": true, "user_id": <id> }`
- Sets Flask session: `session['user_id']` and `session['wallet_address']`

### 3. **Wallet Connection UI** (`/connect-wallet`)

A complete single-page application featuring:
- **Phantom Wallet** button
- **Solflare Wallet** button  
- **Ledger Live** button (UI ready, backend pending)
- Fallback link to traditional email login
- Real-time status messages (loading, error, success)
- Professional dark theme UI

The page handles:
1. Detecting installed wallet extensions
2. Prompting user to sign the nonce
3. Verifying signature server-side
4. Redirecting to dashboard on success

### 4. **Enhanced Navbar**

The navbar now displays:
- Truncated wallet address (first 8 + last 4 chars): `Wallet: 2zQqvV5j...gx7b`
- Available for users logged in via wallet auth

### 5. **Login Page Update**

Added link on login/register pages:
```
Connect Solana Wallet Instead →
```
Directs users to `/connect-wallet`

## Dependencies

Required packages (already in `requirements.txt`):
- `base58==2.1.1` — Solana address encoding/decoding
- `PyNaCl==1.5.0` — Ed25519 signature verification

Verify installation:
```bash
pip list | grep -E "(base58|PyNaCl)"
```

## Testing the Wallet Auth Flow

### Prerequisites

1. **Install a Solana wallet browser extension:**
   - [Phantom](https://phantom.app/) (recommended)
   - [Solflare](https://solflare.com/)

2. **Have a test Solana account** (devnet or mainnet)

### Step-by-Step Test

#### Step 1: Start the app
```bash
cd /path/to/zencrypt-v6.2.2-alpha
.\zenven\Scripts\Activate.ps1
python webapp.py
```

You should see:
```
Zencrypt Web-App - Developed And Owned Entirely By imaclone.x
The Web App is now successfully up and running: http://localhost:5000/
```

#### Step 2: Navigate to wallet connect page
- Open browser → http://localhost:5000
- Click **"Connect Solana Wallet Instead →"** (or go directly to http://localhost:5000/connect-wallet)

#### Step 3: Connect wallet
- Click **Phantom** (or your installed wallet)
- Browser will prompt to allow access to wallet extension
- Approve the connection in your wallet popup

#### Step 4: Sign the nonce
- App will show: "Waiting for wallet signature..."
- Wallet extension will prompt: "Sign message?" or "Approve signing"
- The message shown is your random nonce (e.g., `a1b2c3d4e5f6...`)
- Click **Sign** in your wallet

#### Step 5: Verify authentication succeeded
- Status updates: "✓ Successfully authenticated!"
- You are redirected to the dashboard (`/`)
- Navbar displays: `Wallet: 2zQqvV...x7b`
- You can access all features (hash, encrypt, decrypt, etc.)

#### Step 6: Check session persistence
- Open DevTools → Application → Cookies → localhost
- Look for a cookie named `session` with encrypted Flask session data
- Refresh the page — you should still be logged in

### Troubleshooting

#### Issue: "Phantom wallet not found"
- **Solution:** Install [Phantom browser extension](https://phantom.app/)

#### Issue: "Signature verification failed" (400 error)
- **Possible causes:**
  - Nonce mismatch — ensure you haven't opened wallet connect in multiple tabs
  - Wallet signed a different message
  - Browser console error — open DevTools and check
- **Solution:** Close all tabs, start fresh at `/connect-wallet`

#### Issue: "User creation failed" (500 error)
- **Possible causes:**
  - Database issue (locked, permissions, path invalid)
  - Multiple users with same wallet address
- **Solution:**
  - Check server logs for detailed error
  - Delete `instance/zencrypt.db` and restart (removes all users)

#### Issue: Session not persisting after page refresh
- **Possible causes:**
  - Session cookie being blocked by browser privacy settings
  - `app.secret_key` randomized (shouldn't happen in single process)
- **Solution:**
  - Check browser cookie privacy settings
  - Open DevTools → Application → Cookies and look for Flask session cookie

#### Issue: Navbar shows but doesn't toggle
- **Possible causes:**
  - JavaScript error in browser console
  - DOM element not rendering correctly
- **Solution:**
  - Open DevTools → Console
  - Check for any error messages
  - Verify navbar HTML is present: right-click → Inspect Element

## API Summary

### Public Routes (No Auth Required)
- `GET /` → Redirect to login or dashboard
- `GET /login` → Login form
- `GET /register` → Registration form
- `GET /connect-wallet` → Wallet connection page
- `GET /auth/nonce` → Get nonce for signing
- `POST /auth/verify` → Verify wallet signature
- `GET /__session` → (Dev only) View session contents

### Protected Routes (Auth Required)
- `GET /` → Dashboard (hash generation)
- `GET /encrypt` → Encrypt text
- `GET /decrypt` → Decrypt text
- `GET /file` → File operations
- `GET /argon2` → Advanced hashing
- `GET /pgp` → PGP encryption
- `GET /export-key` → Export encryption key
- `GET /import-key` → Import encryption key
- `GET /logout` → Log out

## Database Schema Changes

### User Model

**Before:**
```python
class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(256), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
```

**After:**
```python
class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(120), unique=True, nullable=True)
    password_hash = db.Column(db.String(256), nullable=True)
    wallet_address = db.Column(db.String(44), unique=True, nullable=True)  # NEW
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
```

**Migration:** Run Flask-Migrate to add the `wallet_address` column:
```bash
flask db migrate -m "Add wallet_address to User"
flask db upgrade
```

Or delete the database and let Flask recreate it:
```bash
rm instance/zencrypt.db  # On Linux/Mac: rm
del zencrypt.db          # On Windows
python -c "from webapp import app, db; app.app_context().push(); db.create_all()"
```

## Code Files Modified

1. **`models.py`**
   - Added `wallet_address` field to `User` model
   - Made `email` and `password_hash` nullable

2. **`webapp.py`**
   - Added imports: `base58`, `nacl.signing.VerifyKey`, `nacl.encoding.RawEncoder`
   - Updated `@app.route('/auth/verify')` endpoint with proper signature verification
   - Created complete `/connect-wallet` page with Phantom/Solflare integration
   - Enhanced navbar to display wallet address
   - Added wallet connection link to login pages

3. **No changes to:** `requirements.txt` (deps already present), static files, other modules

## Security Notes

### Signature Verification
- Uses Ed25519 elliptic curve cryptography (industry standard for Solana)
- Nonce is random 32-byte hex string (cryptographically secure)
- Nonce stored in session and compared before creating/updating user
- Nonce destroyed after verification (one-time use)

### Session Management
- Flask session cookie is httpOnly (no JavaScript access)
- Session ID stored securely on server
- User's encryption keys are separate and unaffected

### Wallet Addresses
- Stored in database as base58-encoded public keys (44 characters)
- Unique constraint prevents duplicate accounts per wallet
- No private keys ever transmitted or stored

## Future Enhancements

1. **Multi-Signature Support**
   - Allow users to add/remove multiple wallet addresses to same account

2. **Ledger Live Integration**
   - Complete Ledger wallet support for hardware security

3. **Wallet Disconnection**
   - Add "Disconnect Wallet" option to navbar
   - Allow switching between wallets

4. **Rate Limiting**
   - Add rate limits to `/auth/nonce` and `/auth/verify` endpoints
   - Prevent brute force attacks

5. **Analytics**
   - Track wallet auth vs email auth usage
   - Monitor authentication flow completion rates

## Useful Commands

**Check installed versions:**
```bash
pip show base58 PyNaCl
```

**View Flask session contents (dev only):**
```bash
curl http://localhost:5000/__session
```

**Test nonce generation:**
```bash
curl http://localhost:5000/auth/nonce
```

**Reset database:**
```bash
rm instance/zencrypt.db  # Linux/Mac
del zencrypt.db          # Windows PowerShell
```

**Run with debug mode (dev only):**
```bash
FLASK_ENV=development FLASK_DEBUG=1 python webapp.py
```

## Support

For issues or questions:
1. Check the troubleshooting section above
2. Open DevTools Console for client-side errors
3. Check server logs (terminal output) for backend errors
4. Review the modified source files for implementation details

---

**Version:** Zencrypt v6.2.2-A2  
**Last Updated:** February 2025  
**Maintainer:** imaclone.x
