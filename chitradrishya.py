import streamlit as st
import sqlite3
import io
from PIL import Image, ImageEnhance
import uuid
import mimetypes
from datetime import datetime
import base64
import os
from dotenv import load_dotenv
import logging
import names
import plotly.express as px
try:
    from streamlit_javascript import st_javascript
except ImportError:
    st_javascript = lambda x: ""  # Fallback if package is missing

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv()
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "admin123")
DB_PATH = "gallery.db"
MAX_FILE_SIZE_MB = 5

# -------------------------------
# Helper Functions
# -------------------------------
def image_to_base64(image_data):
    """Convert image data (bytes) to base64 string."""
    return base64.b64encode(image_data).decode('utf-8') if isinstance(image_data, bytes) else image_data.encode('utf-8')

def thumbnail_to_bytes(image):
    """Convert PIL Image to bytes."""
    output = io.BytesIO()
    image.save(output, format="PNG")
    return output.getvalue()

def validate_file(file):
    """Validate uploaded file size, type, and integrity."""
    file_size_bytes = len(file.getvalue())
    if file_size_bytes > MAX_FILE_SIZE_MB * 1024 * 1024:
        st.error(f"File '{file.name}' is too large (max {MAX_FILE_SIZE_MB}MB).")
        logger.warning(f"File {file.name} exceeds size limit")
        return False
    file_type = file.type if hasattr(file, 'type') and file.type else os.path.splitext(file.name)[1].lower()
    if file_type not in ['image/jpeg', 'image/png', '.jpg', '.jpeg', '.png']:
        st.error(f"File '{file.name}' must be JPG or PNG.")
        logger.warning(f"Unsupported file type for {file.name}: {file_type}")
        return False
    try:
        file.seek(0)
        Image.open(file).verify()
        file.seek(0)
    except Exception as e:
        st.error(f"File '{file.name}' is invalid or corrupted.")
        logger.error(f"Corrupted file {file.name}: {str(e)}")
        return False
    return True

# -------------------------------
# Helper Classes
# -------------------------------
class DatabaseManager:
    @staticmethod
    def connect():
        try:
            return sqlite3.connect(DB_PATH)
        except sqlite3.OperationalError as e:
            logger.error(f"Failed to connect to database: {str(e)}")
            st.error("Cannot connect to the database.")
            raise

    @staticmethod
    def init_db():
        conn = DatabaseManager.connect()
        c = conn.cursor()
        c.execute("""
            CREATE TABLE IF NOT EXISTS folders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                folder TEXT UNIQUE NOT NULL,
                name TEXT NOT NULL,
                age INTEGER NOT NULL,
                profession TEXT NOT NULL,
                category TEXT NOT NULL
            )
        """)
        c.execute("""
            CREATE TABLE IF NOT EXISTS images (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                folder TEXT NOT NULL,
                image_data BLOB NOT NULL,
                download_allowed BOOLEAN NOT NULL DEFAULT 1,
                FOREIGN KEY(folder) REFERENCES folders(folder)
            )
        """)
        c.execute("""
            CREATE TABLE IF NOT EXISTS surveys (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                folder TEXT NOT NULL,
                rating INTEGER NOT NULL,
                feedback TEXT,
                timestamp TEXT NOT NULL,
                FOREIGN KEY(folder) REFERENCES folders(folder)
            )
        """)
        c.execute("""
            CREATE TABLE IF NOT EXISTS image_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                image_id INTEGER NOT NULL,
                folder TEXT NOT NULL,
                image_data BLOB NOT NULL,
                timestamp TEXT NOT NULL,
                FOREIGN KEY(image_id) REFERENCES images(id)
            )
        """)
        default_folders = [
            {"name": "Xiaojing", "age": 26, "profession": "Graphic Designer", "category": "Artists", "folder": "xiaojing"},
            {"name": "Yuena", "age": 29, "profession": "Painter", "category": "Artists", "folder": "yuena"},
            {"name": "Yijie", "age": 30, "profession": "Literature Teacher", "category": "Teachers", "folder": "yijie"},
            {"name": "Yajie", "age": 27, "profession": "Musician", "category": "Artists", "folder": "yajie"},
            {"name": "Yu", "age": 47, "profession": "Data Scientist", "category": "Engineers", "folder": "yu"},
            {"name": "Chunyang", "age": 25, "profession": "Software Developer", "category": "Engineers", "folder": "chunyang"},
            {"name": "Haoran", "age": 34, "profession": "History Teacher", "category": "Teachers", "folder": "haoran"},
        ]
        for folder_data in default_folders:
            c.execute("SELECT COUNT(*) FROM folders WHERE folder = ?", (folder_data["folder"],))
            if c.fetchone()[0] == 0:
                c.execute("""
                    INSERT INTO folders (folder, name, age, profession, category)
                    VALUES (?, ?, ?, ?, ?)
                """, (folder_data["folder"], folder_data["name"], folder_data["age"],
                      folder_data["profession"], folder_data["category"]))
        conn.commit()
        conn.close()
        logger.info("Database initialized")

    @staticmethod
    def load_folders(search_query=""):
        conn = DatabaseManager.connect()
        c = conn.cursor()
        query = "SELECT folder, name, age, profession, category FROM folders WHERE name LIKE ? OR folder LIKE ? OR profession LIKE ? OR category LIKE ?"
        c.execute(query, (f"%{search_query}%", f"%{search_query}%", f"%{search_query}%", f"%{search_query}%"))
        folders = [{"folder": r[0], "name": r[1], "age": r[2], "profession": r[3], "category": r[4]} for r in c.fetchall()]
        conn.close()
        return folders

    @staticmethod
    def add_folder(folder, name, age, profession, category):
        conn = DatabaseManager.connect()
        try:
            c = conn.cursor()
            c.execute("""
                INSERT INTO folders (folder, name, age, profession, category)
                VALUES (?, ?, ?, ?, ?)
            """, (folder, name, age, profession, category))
            conn.commit()
            return True
        except sqlite3.IntegrityError:
            st.error(f"Folder '{folder}' already exists.")
            return False
        finally:
            conn.close()

    @staticmethod
    def load_images_to_db(uploaded_files, folder, download_allowed=True):
        conn = DatabaseManager.connect()
        c = conn.cursor()
        for uploaded_file in uploaded_files:
            image_data = uploaded_file.read()
            extension = os.path.splitext(uploaded_file.name)[1].lower()
            random_filename = f"{uuid.uuid4()}{extension}"
            c.execute("SELECT COUNT(*) FROM images WHERE folder = ? AND name = ?", (folder, random_filename))
            if c.fetchone()[0] == 0:
                c.execute("INSERT INTO images (name, folder, image_data, download_allowed) VALUES (?, ?, ?, ?)",
                          (random_filename, folder, image_data, download_allowed))
        conn.commit()
        conn.close()

    @staticmethod
    def update_download_permission(folder, image_name, download_allowed):
        conn = DatabaseManager.connect()
        c = conn.cursor()
        c.execute("UPDATE images SET download_allowed = ? WHERE folder = ? AND name = ?",
                  (download_allowed, folder, image_name))
        conn.commit()
        conn.close()

    @staticmethod
    def delete_image(folder, name):
        conn = DatabaseManager.connect()
        c = conn.cursor()
        c.execute("DELETE FROM images WHERE folder = ? AND name = ?", (folder, name))
        conn.commit()
        conn.close()

    @staticmethod
    def load_survey_data():
        conn = DatabaseManager.connect()
        c = conn.cursor()
        c.execute("SELECT folder, rating, feedback, timestamp FROM surveys")
        survey_data = {}
        for row in c.fetchall():
            folder, rating, feedback, timestamp = row
            if folder not in survey_data:
                survey_data[folder] = []
            survey_data[folder].append({"rating": rating, "feedback": feedback, "timestamp": timestamp})
        conn.close()
        return survey_data

    @staticmethod
    def save_survey_data(folder, rating, feedback, timestamp):
        conn = DatabaseManager.connect()
        c = conn.cursor()
        c.execute("INSERT INTO surveys (folder, rating, feedback, timestamp) VALUES (?, ?, ?, ?)",
                  (folder, rating, feedback, timestamp))
        conn.commit()
        conn.close()

    @staticmethod
    def delete_survey_entry(folder, timestamp):
        conn = DatabaseManager.connect()
        c = conn.cursor()
        c.execute("DELETE FROM surveys WHERE folder = ? AND timestamp = ?", (folder, timestamp))
        conn.commit()
        conn.close()

    @staticmethod
    def get_images(folder):
        conn = DatabaseManager.connect()
        c = conn.cursor()
        c.execute("SELECT name, image_data, download_allowed FROM images WHERE folder = ?", (folder,))
        images = []
        for r in c.fetchall():
            name, data, download = r
            try:
                img = Image.open(io.BytesIO(data))
                base64_image = image_to_base64(data)
                images.append({"name": name, "image": img, "data": data, "download": download, "base64": base64_image})
            except Exception as e:
                st.error(f"Error loading image {name}: {str(e)}")
        conn.close()
        return images

# -------------------------------
# Initialize DB & Session State
# -------------------------------
init_db()
if "zoom_folder" not in st.session_state:
    st.session_state.zoom_folder = None
if "zoom_index" not in st.session_state:
    st.session_state.zoom_index = 0
if "is_author" not in st.session_state:
    st.session_state.is_author = False

# -------------------------------
# Sidebar: Author Controls
# -------------------------------
with st.sidebar:
    st.title("Author Login")
    with st.form(key="login_form"):
        pwd = st.text_input("Password", type="password")
        if st.form_submit_button("Login"):
            if pwd == "admin123":
                st.session_state.is_author = True
                st.success("Logged in as author!")
            else:
                st.error("Wrong password")
    if st.session_state.is_author and st.button("Logout"):
        st.session_state.is_author = False
        st.success("Logged out")
        st.rerun()

    if st.session_state.is_author:
        st.subheader("Manage Folders & Images")

        # Add Folder
        with st.form(key="add_folder_form"):
            new_folder = st.text_input("Folder Name (e.g., 'newfolder')")
            new_name = st.text_input("Person Name")
            new_age = st.number_input("Age", min_value=1, max_value=150, step=1)
            new_profession = st.text_input("Profession")
            new_category = st.selectbox("Category", ["Artists", "Engineers", "Teachers"])
            if st.form_submit_button("Add Folder"):
                if new_folder and new_name and new_profession and new_category:
                    if add_folder(new_folder.lower(), new_name, new_age, new_profession, new_category):
                        st.success(f"Folder '{new_folder}' added successfully!")
                        st.rerun()
                    else:
                        st.error(f"Folder '{new_folder}' already exists or invalid input.")
                else:
                    st.error("Please fill in all fields.")

        # Upload Images
        data = load_folders()
        folder_choice = st.selectbox("Select Folder", [item["folder"] for item in data], key="upload_folder")
        download_allowed = st.checkbox("Allow Downloads for New Images", value=True)
        uploaded_files = st.file_uploader(
            "Upload Images", accept_multiple_files=True, type=['jpg','jpeg','png'], key="upload_files"
        )

        if st.button("Upload to DB") and uploaded_files:
            load_images_to_db(uploaded_files, folder_choice, download_allowed)
            st.success(f"{len(uploaded_files)} image(s) uploaded to '{folder_choice}'!")
            st.rerun()

        # Download Permissions
        folder_choice_perm = st.selectbox("Select Folder for Download Settings", [item["folder"] for item in data], key=f"download_folder_{uuid.uuid4()}")
        images = get_images(folder_choice_perm)
        if images:
            with st.form(key=f"download_permissions_form_{folder_choice_perm}"):
                st.write("Toggle Download Permissions:")
                download_states = {}
                for img_dict in images:
                    toggle_key = f"download_toggle_{folder_choice_perm}_{img_dict['name']}"
                    download_states[img_dict['name']] = st.checkbox(
                        f"Allow download for {img_dict['name'][:8]}...{img_dict['name'][-4:]}",
                        value=img_dict["download"],
                        key=toggle_key
                    )
                if st.form_submit_button("Apply Download Permissions"):
                    for img_dict in images:
                        if download_states[img_dict['name']] != img_dict["download"]:
                            update_download_permission(folder_choice_perm, img_dict["name"], download_states[img_dict['name']])
                    st.success("Download permissions updated!")
                    st.rerun()

# -------------------------------
# CSS Styling
# -------------------------------
st.markdown("""
<style>
.folder-card {background: #f9f9f9; border-radius: 8px; padding: 15px; margin-bottom: 20px; box-shadow: 0 4px 8px rgba(0,0,0,0.1);}
.folder-header {font-size:1.5em; color:#333; margin-bottom:10px;}
.image-grid {display:flex; flex-wrap:wrap; gap:10px;}
img {border-radius:4px;}
</style>
""", unsafe_allow_html=True)

# -------------------------------
# Main App UI
# -------------------------------
st.title("📸 Interactive Photo Gallery & Survey")

data = load_folders()
survey_data = load_survey_data()
categories = sorted(set(item["category"] for item in data))
tabs = st.tabs(categories)

# Grid view
if st.session_state.zoom_folder is None:
    for cat, tab in zip(categories, tabs):
        with tab:
            cat_folders = [f for f in data if f["category"] == cat]
            for f in cat_folders:
                st.markdown(
                    f'<div class="folder-card"><div class="folder-header">'
                    f'{f["name"]} ({f["age"]}, {f["profession"]})</div>',
                    unsafe_allow_html=True
                )

                # Load images
                images = get_images(f["folder"])
                if images:
                    cols = st.columns(4)
                    for idx, img_dict in enumerate(images):
                        with cols[idx % 4]:
                            if st.button("🔍 View", key=f"view_{f['folder']}_{idx}"):
                                st.session_state.zoom_folder = f["folder"]
                                st.session_state.zoom_index = idx
                                st.rerun()
                            st.image(img_dict["image"], use_container_width=True)
                else:
                    st.warning(f"No images found for {f['folder']}")

                # Survey form + previous feedback
                with st.expander(f"📝 Survey for {f['name']}"):
                    with st.form(key=f"survey_form_{f['folder']}"):
                        rating = st.slider("Rating (1-5)", 1, 5, 3, key=f"rating_{f['folder']}")
                        feedback = st.text_area("Feedback", key=f"feedback_{f['folder']}")
                        if st.form_submit_button("Submit"):
                            timestamp = datetime.now().isoformat()
                            save_survey_data(f["folder"], rating, feedback, timestamp)
                            st.success("✅ Response recorded")
                            st.rerun()

                    # Show past survey results
                    if f["folder"] in survey_data and survey_data[f["folder"]]:
                        st.write("### 📊 Previous Feedback:")

                        # Calculate and show average rating
                        ratings = [entry['rating'] for entry in survey_data[f["folder"]]]
                        avg_rating = sum(ratings) / len(ratings)
                        st.markdown(f"**Average Rating:** ⭐ {avg_rating:.1f} ({len(ratings)} reviews)")

                        # List each past response with optional delete button
                        for entry in survey_data[f["folder"]]:
                            cols = st.columns([6, 1])  # feedback + delete button
                            with cols[0]:
                                rating_display = "⭐" * entry["rating"]
                                st.markdown(
                                    f"- {rating_display} — {entry['feedback']}  \n"
                                    f"<sub>🕒 {entry['timestamp']}</sub>",
                                    unsafe_allow_html=True
                                )
                            if st.session_state.is_author:
                                with cols[1]:
                                    if st.button("🗑️", key=f"delete_survey_{f['folder']}_{entry['timestamp']}"):
                                        delete_survey_entry(f["folder"], entry["timestamp"])
                                        st.success("Deleted comment.")
                                        st.rerun()
                    else:
                        st.info("No feedback yet — be the first to leave a comment!")

# Zoom view
else:
    folder = st.session_state.zoom_folder
    images = get_images(folder)
    idx = st.session_state.zoom_index
    if idx >= len(images):
        idx = 0
        st.session_state.zoom_index = 0
    img_dict = images[idx]

    st.subheader(f"🔍 Viewing {folder} ({idx+1}/{len(images)})")
    st.image(img_dict["image"], use_container_width=True)

    col1, col2, col3 = st.columns([1,8,1])
    with col1:
        if idx > 0 and st.button("◄ Previous", key=f"prev_{folder}_{idx}"):
            st.session_state.zoom_index -=1
            st.rerun()
    with col3:
        if idx < len(images)-1 and st.button("Next ►", key=f"next_{folder}_{idx}"):
            st.session_state.zoom_index +=1
            st.rerun()

    if img_dict["download"]:
        mime, _ = mimetypes.guess_type(img_dict["name"])
        st.download_button("⬇️ Download", data=img_dict["data"], file_name=f"{uuid.uuid4()}{os.path.splitext(img_dict['name'])[1]}", mime=mime, key=f"download_{folder}_{img_dict['name']}")

    if st.session_state.is_author:
        if st.button("🗑️ Delete Image", key=f"delete_{folder}_{img_dict['name']}"):
            delete_image(folder, img_dict["name"])
            st.success("Deleted.")
            st.session_state.zoom_index = max(0, idx-1)
            if len(get_images(folder))==0:
                st.session_state.zoom_folder=None
                st.session_state.zoom_index=0
            st.rerun()

    if st.button("⬅️ Back to Grid", key=f"back_{folder}_{idx}"):
        st.session_state.zoom_folder=None
        st.session_state.zoom_index=0
        st.rerun()
