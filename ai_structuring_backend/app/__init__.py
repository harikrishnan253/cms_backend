"""
Flask Application Factory
"""

from flask import Flask
from flask_cors import CORS

from .models import db, init_db
from .routes import api_bp
from .services import queue_service


def create_app(config_object='config'):
    """Create and configure the Flask application."""
    app = Flask(__name__)
    
    # Load config
    app.config.from_object(config_object)
    
    # Enable CORS for React frontend
    CORS(app, origins=['http://localhost:3000', 'http://127.0.0.1:3000'])
    
    # Initialize database
    init_db(app)
    
    # Initialize queue service
    queue_service.init_app(app)
    
    # Register blueprints
    app.register_blueprint(api_bp)
    
    # Health check endpoint
    @app.route('/health')
    def health():
        return {'status': 'healthy'}
    
    return app
