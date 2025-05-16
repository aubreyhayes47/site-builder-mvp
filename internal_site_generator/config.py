# ISG_Project/internal_site_generator/config.py
import os

# basedir is ISG_Project/internal_site_generator/
basedir_package = os.path.abspath(os.path.dirname(__file__))
# project_root is one level up from basedir_package
project_root = os.path.dirname(basedir_package)

class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'your-secret-key-for-dev'
    # Point to the instance folder at the project root level
    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL') or \
        'sqlite:///' + os.path.join(project_root, 'instance', 'app.db')
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    UPLOAD_FOLDER_RELATIVE = 'user_uploads' # Relative to instance_path or project_root
    UPLOAD_FOLDER = os.path.join(project_root, 'instance', UPLOAD_FOLDER_RELATIVE) # Store in instance folder
    MAX_CONTENT_LENGTH = 16 * 1024 * 1024  # 16 MB upload limit
    ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'svg', 'ico'} # For favicons too
