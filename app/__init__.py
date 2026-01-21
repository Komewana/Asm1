import os
from flask import Flask

from .config import STATIC_DIR, INPUT_DIR, OUTPUT_DIR
from .db import db_init
from .model import load_model
from .worker import start_worker_thread
from .routes import bp


def create_app():
    app = Flask(
        __name__,
        template_folder=os.path.join(os.path.dirname(os.path.dirname(__file__)), "templates"),
    )

    os.makedirs(STATIC_DIR, exist_ok=True)
    os.makedirs(INPUT_DIR, exist_ok=True)
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    db_init()
    load_model()

    app.register_blueprint(bp)
    start_worker_thread()

    return app
