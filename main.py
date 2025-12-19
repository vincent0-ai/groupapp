import os
import sys

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app import create_app
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Create app
app, socketio = create_app(os.getenv('FLASK_ENV', 'development'))

if __name__ == '__main__':
    # Respect configuration debug flag and PORT env var
    socketio.run(app, debug=app.config.get('DEBUG', False), host='0.0.0.0', port=int(os.getenv('PORT', 5000)))
