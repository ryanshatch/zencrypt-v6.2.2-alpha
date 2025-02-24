import os
from webapp import app, db

def init_db():
    with app.app_context():
        db.create_all()
        print("Database initialized successfully!")

def main():
    # Ensure the static directory exists
    os.makedirs('static', exist_ok=True)
    
    # Initialize database if it doesn't exist
    if not os.path.exists('zencrypt.db'):
        init_db()
    
    # Run the application
    app.run(host='0.0.0.0', port=5000)

if __name__ == '__main__':
    main()
