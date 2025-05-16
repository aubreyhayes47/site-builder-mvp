# ISG_Project/run.py
from internal_site_generator import create_app # Import create_app from your package

app = create_app()

if __name__ == '__main__':
    app.run(debug=True)
