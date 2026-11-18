"""Local development server:  python run.py   ->  http://127.0.0.1:5000

Plain-http development needs non-Secure session cookies; production (HTTPS) keeps the
secure default. Never expose this server beyond your own machine.
"""
import os

os.environ.setdefault("SESSION_COOKIE_SECURE", "0")

from command_centre import create_app  # noqa: E402

if __name__ == "__main__":
    create_app().run(host="127.0.0.1", port=5000, debug=True)
