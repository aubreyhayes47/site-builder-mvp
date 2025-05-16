import sqlite3
import os

# Construct the path to the database file
# Assumes this script is in your project root, and 'instance/app.db' is the path
project_root = os.path.dirname(os.path.abspath(__file__))
db_path = os.path.join(project_root, 'instance', 'app.db')

print(f"Attempting to connect to database at: {db_path}")

if not os.path.exists(db_path):
    print(f"Error: Database file not found at {db_path}")
    print("Please ensure the path is correct and the database file exists.")
else:
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        # --- Customize your query here ---
        # Option 1: List all template names and IDs to help you identify your minimal template
        print("\n--- Available Page Templates (id, name) ---")
        cursor.execute("SELECT id, name FROM page_template;")
        for row in cursor.fetchall():
            print(row)

        # Option 2: Query specific template by name (replace with your actual minimal template name)
        template_name_to_check = "Minimal Template" # <--- CHANGE THIS if your minimal template has a different name
        print(f"\n--- HTML Content for template named '{template_name_to_check}' ---")
        cursor.execute("SELECT html_content FROM page_template WHERE name = ?;", (template_name_to_check,))
        row = cursor.fetchone()
        if row:
            print(row[0])
        else:
            print(f"No template found with the name '{template_name_to_check}'. Please check the name or use its ID.")

        # Option 3: Query specific template by ID (replace with your actual minimal template ID)
        # template_id_to_check = 1 # <--- CHANGE THIS to the ID of your minimal template
        # print(f"\n--- HTML Content for template with ID {template_id_to_check} ---")
        # cursor.execute("SELECT html_content FROM page_template WHERE id = ?;", (template_id_to_check,))
        # row = cursor.fetchone()
        # if row:
        #     print(row[0])
        # else:
        #     print(f"No template found with ID {template_id_to_check}.")
        # --- End of query customization ---

        conn.close()

    except sqlite3.Error as e:
        print(f"SQLite error: {e}")
    except Exception as e:
        print(f"An error occurred: {e}")
