# ISG_Project/internal_site_generator/__init__.py
import os
import errno
from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from flask_login import LoginManager
from flask_wtf.csrf import CSRFProtect # <--- ADD THIS IMPORT
from .config import Config

db = SQLAlchemy()
migrate = Migrate()
login_manager = LoginManager()
csrf = CSRFProtect() # <--- INSTANTIATE CSRFProtect

login_manager.login_view = 'auth.login'
login_manager.login_message_category = 'info'

def create_app(config_class=Config):
    app = Flask(__name__, instance_relative_config=True)
    app.config.from_object(config_class)

    try:
        os.makedirs(app.instance_path)
    except OSError as e:
        if e.errno != errno.EEXIST:
            raise

    db.init_app(app)
    migrate.init_app(app, db)
    login_manager.init_app(app)
    csrf.init_app(app) # <--- INITIALIZE CSRFProtect WITH THE APP

    from .models import User

    @login_manager.user_loader
    def load_user(user_id):
        return User.query.get(int(user_id))

    from .auth import bp as auth_bp
    app.register_blueprint(auth_bp, url_prefix='/auth')

    from .main import bp as main_bp
    app.register_blueprint(main_bp)

    @app.route('/test_init/')
    def test_init_page():
        return '<h1>Testing the Flask Application Factory from __init__.py!</h1>'

    return app
