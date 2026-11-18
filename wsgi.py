"""WSGI entry point (gunicorn / PythonAnywhere): ``application``."""
from command_centre import create_app

application = create_app()
app = application
