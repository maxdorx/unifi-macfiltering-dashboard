from __future__ import annotations

import os
from waitress import serve
from app import create_app

app = create_app()

if __name__ == "__main__":
    host = os.getenv("HOST", "0.0.0.0")
    port = int(os.getenv("PORT", "4000"))
    print(f"Starting mac-filtering on {host}:{port}")
    serve(app, host=host, port=port)
