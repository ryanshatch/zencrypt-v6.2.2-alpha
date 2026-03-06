"""
********************************************************************************************
* Title: Zencrypt WebApp           |********************************************************
* Developed by: Ryan Hatch         |********************************************************
* Date: August 10th 2022           |********************************************************
* Last Updated: Febuary 13th 2025  |********************************************************
* Version: 6.2-A                   |********************************************************
********************************************************************************************
*****************************#*| Zencrypt v6.2-A |******************************************
<><><><><><><><><><><><><><><><><><><><><><><><><><><><><><><><><><><><><><><><><><><><><><>
********************************#* Description: |*******************************************
<><><><><><><><><><><><><><><><><><><><><><><><><><><><><><><><><><><><><><><><><><><><><><>
*              Zencrypt Web-App is a Flask application that can be used to:                *
*       - Generate hashes: using SHA256 hashing algorithm, with an optional salt value.    *
*       - Encrypt text and files: using Fernet symmetric encryption algorithm.             *
<><><><><><><><><><><><><><><><><><><><><><><><><><><><><><><><><><><><><><><><><><><><><><>
""""""********************#* Web-App Implementations: |*************************************
- The CLI and webapp code are separated for clarity, scalability and modularity.           *
- The Web-App uses Flask and cryptography libraries with a HTML interface for the UI/UX.   *
- The webapp v5 is hosted on a local server, and can be accessed via a web browser.        *
********************************************************************************************
*           #* Some key differences in the Web-Apps functionality are:                     *
- Securely handle MongoDB operations for storing hashes and encrypted texts.               *
- Implement user authentication and session management using JWT tokens.                   *
- Handle file uploads, encryption/decryption, and text input handling.                     *
- Its also important to note that PGP encryption is not implemented currently in v5.3,     *
    but will be in the final stages of Zencrypt v6-A1                                      *
********************************************************************************************
"""

from models import db, User, Hash, EncryptedText, Key, PGPKey  # Add PGPKey here
#* Importing the required libraries for the webapp
from flask import Flask, request, render_template_string, redirect, url_for, session, jsonify, send_from_directory
from flask_sqlalchemy import SQLAlchemy
from flask_jwt_extended import JWTManager, create_access_token, jwt_required, get_jwt_identity
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_wtf.csrf import CSRFProtect, generate_csrf
from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives.asymmetric import rsa, padding
from cryptography.hazmat.primitives import serialization
from werkzeug.security import generate_password_hash, check_password_hash
from markupsafe import escape
import hashlib
import logging
import os
import re
import base64
import secrets
from datetime import timedelta
from dotenv import load_dotenv
from utils import generate_pgp_keypair, pgp_encrypt_message, pgp_decrypt_message
from flask_migrate import Migrate
from crypto_utils import ECCHandler, Argon2Handler, ParallelFileProcessor
from config import config

logger = logging.getLogger(__name__)

# #* ---------------------- | Environment & Database Configuration | ---------------------- #

# Load environment variables from .env file
load_dotenv()

# Flask Configuration and JWT Manager
app = Flask(__name__)
config_name = os.getenv('FLASK_ENV', 'default')
app.config.from_object(config[config_name])
config[config_name].init_app(app)

# SQLite Configuration
basedir = os.path.abspath(os.path.dirname(__file__))
app.config['SQLALCHEMY_DATABASE_URI'] = os.getenv('SQLALCHEMY_DATABASE_URI', f'sqlite:///{basedir}/zencrypt.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# Initialize database
db.init_app(app)
migrate = Migrate(app, db)

# Create tables
with app.app_context():
    db.create_all()

# SECRET_KEY must be set to a stable value so sessions survive restarts.
# os.urandom(24) as a fallback means every restart invalidates all sessions.
_secret_key = os.environ.get('SECRET_KEY')
if not _secret_key:
    if os.getenv('FLASK_ENV') == 'production':
        raise RuntimeError('SECRET_KEY environment variable must be set in production')
    _secret_key = secrets.token_hex(32)
app.secret_key = _secret_key

# CSRF protection configuration
app.config['WTF_CSRF_TIME_LIMIT'] = 3600  # 1 hour

# #* ---------------------- | JWT Configuration | ---------------------- #

# JWT secret key — require an explicit value so JWT tokens are never signed with None
_jwt_secret = os.getenv('JWT_SECRET_KEY') or _secret_key
if not _jwt_secret:
    raise RuntimeError('JWT_SECRET_KEY (or SECRET_KEY) environment variable must be set')
app.config['JWT_SECRET_KEY'] = _jwt_secret
app.config['JWT_ACCESS_TOKEN_EXPIRES'] = timedelta(hours=1)

# Initialize JWT Manager
jwt = JWTManager(app)

# #* ---------------------- | Rate limiting | ---------------------- #

limiter = Limiter(
    get_remote_address,
    app=app,
    default_limits=["200 per day", "50 per hour"],
    storage_uri="memory://"
)

# #* ---------------------- | CSRF Protection | ---------------------- #

csrf = CSRFProtect(app)

# #* ---------------------- | Key Management | ---------------------- #
def initialize_key(user_id):
    """Initialize or retrieve encryption key for a user"""
    # Check for existing active key
    key = Key.query.filter_by(user_id=user_id, active=True).first()
    
    if key:
        return key.key_value.encode()
    
    # Generate new key
    new_key = Fernet.generate_key()
    
    # Store in database
    key_entry = Key(
        key_value=new_key.decode(),
        user_id=user_id
    )
    
    try:
        db.session.add(key_entry)
        db.session.commit()
        return new_key
    except Exception as e:
        db.session.rollback()
        print(f"Error storing key: {e}")
        # Fallback to temporary key if database storage fails
        return Fernet.generate_key()

def get_cipher_suite(user_id):
    """Get Fernet cipher suite for a user"""
    key = initialize_key(user_id)
    return Fernet(key)

def rotate_key(user_id):
    """Rotate encryption key for a user"""
    try:
        # Deactivate old key
        old_key = Key.query.filter_by(user_id=user_id, active=True).first()
        if old_key:
            old_key.active = False
            
        # Generate and store new key
        new_key = Fernet.generate_key()
        key_entry = Key(
            key_value=new_key.decode(),
            user_id=user_id
        )
        
        db.session.add(key_entry)
        db.session.commit()
        
        return new_key
    except Exception as e:
        db.session.rollback()
        print(f"Error rotating key: {e}")
        return None

def initialize_ecc():
    """Initialize ECC handler for the application"""
    return ECCHandler(curve=app.config['ECC_CURVE'])

def initialize_argon2():
    """Initialize Argon2 handler for the application"""
    return Argon2Handler(
        time_cost=app.config['ARGON2_TIME_COST'],
        memory_cost=app.config['ARGON2_MEMORY_COST'],
        parallelism=app.config['ARGON2_PARALLELISM']
    )

def get_file_processor():
    """Get configured file processor instance"""
    return ParallelFileProcessor(
        num_workers=app.config['MAX_WORKERS'],
        chunk_size=app.config['CHUNK_SIZE'],
        use_processes=app.config['USE_PROCESSES']
    )

# #* ---------------------- | Security Response Headers | ---------------------- #

@app.after_request
def add_security_headers(response):
    """Add security-relevant HTTP response headers to every response."""
    response.headers['X-Frame-Options'] = 'DENY'
    response.headers['X-Content-Type-Options'] = 'nosniff'
    # X-XSS-Protection is deprecated in modern browsers but retained for
    # defense-in-depth coverage on legacy browsers that still honour it.
    response.headers['X-XSS-Protection'] = '1; mode=block'
    response.headers['Referrer-Policy'] = 'strict-origin-when-cross-origin'
    response.headers['Permissions-Policy'] = 'geolocation=(), camera=(), microphone=()'
    if not app.debug:
        response.headers['Strict-Transport-Security'] = 'max-age=31536000; includeSubDomains'
    return response

# #* ---------------------- | Styling and HTML for the Web-App | ---------------------- #

STYLE_TEMPLATE = """
    body {
        background-color: #1e1e1e;
        color: #ffffff;
        font-family: 'Nunito Sans', sans-serif;
        line-height: 1.6;
        margin: 0;
        padding: 0;
        min-height: 100vh;
        display: flex;
        flex-direction: column;
    }
    .container {
        width: 95%;
        max-width: 1200px;
        margin: 0 auto;
        padding: 20px;
        flex: 1;
    }
    .form-container {
        width: 95%;
        max-width: 600px;
        margin: 2rem auto;
        padding: 2rem;
        display: flex;
        flex-direction: column;
        align-items: center;
    }
    .form-container form {
        width: 100%;
        display: flex;
        flex-direction: column;
        align-items: center;
        gap: 1rem;
    }
    .button-wrapper {
        width: 100%;
        display: flex;
        justify-content: center;
        margin: 1rem 0;
    }
    textarea, input[type="text"], input[type="password"], input[type="email"] {
        width: 100%;
        padding: 15px;
        font-size: 16px;
        border-radius: 5px;
        background-color: #2d2d2d;
        color: #ffffff;
        border: 1px solid #444;
        transition: border-color 0.3s ease;
    }
    textarea {
        height: 10vh;
        resize: vertical;
    }
    textarea:focus, input:focus {
        border-color: #0066ff;
        outline: none;
    }
    button {
        width: 100%;
        max-width: 300px;
        padding: 15px;
        font-size: 16px;
        border-radius: 5px;
        background-color: #0066ff;
        color: #ffffff;
        border: none;
        cursor: pointer;
        transition: background-color 0.3s ease;
    }
    button:hover {
        background-color: #0052cc;
    }
    .menu {
        display: flex;
        flex-wrap: wrap;
        gap: 10px;
        justify-content: center;
        margin: 20px 0;
    }
    .menu form {
        margin: 0;
    }
    .menu input[type="file"] {
        display: none;
    }
    .menu button {
        margin: 0;
        padding: 8px 16px;
        white-space: nowrap;
    }
    .auth-container {
        width: 100%;
        max-width: 400px;
        margin: 2rem auto;
        padding: 2rem;
    }
    .navbar {
        background-color: #1e1e1e;
        border-bottom: 1px solid #444;
        padding: 1rem;
        width: 100%;
        box-shadow: 0 2px 4px rgba(0,0,0,0.2);
    }
    .navbar-container {
        max-width: 1200px;
        margin: 0 auto;
        display: flex;
        justify-content: space-between;
        align-items: center;
    }
    .navbar-brand {
        font-size: 1.5rem;
        font-weight: bold;
        color: #ffffff;
        cursor: pointer;
        user-select: none;
        padding: 0.5rem;
    }
    .navbar-menu {
        background-color: #1e1e1e;
        border-bottom: 1px solid #444;
        padding: 1rem;
        display: none;
    }
    .navbar-menu.active {
        display: block;
    }
    .main-content {
        padding: 2rem 1rem;
        flex: 1;
    }
    @media (max-width: 768px) {
        .container {
            width: 95%;
            padding: 10px;
        }
        .menu {
            flex-direction: column;
            align-items: stretch;
        }
        .menu button {
            width: 100%;
            margin: 5px 0;
        }
        .form-container {
            padding: 1rem;
        }
    }
"""

# Define header/banner separately as it's reused
HEADER_TEMPLATE = """
    <div class="header">
        <div style="text-align: center; font-family: 'Helvetica', sans-serif; color: #999;">
            <p style="font-size: 1.1em; margin: 0.5em 0;">
                <span style="font-family: 'Consolas', monospace;">© 2025</span> 
                All rights reserved by 
                <span style="font-family: 'Consolas', monospace; color: #0066ff;">Ryanshatch</span>
            </p>
        </div>
    </div>
"""

# Main application template
APP_TEMPLATE = f"""
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Zencrypt Web-App</title>
    <link rel="icon" type="image/x-icon" href="/favicon.ico">
    <link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Nunito+Sans:wght@400;600&display=swap">
    <style>
        {STYLE_TEMPLATE}
    </style>
    <script crossorigin src="https://unpkg.com/react@17/umd/react.development.js"></script>
    <script crossorigin src="https://unpkg.com/react-dom@17/umd/react-dom.development.js"></script>
</head>
<body>
    <div class="main-content">
        {HEADER_TEMPLATE}
        
        {{% if session.get('user_id') %}}
            <nav class="navbar">
                <div class="navbar-container">
                    <div class="navbar-brand" onclick="toggleMenu()">
                        ☰ Zencrypt
                        <span style="font-size: 1.0rem;"></span>
                    </div>
                    <div class="navbar-menu" id="navMenu">
                        <a href="/"><button>Generate Hash</button></a>
                        <a href="/encrypt"><button>Encrypt Text</button></a>
                        <a href="/decrypt"><button>Decrypt Text</button></a>
                        <a href="/file"><button>Encode / Decode .txt Files</button></a>
                        <a href="/pgp"><button>PGP Encryption</button></a>
                        <a href="/advanced"><button>AAC & Argon2</button></a>
                        <a href="/export-key"><button>Export Key</button></a>
                        <a href="/import-key"><button>Import Key</button></a>
                        <a href="/logout"><button>Logout</button></a>
                    </div>
                </div>
            </nav>
            <hr style="border: 0; height: 1px; background-image: linear-gradient(to right, rgba(0, 102, 255, 0), rgba(0, 102, 255, 0.75), rgba(0, 102, 255, 0));">
            {{{{ content | safe }}}}
            {{% if output %}}
                <div class="output">{{{{ output }}}}</div>
            {{% endif %}}
        {{% else %}}
            <div class="auth-container">
                <h2>{{% if request.path == '/register' %}}Register{{% else %}}Login{{% endif %}}</h2>
                {{% if error %}}
                    <div class="error-message">{{{{ error }}}}</div>
                {{% endif %}}
                <form method="POST" action="{{% if request.path == '/register' %}}/register{{% else %}}/login{{% endif %}}">
                    <input type="hidden" name="csrf_token" value="{{{{ csrf_token() }}}}">
                    <input type="email" name="email" placeholder="Email" required>
                    <input type="password" name="password" placeholder="Password" required>
                    <button type="submit">{{% if request.path == '/register' %}}Register{{% else %}}Login{{% endif %}}</button>
                </form>
                {{% if request.path == '/register' %}}
                    <p>Already have an account? <a href="/login">Login</a></p>
                {{% else %}}
                    <p>Don't have an account? <a href="/register">Register</a></p>
                {{% endif %}}
            </div>
            <hr style="border: 0; height: 1px; background-image: linear-gradient(to right, rgba(0, 102, 255, 0), rgba(0, 102, 255, 0.75), rgba(0, 102, 255, 0));">
            <h1 style="text-align: center;">Zencrypt Web-App</h1>
            <div class="links">
                <h6 style="text-align: center;">
                <li><b>White Papers</b> - <a href="https://zencrypt.gitbook.io/zencrypt" target="_blank">https://zencrypt.gitbook.io/zencrypt</a></li>
                <li><b>ePortfolio</b> - <a href="https://www.ryanshatch.com" target="_blank">https://www.ryanshatch.com</a></li>
                </h6>
            </div>
            <hr style="border: 0; height: 1px; background-image: linear-gradient(to right, rgba(0, 102, 255, 0), rgba(0, 102, 255, 0.75), rgba(0, 102, 255, 0));">
        {{% endif %}}
    </div>
    <script>
        function toggleMenu() {{
            const menu = document.getElementById('navMenu');
            menu.classList.toggle('active');
        }}
        
        // Close menu when clicking outside
        document.addEventListener('click', function(event) {{
            const menu = document.getElementById('navMenu');
            const menuButton = document.querySelector('.navbar-brand');
            
            if (!menu.contains(event.target) && !menuButton.contains(event.target)) {{
                menu.classList.remove('active');
            }}
        }});
        
        // Close menu when scrolling
        let lastScroll = 0;
        window.addEventListener('scroll', function() {{
            const menu = document.getElementById('navMenu');
            const currentScroll = window.pageYOffset;
            
            if (currentScroll > lastScroll) {{
                menu.classList.remove('active');
            }}
            lastScroll = currentScroll;
        }});
    </script>
</body>
</html>
"""

# * ---------------------- | Web-App Routes | ---------------------- #
# * Checks if the database is connected and returns an error message if not connected when the webapp is started.
def safe_db_operation(operation): 
    if db is None:                                      # Check if the database is connected
        return None, "Database not connected"           # Return an error message if the database is not connected
    try:
        result = operation()                            # Perform the database operation and store the result
        return result, None                             # Return the result and no error message if the operation is successful
    except Exception as e:                              # Catch any exceptions that occur during the database operation
        print(f"Database operation error: {e}")         # Print an error message if the database operation fails
        return None, str(e)                             # Return no result and an error message if the operation fails

#* ---------------------- | Favicon Route | ---------------------- #
@app.route('/favicon.ico')
def favicon():
    return send_from_directory(
        os.path.join(app.root_path, 'static'),
        'favicon.ico',
        mimetype='image/vnd.microsoft.icon'
    )

#* ---------------------- | Authentication Routes | ---------------------- #
@app.route('/login', methods=['GET', 'POST'])
@limiter.limit("10 per minute")
def login():
    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')
        
        user = User.query.filter_by(email=email).first()
        
        if user and check_password_hash(user.password_hash, password):
            session['user_id'] = user.id
            access_token = create_access_token(identity=user.id)
            session['access_token'] = access_token
            return redirect(url_for('hash_page'))
        
        return render_template_string(APP_TEMPLATE, error="Invalid credentials")
    
    return render_template_string(APP_TEMPLATE)

#* ---------------------- | Registration Route | ---------------------- #
@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')
        
        if not email or not password:
            return render_template_string(APP_TEMPLATE, 
                error="Email and password are required")
            
        if User.query.filter_by(email=email).first():
            return render_template_string(APP_TEMPLATE, 
                error="Email already exists")
        
        try:
            user = User(
                email=email,
                password_hash=generate_password_hash(password)
            )
            db.session.add(user)
            db.session.commit()

            initialize_key(user.id)
            return redirect(url_for('login'))
        except Exception as e:
            db.session.rollback()
            logger.error("Registration error: %s", e)
            return render_template_string(APP_TEMPLATE,
                error="Registration failed. Please try again.")
    
    return render_template_string(APP_TEMPLATE)

#* ---------------------- | Logout Route | ---------------------- #
@app.route('/logout')
def logout():
    user_id = session.get('user_id')
    if user_id:
    #* ---------------------- | Deleting Logged Data | ---------------------- #
        # try:
        #     # Clean up user data
        #     Hash.query.filter_by(user_id=user_id).delete()
        #     EncryptedText.query.filter_by(user_id=user_id).delete()
        #     # Deactivate user's keys
        #     Key.query.filter_by(user_id=user_id, active=True).update({"active": False})
        #     db.session.commit()
        # except Exception as e:
        #     db.session.rollback()
        #     print(f"Error cleaning up user data: {e}")
        pass
    
    session.clear()
    return redirect(url_for('login'))

#* ---------------------- | Encryption & Decryption Routes | ---------------------- #
@app.route('/', methods=['GET', 'POST'])
def hash_page():
    if not session.get('user_id'):
        return redirect(url_for('login'))

    token = generate_csrf()
    content = f"""
    <div class="form-container">
        <form method="POST">
            <input type="hidden" name="csrf_token" value="{token}">
            <textarea name="text" placeholder="Enter text to hash"></textarea>
            <input type="text" name="salt" placeholder="Salt (optional)">
            <div class="button-wrapper">
                <button type="submit">Generate Hash</button>
            </div>
        </form>
    </div>
    """
    
    if request.method == 'POST':
        text = request.form.get('text', '')
        salt = request.form.get('salt', '')
        if text:
            hash_value = hashlib.sha256((text + salt).encode()).hexdigest()
            
            new_hash = Hash(
                hash_value=hash_value,
                salt=salt,
                user_id=session['user_id']
            )
            db.session.add(new_hash)
            db.session.commit()
            
            return render_template_string(APP_TEMPLATE,
                content=content,
                output=f"SHA256 Hash:\n{hash_value}")
    
    return render_template_string(APP_TEMPLATE, content=content)

@app.route('/encrypt', methods=['GET', 'POST'])
def encrypt_page():
    if not session.get('user_id'):
        return redirect(url_for('login'))

    token = generate_csrf()
    content = f"""
    <div class="form-container">
        <form method="POST">
            <input type="hidden" name="csrf_token" value="{token}">
            <textarea name="text" placeholder="Enter text to encrypt"></textarea>
            <div class="button-wrapper">
                <button type="submit">Encrypt</button>
            </div>
        </form>
    </div>
    """

    if request.method == 'POST':
        text = request.form.get('text', '')
        if text:
            try:
                cipher_suite = get_cipher_suite(session['user_id'])
                encrypted = cipher_suite.encrypt(text.encode())

                # Store in database
                new_encrypted = EncryptedText(
                    encrypted_content=encrypted.decode(),
                    user_id=session['user_id']
                )
                db.session.add(new_encrypted)
                db.session.commit()

                return render_template_string(APP_TEMPLATE,
                    content=content,
                    output=f"Encrypted Text:\n{encrypted.decode()}")
            except Exception as e:
                db.session.rollback()
                logger.error("Encryption error: %s", e)
                return render_template_string(APP_TEMPLATE,
                    content=content,
                    output="Encryption failed. Please try again.")

    return render_template_string(APP_TEMPLATE, content=content)

#* Route to the decrypt text page of the web-app with the decryption function
@app.route('/decrypt', methods=['GET', 'POST'])
def decrypt_page():
    if not session.get('user_id'):
        return redirect(url_for('login'))

    token = generate_csrf()
    content = f"""
    <div class="form-container">
        <form method="POST">
            <input type="hidden" name="csrf_token" value="{token}">
            <textarea name="text" placeholder="Enter text to decrypt"></textarea>
            <div class="button-wrapper">
                <button type="submit">Decrypt</button>
            </div>
        </form>
    </div>
    """

    if request.method == 'POST':
        text = request.form.get('text', '')
        if text:
            try:
                cipher_suite = get_cipher_suite(session['user_id'])
                decrypted = cipher_suite.decrypt(text.encode())
                return render_template_string(APP_TEMPLATE,
                    content=content,
                    output=f"Decrypted Text:\n{decrypted.decode()}")
            except InvalidToken:
                return render_template_string(APP_TEMPLATE,
                    content=content,
                    output="Decryption failed: invalid ciphertext or wrong key.")
            except Exception as e:
                logger.error("Decryption error: %s", e)
                return render_template_string(APP_TEMPLATE,
                    content=content,
                    output="Decryption failed. Please try again.")

    return render_template_string(APP_TEMPLATE, content=content)

#* ---------------------- | File Operations Route | ---------------------- #
#* Route to the file operations page of the web-app with the file encryption/decryption function
@app.route('/file', methods=['GET', 'POST'])
def file_page():
    if not session.get('user_id'):
        return redirect(url_for('login'))

    token = generate_csrf()
    content = f"""
    <div class="form-container">
        <form method="POST" enctype="multipart/form-data" style="text-align: center;">
            <input type="hidden" name="csrf_token" value="{token}">
            <div class="file-upload-wrapper" style="margin: 20px 0;">
                <label for="file-upload" class="custom-file-upload" style="
                    display: inline-block;
                    padding: 10px 20px;
                    background: #2d2d2d;
                    color: #fff;
                    border: 1px solid #444;
                    border-radius: 5px;
                    cursor: pointer;
                    margin-bottom: 10px;">
                    Choose File
                </label>
                <input id="file-upload" type="file" name="file" required style="display: none;">
                <div id="file-name" style="margin-top: 5px; color: #999;"></div>
            </div>
            <input type="password" name="password" placeholder="Enter Password" required style="width: 75%;">
            <select name="operation" style="
                width: 75%;
                padding: 15px;
                margin: 20px 0;
                background-color: #2d2d2d;
                color: #ffffff;
                border: 1px solid #444;
                border-radius: 5px;">
                <option value="encrypt">Encrypt File</option>
                <option value="decrypt">Decrypt File</option>
            </select>
            <div class="button-wrapper">
                <button type="submit">Process File</button>
            </div>
        </form>
    </div>
    <script>
        document.getElementById('file-upload').onchange = function() {{
            document.getElementById('file-name').textContent = this.files[0] ? this.files[0].name : '';
        }};
    </script>
    """

    if request.method == 'POST':
        if 'file' not in request.files:
            return render_template_string(APP_TEMPLATE,
                content=content,
                output="Please select a file to process")

        file = request.files['file']
        if file.filename == '':
            return render_template_string(APP_TEMPLATE,
                content=content,
                output="No file selected")

        try:
            file_content = file.read()
            password = request.form.get('password', '').encode()
            operation = request.form.get('operation')

            if not password:
                return render_template_string(APP_TEMPLATE,
                    content=content,
                    output="Password is required")

            cipher_suite = get_cipher_suite(session['user_id'])
            if operation == 'encrypt':
                encrypted = cipher_suite.encrypt(file_content)
                return render_template_string(APP_TEMPLATE,
                    content=content,
                    output=f"File encrypted successfully!\nEncrypted content:\n{base64.b64encode(encrypted).decode()}")
            else:
                try:
                    decrypted = cipher_suite.decrypt(base64.b64decode(file_content))
                    return render_template_string(APP_TEMPLATE,
                        content=content,
                        output=f"File decrypted successfully!\nDecrypted content:\n{decrypted.decode()}")
                except Exception:
                    return render_template_string(APP_TEMPLATE,
                        content=content,
                        output="Invalid encrypted file or wrong key")

        except Exception as e:
            logger.error("File processing error: %s", e)
            return render_template_string(APP_TEMPLATE,
                content=content,
                output="Error processing file. Please try again.")

    return render_template_string(APP_TEMPLATE, content=content)

@app.route('/export-key', methods=['GET', 'POST'])
def export_key():
    if not session.get('user_id'):
        return redirect(url_for('login'))

    try:
        key = Key.query.filter_by(user_id=session['user_id'], active=True).first()
        if key:
            # Sanitize key_name: only allow alphanumeric chars, hyphens, and underscores
            # to prevent Content-Disposition header injection
            raw_name = request.args.get('key_name', 'zen_key')
            key_name = re.sub(r'[^a-zA-Z0-9_-]', '', raw_name) or 'zen_key'
            response = app.response_class(
                key.key_value,
                mimetype='application/octet-stream',
                headers={'Content-Disposition': f'attachment; filename="{key_name}.key"'}
            )
            return response
        return "No active key found", 404
    except Exception as e:
        logger.error("Key export error: %s", e)
        return "Error exporting key", 500

@app.route('/import-key', methods=['GET', 'POST'])
def import_key():
    if not session.get('user_id'):
        return redirect(url_for('login'))

    if request.method == 'GET':
        # Show the file upload form
        token = generate_csrf()
        content = f"""
        <div class="form-container">
            <form method="POST" action="/import-key" enctype="multipart/form-data">
                <input type="hidden" name="csrf_token" value="{token}">
                <input type="file" name="key_file" style="display: none;" id="key_file" onchange="this.form.submit()">
                <button type="button" onclick="document.getElementById('key_file').click()">Import Key</button>
            </form>
        </div>
        """
        return render_template_string(APP_TEMPLATE, content=content)

    # Handle POST request (file upload)
    if 'key_file' not in request.files:
        return redirect(url_for('hash_page'))

    file = request.files['key_file']
    if file.filename == '':
        return redirect(url_for('hash_page'))

    try:
        key_content = file.read().decode().strip()

        # Validate that the uploaded file is a well-formed Fernet key
        # before replacing the user's active key.
        # Fernet raises ValueError for malformed keys (wrong length / bad base64).
        try:
            Fernet(key_content.encode())
        except ValueError:
            token = generate_csrf()
            content = f"""
            <div class="form-container">
                <form method="POST" action="/import-key" enctype="multipart/form-data">
                    <input type="hidden" name="csrf_token" value="{token}">
                    <input type="file" name="key_file" style="display: none;" id="key_file" onchange="this.form.submit()">
                    <button type="button" onclick="document.getElementById('key_file').click()">Import Key</button>
                </form>
            </div>
            """
            return render_template_string(APP_TEMPLATE, content=content,
                error="Invalid key file: not a valid Fernet key.")

        # Deactivate old key and store the new one
        Key.query.filter_by(user_id=session['user_id'], active=True).update({"active": False})
        new_key = Key(
            key_value=key_content,
            user_id=session['user_id'],
            active=True
        )
        db.session.add(new_key)
        db.session.commit()
        return redirect(url_for('hash_page'))
    except Exception as e:
        db.session.rollback()
        logger.error("Key import error: %s", e)
        return "Error importing key", 500

@app.route('/pgp', methods=['GET'])
def pgp_page():
    if not session.get('user_id'):
        return redirect(url_for('login'))

    token = generate_csrf()
    content = f"""
    <div class="form-container">
        <form method="POST" action="/pgp/generate">
            <input type="hidden" name="csrf_token" value="{token}">
            <div class="button-wrapper">
                <button type="submit">Generate Keys</button>
            </div>
        </form>
        <form method="POST" action="/pgp/encrypt">
            <input type="hidden" name="csrf_token" value="{token}">
            <textarea name="message" placeholder="Message:"></textarea>
            <input type="text" name="recipient_email" placeholder="Email of recipient" required>
            <div class="button-wrapper">
                <button type="submit">Encrypt</button>
            </div>
        </form>
        <form method="POST" action="/pgp/decrypt">
            <input type="hidden" name="csrf_token" value="{token}">
            <textarea name="encrypted_message" placeholder="Message:"></textarea>
            <div class="button-wrapper">
                <button type="submit">Decrypt</button>
            </div>
        </form>
    </div>
    """

    return render_template_string(APP_TEMPLATE, content=content)

@app.route('/pgp/generate', methods=['POST'])
def generate_pgp():
    if not session.get('user_id'):
        return redirect(url_for('login'))

    try:
        private_key, public_key = generate_pgp_keypair()

        # Deactivate old keys
        PGPKey.query.filter_by(user_id=session['user_id'], active=True).update({"active": False})

        # Store new keys
        new_keys = PGPKey(
            public_key=public_key,
            private_key=private_key,
            user_id=session['user_id']
        )

        db.session.add(new_keys)
        db.session.commit()

        return redirect(url_for('pgp_page'))
    except Exception as e:
        logger.error("PGP key generation error: %s", e)
        return "Error generating PGP keys", 500

@app.route('/pgp/encrypt', methods=['POST'])
def pgp_encrypt():
    if not session.get('user_id'):
        return redirect(url_for('login'))

    message = request.form.get('message')
    recipient_email = request.form.get('recipient_email')

    try:
        recipient = User.query.filter_by(email=recipient_email).first()
        if not recipient:
            return "Recipient not found", 404

        recipient_key = PGPKey.query.filter_by(user_id=recipient.id, active=True).first()
        if not recipient_key:
            return "Recipient has no active PGP key", 400

        encrypted = pgp_encrypt_message(message, recipient_key.public_key)
        # escape() prevents XSS if ciphertext somehow contains HTML-special chars
        return render_template_string(APP_TEMPLATE,
            content=f"Encrypted message:<br><textarea readonly>{escape(encrypted)}</textarea>")
    except Exception as e:
        logger.error("PGP encrypt error: %s", e)
        return "Error encrypting message", 500

@app.route('/pgp/decrypt', methods=['POST'])
def pgp_decrypt():
    if not session.get('user_id'):
        return redirect(url_for('login'))

    encrypted_message = request.form.get('encrypted_message')

    try:
        user_key = PGPKey.query.filter_by(user_id=session['user_id'], active=True).first()
        if not user_key:
            return "No active PGP key found", 400

        decrypted = pgp_decrypt_message(encrypted_message, user_key.private_key)
        # escape() is critical here: decrypted content is user-controlled and must
        # not be injected raw into the HTML (XSS prevention)
        return render_template_string(APP_TEMPLATE,
            content=f"Decrypted message:<br><textarea readonly>{escape(decrypted)}</textarea>")
    except Exception as e:
        logger.error("PGP decrypt error: %s", e)
        return "Error decrypting message", 500

@app.route('/advanced', methods=['GET', 'POST'])
@jwt_required()
@csrf.exempt
def advanced_crypto():
    if request.method == 'POST':
        operation = request.form.get('operation')
        
        if operation == 'ecc':
            ecc = initialize_ecc()
            private_key, public_key = ecc.generate_keypair()
            # Store keys in session or database as needed
            return jsonify({'status': 'ECC keys generated'})
            
        elif operation == 'argon2':
            password = request.form.get('password')
            argon2_handler = initialize_argon2()
            hashed = argon2_handler.hash_password(password)
            return jsonify({'hash': hashed})
            
        elif operation == 'parallel_encrypt':
            if 'file' not in request.files:
                return jsonify({'error': 'No file provided'})
                
            file = request.files['file']
            processor = ParallelFileProcessor()
            
            # Process file in parallel using current encryption method
            def encrypt_chunk(chunk: bytes) -> bytes:
                cipher_suite = get_cipher_suite(session['user_id'])
                return cipher_suite.encrypt(chunk)
                
            encrypted = processor.process_file_parallel(file, encrypt_chunk)
            return jsonify({'status': 'File encrypted', 'size': len(encrypted)})
    
    return render_template_string(APP_TEMPLATE, 
        content="Advanced Cryptography Options")

#<><><><><><><><><><><><><><><><><><><><><><><><><><><><><><><><><><><><><><><><><><><><><><><><><><><><><><><><><><><><><><><><><><><>
#* TRIFORCE ASCII ART BANNER FOR THE WEB-APP     <><><><><><><><><><><><><><><><><><><><><><><><><><><><><><><><><><><><><><><><><><><>
#<><><><><><><><><><><><><><><><><><><><><><><><><><><><><><><><><><><><><><><><><><><><><><><><><><><><><><><><><><><><><><><><><><><>
# #* ---------------------- | Triforce ASCII Art Banner | ---------------------- #
BOLD = '\033[1m'
END = '\033[0m'

ASCII_BANNER = f"""

                           /\\
                          /__\\
                         /\\  /\\
                        /__\\/__\\
                       /\\      /\\
                      /__\\    /__\\
                     /\\  /\\  /\\  /\
                    /__\\/__\\/__\\/__\
                    
"""
#* Function to print the Zencrypt banner in the console along with Zencrypt whitepapers and ePortfolio links to my website.
def print_startup_banner():
    print(ASCII_BANNER)
    print(f"{BOLD}Zencrypt Web-App{END} - Developed And Owned Entirely By Ryanshatch{END}\n")
    print(f"Zencrypt {BOLD}Whitepapers and Docs{END} - {BOLD}https://zencrypt.gitbook.io/zencrypt{END}")
    print(f"{BOLD}ePortfolio{END} - {BOLD}https://www.ryanshatch.com{END}\n")
    print(f"Thank you for using Zencrypt {BOLD}v5.3-A2{END}\n")
    print(f"{BOLD}The Web App is now successfully up and running: http://localhost:5000/{END}\n\n")

#* Main function to run the Flask application
if __name__ == '__main__':
    print_startup_banner()
    if os.getenv('FLASK_ENV') == 'production':
        if not os.getenv('SECRET_KEY'):
            print("Please set the SECRET_KEY environment variable")
            exit(1) # Exit if SECRET_KEY is not set
        initialize_key() # Initialize the encryption key for the user
        app.run(host='0.0.0.0', port=5000, debug=False)  # Let Nginx handle SSL
    else:
        app.run(host='0.0.0.0', port=5000, debug=False)
