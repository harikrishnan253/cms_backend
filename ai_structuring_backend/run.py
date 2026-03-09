#!/usr/bin/env python3
"""
Run the Pre-Editor backend server.
"""

import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

from app import create_app

app = create_app()

if __name__ == '__main__':
    port = int(os.getenv('PORT', 5000))
    debug = os.getenv('FLASK_DEBUG', 'true').lower() == 'true'
    
    print(f"""
╔══════════════════════════════════════════════════════════════╗
║           S4Carlisle Pre-Editor v3 - Backend                 ║
╠══════════════════════════════════════════════════════════════╣
║  API Server:  http://localhost:{port}                          ║
║  Health:      http://localhost:{port}/health                   ║
║  Queue API:   http://localhost:{port}/api/queue/status         ║
╚══════════════════════════════════════════════════════════════╝
    """)
    
    app.run(host='0.0.0.0', port=port, debug=debug)
