from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from flask_login import LoginManager
from config import Config # Import the Config class


# The rest of your models and routes will eventually be in other files.
# For now, your main execution point if you run `python app.py` could be:
if __name__ == '__main__':
    application = create_app()
    application.run(debug=True)
