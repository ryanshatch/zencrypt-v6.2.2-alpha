#!/usr/bin/env python
"""
Quick test script for Zencrypt wallet authentication flow.
Tests each step of the wallet authentication without requiring a browser.

Usage:
    python test_wallet_auth.py

Requirements:
    - Flask app running on http://localhost:5000
    - base58 and PyNaCl installed
"""

import requests
import json
from nacl.signing import SigningKey
from nacl.encoding import RawEncoder
import base58
import sys

BASE_URL = "http://localhost:5000"

def test_nonce_generation(session):
    """Test 1: Generate a nonce from the server."""
    print("\n[TEST 1] Generating nonce...")
    try:
        response = session.get(f"{BASE_URL}/auth/nonce")
        if response.status_code != 200:
            print(f"  ✗ Failed: {response.status_code}")
            return None
        
        data = response.json()
        nonce = data.get('nonce')
        if not nonce:
            print("  ✗ No nonce in response")
            return None
        
        print(f"  ✓ Nonce generated: {nonce[:16]}...")
        return nonce
    except Exception as e:
        print(f"  ✗ Error: {e}")
        return None

def test_signature_generation(nonce):
    """Test 2: Create a test wallet and sign the nonce."""
    print("\n[TEST 2] Generating test wallet and signature...")
    try:
        # Generate a random Ed25519 keypair
        signing_key = SigningKey.generate()
        verify_key = signing_key.verify_key
        
        # Get the public key in base58 format (Solana standard)
        pubkey_bytes = bytes(verify_key)
        pubkey_b58 = base58.b58encode(pubkey_bytes).decode('utf-8')
        
        print(f"  ✓ Test wallet generated: {pubkey_b58[:8]}...{pubkey_b58[-4:]}")
        
        # Sign the nonce
        message = nonce.encode('utf-8')
        signature = signing_key.sign(message, encoder=RawEncoder).signature
        signature_b64 = __import__('base64').b64encode(signature).decode('utf-8')
        
        print(f"  ✓ Nonce signed: {signature_b64[:16]}...")
        
        return pubkey_b58, signature_b64
    except Exception as e:
        print(f"  ✗ Error: {e}")
        return None, None

def test_signature_verification(session, pubkey_b58, signature_b64, nonce):
    """Test 3: Verify the signature with the server."""
    print("\n[TEST 3] Verifying signature with server...")
    try:
        payload = {
            "public_key": pubkey_b58,
            "signature_b64": signature_b64,
            "nonce": nonce
        }
        
        response = session.post(
            f"{BASE_URL}/auth/verify",
            json=payload
        )
        
        if response.status_code != 200:
            print(f"  ✗ Verification failed: {response.status_code}")
            print(f"    Response: {response.text}")
            return False
        
        data = response.json()
        if data.get('success'):
            print(f"  ✓ Signature verified!")
            print(f"    User ID: {data.get('user_id')}")
            return True
        else:
            print(f"  ✗ Verification returned false")
            print(f"    Response: {data}")
            return False
    except Exception as e:
        print(f"  ✗ Error: {e}")
        return False

def test_session_persistence(session):
    """Test 4: Check that session was created."""
    print("\n[TEST 4] Checking session persistence...")
    try:
        response = session.get(f"{BASE_URL}/__session")
        if response.status_code == 404:
            print("  ⚠ /__session endpoint not available (production mode?)")
            return None
        
        if response.status_code != 200:
            print(f"  ✗ Failed: {response.status_code}")
            return None
        
        data = response.json()
        if 'error' in data:
            print(f"  ✗ Error: {data['error']}")
            return False
        
        user_id = data.get('user_id')
        wallet = data.get('wallet_address')
        
        if user_id:
            print(f"  ✓ Session found!")
            print(f"    User ID: {user_id}")
            print(f"    Wallet: {wallet[:8]}...{wallet[-4:] if wallet else 'N/A'}")
            return True
        else:
            print(f"  ✗ No user_id in session")
            print(f"    Session data: {data}")
            return False
    except Exception as e:
        print(f"  ✗ Error: {e}")
        return False

def main():
    """Run all tests."""
    print("=" * 60)
    print("ZENCRYPT WALLET AUTH TEST SUITE")
    print("=" * 60)
    
    # Create a persistent session to maintain cookies
    session = requests.Session()
    
    # Check if server is running
    try:
        response = session.get(BASE_URL, timeout=2)
    except requests.exceptions.ConnectionError:
        print(f"\n✗ FATAL: Cannot connect to {BASE_URL}")
        print("  Please start the Flask app first:")
        print("    cd /path/to/zencrypt")
        print("    python webapp.py")
        sys.exit(1)
    except Exception as e:
        print(f"\n✗ FATAL: Connection error: {e}")
        sys.exit(1)
    
    print(f"✓ Connected to {BASE_URL}\n")
    
    # Run tests
    nonce = test_nonce_generation(session)
    if not nonce:
        print("\n✗ Cannot continue without nonce")
        sys.exit(1)
    
    pubkey_b58, signature_b64 = test_signature_generation(nonce)
    if not pubkey_b58 or not signature_b64:
        print("\n✗ Cannot continue without signature")
        sys.exit(1)
    
    verified = test_signature_verification(session, pubkey_b58, signature_b64, nonce)
    if not verified:
        print("\n✗ Signature verification failed")
        sys.exit(1)
    
    session_ok = test_session_persistence(session)
    if session_ok is False:
        print("\n✗ Session persistence test failed")
        sys.exit(1)
    
    print("\n" + "=" * 60)
    print("✓ ALL TESTS PASSED!")
    print("=" * 60)
    print("\nNext steps:")
    print("1. Open http://localhost:5000/connect-wallet in your browser")
    print("2. Install Phantom or Solflare wallet extension")
    print("3. Click the wallet button and follow the prompts")
    print("4. Sign the message when prompted")
    print("5. You should be authenticated and redirected to the dashboard")

if __name__ == '__main__':
    main()
