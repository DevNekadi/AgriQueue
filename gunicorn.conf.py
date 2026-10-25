"""
Gunicorn configuration for production deployment (Render / Linux).
Binds dynamically to the PORT environment variable assigned by the host.
"""

import os

# Render automatically injects the PORT environment variable
port = os.environ.get("PORT", "5000")
bind = f"0.0.0.0:{port}"

# Concurrency & Worker configuration
workers = int(os.environ.get("WEB_CONCURRENCY", "2"))
threads = int(os.environ.get("PYTHON_GET_THREADS", "2"))
timeout = 120

accesslog = "-"
errorlog = "-"
