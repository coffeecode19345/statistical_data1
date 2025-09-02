import streamlit as st
import sqlite3
import io
from PIL import Image, ImageEnhance
import os
from datetime import datetime
import uuid
import re
import base64
from dotenv import load_dotenv
import logging
import json
import names
import plotly.express as px

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv()
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "admin123")  # Fallback for testing
DB_PATH = "gallery.db"
MAX_FILE_SIZE_MB = 5  # Max file size for uploads in MB
FORCE_DB_RESET = os.getenv("FORCE_DB_RESET", "False").lower() == "true"  # Define with default value

# -------------------------------
# Helper Functions
# -------------------------------
def image_to_base64(image_data):
    """Convert image data (bytes) to base64 string."""
    if not isinstance(image_data, bytes):
        raise ValueError("image_data must be bytes")
    return base64.b64encode(image_data).decode('utf-8')

def validate_folder_name(folder):
    """Validate folder name: alphanumeric, underscores, lowercase, 3-20 characters."""
    pattern = r"^[a-z0-9_]{3,20}$"
    return bool(re.match(pattern, folder))

def generate_random_name():
    """Generate a realistic full name using the names library."""
    return names.get_full_name()

def validate_file(file):
    """Validate uploaded file size, type, and integrity."""
    file_size_bytes = len(file.getvalue())
    if file_size_bytes > MAX_FILE_SIZE_MB * 1024 * 1024:
        st.error(f"File {file.name} exceeds {MAX_FILE_SIZE_MB}MB limit.")
        logger.warning(f"File {file.name} exceeds size limit")
        return False
    file_type = file.type if hasattr(file, 'type') and file.type else os.path.splitext(file.name)[1].lower()
    if file_type not in ['image/jpeg', 'image/png', '.jpg', '.jpeg', '.png']:
        st.error(f"File {file.name} is not a supported type (JPG, JPEG, PNG).")
        logger.warning(f"Unsupported file type for {file.name}: {file_type}")
        return False
    try:
        file.seek(0)
        Image.open(file).verify()  # Verify image integrity
        file.seek(0)  # Reset file pointer
    except Exception as e:
        st.error(f"File {file.name} is corrupted or invalid.")
        logger.error(f"Corrupted file {file.name}: {str(e)}")
        return False
    return True

# -------------------------------
# Helper Classes
# -------------------------------
class DatabaseManager:
    """Manage SQLite database operations."""
    
    @staticmethod
    def connect():
        """Establish a database connection."""
        try:
            return sqlite3.connect(DB_PATH)
        except sqlite3.OperationalError as e:
            logger.error(f"Failed to connect to database at {DB_PATH}: {str(e)}")
            st.error(f"Database connection failed: {str(e)}")
            raise

    @staticmethod
    def init_db():
        """Initialize database with required tables."""
        db_dir = os.path.dirname(DB_PATH) or "."
        if not os.access(db_dir, os.W_OK):
            logger.error(f"Directory {db_dir} is not writable")
            st.error(f"Cannot write to database directory: {db_dir}")
            raise PermissionError(f"Directory {db_dir} is not writable")

        if FORCE_DB_RESET and os.path.exists(DB_PATH):
            try:
                os.remove(DB_PATH)
                logger.info(f"Deleted existing database file {DB_PATH} due to FORCE_DB_RESET")
            except Exception as e:
                logger.error(f"Failed to delete database file {DB_PATH}: {str(e)}")
                st.error(f"Failed to reset database: {str(e)}")
                raise

        conn = DatabaseManager.connect()
        try:
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
                {"name": generate_random_name(), "age": 26, "profession": "Graphic Designer", "category": "Artists", "folder": "artist1"},
                {"name": generate_random_name(), "age": 29, "profession": "Painter", "category": "Artists", "folder": "artist2"},
                {"name": generate_random_name(), "age": 30, "profession": "Literature Teacher", "category": "Teachers", "folder": "teacher1"},
                {"name": generate_random_name(), "age": 27, "profession": "Musician", "category": "Artists", "folder": "artist3"},
                {"name": generate_random_name(), "age": 47, "profession": "Data Scientist", "category": "Engineers", "folder": "engineer1"},
                {"name": generate_random_name(), "age": 25, "profession": "Software Developer", "category": "Engineers", "folder": "engineer2"},
                {"name": generate_random_name(), "age": 34, "profession": "History Teacher", "category": "Teachers", "folder": "teacher2"},
            ]
            for folder_data in default_folders:
                if validate_folder_name(folder_data["folder"]):
                    c.execute("SELECT COUNT(*) FROM folders WHERE folder = ?", (folder_data["folder"],))
                    if c.fetchone()[0] == 0:
                        c.execute("""
                            INSERT INTO folders (folder, name, age, profession, category)
                            VALUES (?, ?, ?, ?, ?)
                        """, (folder_data["folder"], folder_data["name"], folder_data["age"],
                              folder_data["profession"], folder_data["category"]))
            conn.commit()
            logger.info("Database initialized successfully")
        except sqlite3.OperationalError as e:
            logger.error(f"SQLite error during database initialization: {str(e)}")
            st.error(f"Database initialization failed: {str(e)}")
            raise
        finally:
            conn.close()

    @staticmethod
    def load_folders(search_query=""):
        """Load folders from database, optionally filtered by search query."""
        conn = DatabaseManager.connect()
        try:
            c = conn.cursor()
            query = "SELECT folder, name, age, profession, category FROM folders WHERE name LIKE ? OR folder LIKE ? OR profession LIKE ? OR category LIKE ?"
            c.execute(query, (f"%{search_query}%", f"%{search_query}%", f"%{search_query}%", f"%{search_query}%"))
            folders = [{"folder": r[0], "name": r[1], "age": r[2], "profession": r[3], "category": r[4]} for r in c.fetchall()]
            logger.info(f"Loaded {len(folders)} folders with search query: {search_query}")
            return folders
        finally:
            conn.close()

    @staticmethod
    def update_folder_name(folder, new_name):
        """Update the name of a candidate in the folders table."""
        conn = DatabaseManager.connect()
        try:
            c = conn.cursor()
            c.execute("UPDATE folders SET name = ? WHERE folder = ?", (new_name, folder))
            conn.commit()
            logger.info(f"Updated name for folder '{folder}' to '{new_name}'")
            return True
        except Exception as e:
            logger.error(f"Error updating folder name: {str(e)}")
            st.error(f"Error updating folder name: {str(e)}")
            return False
        finally:
            conn.close()

    @staticmethod
    def add_folder(folder, name, age, profession, category):
        """Add a new folder to the database with validation."""
        if not validate_folder_name(folder):
            logger.warning(f"Invalid folder name: {folder}")
            st.error("Folder name must be 3-20 characters, lowercase alphanumeric or underscores.")
            return False
        conn = DatabaseManager.connect()
        try:
            c = conn.cursor()
            c.execute("""
                INSERT INTO folders (folder, name, age, profession, category)
                VALUES (?, ?, ?, ?, ?)
            """, (folder, name, age, profession, category))
            conn.commit()
            logger.info(f"Added folder '{folder}'")
            return True
        except sqlite3.IntegrityError:
            logger.warning(f"Folder '{folder}' already exists")
            st.error(f"Folder '{folder}' already exists.")
            return False
        except Exception as e:
            logger.error(f"Error adding folder: {str(e)}")
            st.error(f"Error adding folder: {str(e)}")
            return False
        finally:
            conn.close()

    @staticmethod
    def load_images_to_db(edited_data_list, folder, download_allowed=True):
        """Load edited images into the database."""
        conn = DatabaseManager.connect()
        try:
            c = conn.cursor()
            for edited_data in edited_data_list:
                extension = ".png"
                random_filename = f"{uuid.uuid4()}{extension}"
                c.execute("SELECT COUNT(*) FROM images WHERE folder = ? AND name = ?", (folder, random_filename))
                if c.fetchone()[0] == 0:
                    c.execute("INSERT INTO images (name, folder, image_data, download_allowed) VALUES (?, ?, ?, ?)",
                              (random_filename, folder, edited_data, download_allowed))
            conn.commit()
            logger.info(f"Uploaded {len(edited_data_list)} images to folder '{folder}'")
        except sqlite3.OperationalError as e:
            logger.error(f"SQLite error during image upload: {str(e)}")
            st.error(f"Failed to upload images: {str(e)}")
        finally:
            conn.close()

    @staticmethod
    def swap_image(folder, old_image_name, new_image_file):
        """Replace an existing image with a new uploaded image."""
        conn = DatabaseManager.connect()
        try:
            c = conn.cursor()
            new_image_data = new_image_file.read()
            c.execute("UPDATE images SET image_data = ? WHERE folder = ? AND name = ?",
                      (new_image_data, folder, old_image_name))
            conn.commit()
            logger.info(f"Swapped image '{old_image_name}' in folder '{folder}'")
            return True
        except Exception as e:
            logger.error(f"Error swapping image: {str(e)}")
            st.error(f"Error swapping image: {str(e)}")
            return False
        finally:
            conn.close()

    @staticmethod
    def save_image_history(image_id, folder, image_data):
        """Save image data to history for undo functionality."""
        conn = DatabaseManager.connect()
        try:
            c = conn.cursor()
            timestamp = datetime.now().isoformat()
            c.execute("INSERT INTO image_history (image_id, folder, image_data, timestamp) VALUES (?, ?, ?, ?)",
                      (image_id, folder, image_data, timestamp))
            conn.commit()
            logger.info(f"Saved image history for image_id {image_id} in folder '{folder}'")
        except Exception as e:
            logger.error(f"Error saving image history: {str(e)}")
        finally:
            conn.close()

    @staticmethod
    def get_image_id(folder, image_name):
        """Get the image ID from the database."""
        conn = DatabaseManager.connect()
        try:
            c = conn.cursor()
            c.execute("SELECT id FROM images WHERE folder = ? AND name = ?", (folder, image_name))
            result = c.fetchone()
            return result[0] if result else None
        finally:
            conn.close()

    @staticmethod
    def undo_image_edit(folder, image_name):
        """Restore the most recent image data from history."""
        conn = DatabaseManager.connect()
        try:
            c = conn.cursor()
            image_id = DatabaseManager.get_image_id(folder, image_name)
            if not image_id:
                raise ValueError("Image ID not found")
            c.execute("SELECT image_data, timestamp FROM image_history WHERE image_id = ? ORDER BY timestamp DESC LIMIT 1",
                      (image_id,))
            result = c.fetchone()
            if result:
                image_data, timestamp = result
                c.execute("UPDATE images SET image_data = ? WHERE folder = ? AND name = ?",
                          (image_data, folder, image_name))
                c.execute("DELETE FROM image_history WHERE image_id = ? AND timestamp = ?",
                          (image_id, timestamp))
                conn.commit()
                logger.info(f"Restored image '{image_name}' in folder '{folder}' from history")
                return True
            logger.warning(f"No history found for image '{image_name}' in folder '{folder}'")
            return False
        except Exception as e:
            logger.error(f"Error undoing image edit: {str(e)}")
            st.error(f"Error undoing image edit: {str(e)}")
            return False
        finally:
            conn.close()

    @staticmethod
    def update_download_permission(folder, image_name, download_allowed):
        """Update download permission for an image."""
        conn = DatabaseManager.connect()
        try:
            c = conn.cursor()
            c.execute("UPDATE images SET download_allowed = ? WHERE folder = ? AND name = ?",
                      (download_allowed, folder, image_name))
            conn.commit()
            logger.info(f"Updated download permission for '{image_name}' in folder '{folder}' to {download_allowed}")
        finally:
            conn.close()

    @staticmethod
    def delete_image(folder, name):
        """Delete an image from the database."""
        conn = DatabaseManager.connect()
        try:
            c = conn.cursor()
            c.execute("DELETE FROM images WHERE folder = ? AND name = ?", (folder, name))
            conn.commit()
            logger.info(f"Deleted image '{name}' from folder '{folder}'")
        finally:
            conn.close()

    @staticmethod
    def load_survey_data():
        """Load survey data from database."""
        conn = DatabaseManager.connect()
        try:
            c = conn.cursor()
            c.execute("SELECT folder, rating, feedback, timestamp FROM surveys")
            survey_data = {}
            for row in c.fetchall():
                folder, rating, feedback, timestamp = row
                if folder not in survey_data:
                    survey_data[folder] = []
                survey_data[folder].append({"rating": rating, "feedback": feedback, "timestamp": timestamp})
            logger.info(f"Loaded survey data for {len(survey_data)} folders")
            return survey_data
        finally:
            conn.close()

    @staticmethod
    def save_survey_data(folder, rating, feedback, timestamp):
        """Save survey data to database."""
        conn = DatabaseManager.connect()
        try:
            c = conn.cursor()
            c.execute("INSERT INTO surveys (folder, rating, feedback, timestamp) VALUES (?, ?, ?, ?)",
                      (folder, rating, feedback, timestamp))
            conn.commit()
            logger.info(f"Saved survey data for folder '{folder}'")
        finally:
            conn.close()

    @staticmethod
    def delete_survey_entry(folder, timestamp):
        """Delete a survey entry from database."""
        conn = DatabaseManager.connect()
        try:
            c = conn.cursor()
            c.execute("DELETE FROM surveys WHERE folder = ? AND timestamp = ?", (folder, timestamp))
            conn.commit()
            logger.info(f"Deleted survey entry for folder '{folder}' at timestamp {timestamp}")
        finally:
            conn.close()

    @staticmethod
    def get_images(folder):
        """Get images from database for a folder."""
        conn = DatabaseManager.connect()
        try:
            c = conn.cursor()
            c.execute("SELECT name, image_data, download_allowed FROM images WHERE folder = ?", (folder,))
            images = []
            for r in c.fetchall():
                name, data, download = r
                try:
                    img = Image.open(io.BytesIO(data))
                    thumbnail = ImageProcessor.generate_thumbnail(img, size=(80, 80))  # Smaller thumbnails
                    base64_image = image_to_base64(data)
                    images.append({
                        "name": name,
                        "image": img,
                        "thumbnail": thumbnail,
                        "data": data,
                        "download": download,
                        "base64": base64_image
                    })
                except Exception as e:
                    logger.error(f"Error loading image {name}: {str(e)}")
                    st.error(f"Error loading image {name}: {str(e)}")
            logger.info(f"Loaded {len(images)} images for folder '{folder}'")
            return images
        finally:
            conn.close()

class ImageProcessor:
    """Handle image processing operations."""
    
    @staticmethod
    def generate_thumbnail(image, size=(80, 80)):
        """Generate a thumbnail for an image."""
        img = image.copy()
        img.thumbnail(size)
        return img

    @staticmethod
    def crop_image(image_data, crop_box):
        """Crop an image based on provided coordinates."""
        try:
            img = Image.open(io.BytesIO(image_data)).convert("RGB")
            cropped_img = img.crop(crop_box)
            output = io.BytesIO()
            cropped_img.save(output, format="PNG")
            logger.info(f"Cropped image with box {crop_box}")
            return output.getvalue()
        except Exception as e:
            logger.error(f"Error cropping image: {str(e)}")
            st.error(f"Error cropping image: {str(e)}")
            return None

    @staticmethod
    def rotate_image(image_data, degrees):
        """Rotate an image by the specified degrees."""
        try:
            img = Image.open(io.BytesIO(image_data)).convert("RGB")
            rotated_img = img.rotate(degrees, expand=True)
            output = io.BytesIO()
            rotated_img.save(output, format="PNG")
            logger.info(f"Rotated image by {degrees} degrees")
            return output.getvalue()
        except Exception as e:
            logger.error(f"Error rotating image: {str(e)}")
            st.error(f"Error rotating image: {str(e)}")
            return None

    @staticmethod
    def adjust_brightness(image_data, factor):
        """Adjust image brightness."""
        try:
            img = Image.open(io.BytesIO(image_data)).convert("RGB")
            enhancer = ImageEnhance.Brightness(img)
            adjusted_img = enhancer.enhance(factor)
            output = io.BytesIO()
            adjusted_img.save(output, format="PNG")
            logger.info(f"Adjusted brightness with factor {factor}")
            return output.getvalue()
        except Exception as e:
            logger.error(f"Error adjusting brightness: {str(e)}")
            st.error(f"Error adjusting brightness: {str(e)}")
            return None

    @staticmethod
    def adjust_contrast(image_data, factor):
        """Adjust image contrast."""
        try:
            img = Image.open(io.BytesIO(image_data)).convert("RGB")
            enhancer = ImageEnhance.Contrast(img)
            adjusted_img = enhancer.enhance(factor)
            output = io.BytesIO()
            adjusted_img.save(output, format="PNG")
            logger.info(f"Adjusted contrast with factor {factor}")
            return output.getvalue()
        except Exception as e:
            logger.error(f"Error adjusting contrast: {str(e)}")
            st.error(f"Error adjusting contrast: {str(e)}")
            return None

    @staticmethod
    def adjust_sharpness(image_data, factor):
        """Adjust image sharpness."""
        try:
            img = Image.open(io.BytesIO(image_data)).convert("RGB")
            enhancer = ImageEnhance.Sharpness(img)
            adjusted_img = enhancer.enhance(factor)
            output = io.BytesIO()
            adjusted_img.save(output, format="PNG")
            logger.info(f"Adjusted sharpness with factor {factor}")
            return output.getvalue()
        except Exception as e:
            logger.error(f"Error adjusting sharpness: {str(e)}")
            st.error(f"Error adjusting sharpness: {str(e)}")
            return None

    @staticmethod
    def convert_to_grayscale(image_data):
        """Convert image to grayscale."""
        try:
            img = Image.open(io.BytesIO(image_data)).convert("L")
            output = io.BytesIO()
            img.save(output, format="PNG")
            logger.info("Converted image to grayscale")
            return output.getvalue()
        except Exception as e:
            logger.error(f"Error converting to grayscale: {str(e)}")
            st.error(f"Error converting to grayscale: {str(e)}")
            return None

# -------------------------------
# Initialize DB & Session State
# -------------------------------
try:
    DatabaseManager.init_db()
except sqlite3.OperationalError as e:
    st.error(f"Failed to initialize database: {str(e)}")
    logger.error(f"Database initialization failed: {str(e)}")
    st.stop()

if "zoom_folder" not in st.session_state:
    st.session_state.zoom_folder = None
if "zoom_index" not in st.session_state:
    st.session_state.zoom_index = 0
if "is_author" not in st.session_state:
    st.session_state.is_author = False
if "crop_coords" not in st.session_state:
    st.session_state.crop_coords = None
if "upload_previews" not in st.session_state:
    st.session_state.upload_previews = []
if "dark_mode" not in st.session_state:
    st.session_state.dark_mode = False
if "upload_step" not in st.session_state:
    st.session_state.upload_step = 0
if "search_query" not in st.session_state:
    st.session_state.search_query = ""
if "form_upload_folder" not in st.session_state:
    st.session_state.form_upload_folder = None
if "form_download_allowed" not in st.session_state:
    st.session_state.form_download_allowed = None

# -------------------------------
# CSS and JavaScript
# -------------------------------
st.markdown("""
<style>
body {
    font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
    background: var(--bg-color, #f5f5f5);
    color: var(--text-color, #1a1a1a);
}
.header {
    background: var(--header-bg, #ffffff);
    padding: 1rem;
    box-shadow: 0 2px 4px rgba(0,0,0,0.1);
    display: flex;
    justify-content: space-between;
    align-items: center;
    position: sticky;
    top: 0;
    z-index: 100;
}
.header h1 {
    margin: 0;
    font-size: 1.8rem;
    color: var(--text-color, #1a1a1a);
}
.folder-card {
    background: var(--card-bg, #ffffff);
    border-radius: 12px;
    padding: 1.5rem;
    margin-bottom: 1.5rem;
    box-shadow: 0 4px 12px rgba(0,0,0,0.08);
    transition: transform 0.2s;
}
.folder-card:hover {
    transform: translateY(-2px);
}
.folder-header {
    font-size: 1.4rem;
    font-weight: 600;
    color: var(--text-color, #1a1a1a);
    margin-bottom: 1rem;
}
.image-grid {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(120px, 1fr));
    gap: 1rem;
}
img {
    border-radius: 8px;
    object-fit: cover;
    width: 100%;
    height: 100px;
}
.canvas-container {
    position: relative;
    display: inline-block;
    margin: 1rem 0;
}
#cropCanvas {
    border: 2px solid #007bff;
    border-radius: 8px;
}
.selection-box {
    position: absolute;
    border: 2px dashed #007bff;
    background: rgba(0,123,255,0.2);
    pointer-events: none;
}
.stButton>button {
    border-radius: 8px;
    padding: 0.5rem 1rem;
    font-weight: 500;
    transition: background-color 0.2s;
}
.stButton>button:hover {
    background-color: #e6f0ff;
}
.preview-container {
    border: 1px solid var(--border-color, #e0e0e0);
    padding: 1rem;
    margin-bottom: 1rem;
    border-radius: 12px;
    background: var(--card-bg, #ffffff);
}
.before-after-container {
    position: relative;
    width: 300px;
    height: 200px;
    margin: 1rem 0;
}
.before-after-image {
    width: 100%;
    height: 100%;
    object-fit: cover;
    border-radius: 8px;
}
.slider {
    position: absolute;
    width: 4px;
    height: 100%;
    background: #007bff;
    cursor: ew-resize;
}
:root {
    --bg-color: #f5f5f5;
    --card-bg: #ffffff;
    --text-color: #1a1a1a;
    --border-color: #e0e0e0;
    --header-bg: #ffffff;
}
.dark-mode {
    --bg-color: #1a1a1a;
    --card-bg: #2d2d2d;
    --text-color: #e0e0e0;
    --border-color: #555555;
    --header-bg: #2d2d2d;
}
</style>
""", unsafe_allow_html=True)

# Apply dark mode if enabled
if st.session_state.dark_mode:
    st.markdown("""
    <style>
    body {
        --bg-color: #1a1a1a;
        --card-bg: #2d2d2d;
        --text-color: #e0e0e0;
        --border-color: #555555;
        --header-bg: #2d2d2d;
    }
    </style>
    """, unsafe_allow_html=True)

# -------------------------------
# Header Navigation
# -------------------------------
col1, col2, col3 = st.columns([2, 1, 1])
with col1:
    st.title("🖼️ Photo Gallery")
with col2:
    search_query = st.text_input("Search folders...", value=st.session_state.search_query, key="search_input")
with col3:
    if st.button("🌙 Toggle Dark Mode"):
        st.session_state.dark_mode = not st.session_state.dark_mode
        st.rerun()

# -------------------------------
# Sidebar: Author Controls
# -------------------------------
with st.sidebar:
    st.subheader("🛠️ Admin Tools", help="Manage gallery content (requires login)")
    if not st.session_state.is_author:
        with st.form(key="login_form"):
            pwd = st.text_input("Admin Password", type="password", help="Enter the admin password to access management tools")
            if st.form_submit_button("🔐 Login"):
                if pwd == ADMIN_PASSWORD:
                    st.session_state.is_author = True
                    st.balloons()
                    st.success("Logged in as admin!")
                    logger.info("Admin logged in")
                    st.rerun()
                else:
                    st.error("Incorrect password")
                    logger.warning("Failed login attempt")
    else:
        if st.button("🔓 Logout", help="Log out of admin mode"):
            st.session_state.is_author = False
            st.success("Logged out")
            logger.info("Admin logged out")
            st.rerun()

        with st.expander("📁 Add New Folder"):
            with st.form(key="add_folder_form"):
                st.markdown("**Create a new folder**")
                new_folder = st.text_input("Folder Name", help="Use lowercase alphanumeric or underscores (3-20 characters)")
                new_name = st.text_input("Person Name", help="Enter the full name")
                new_age = st.number_input("Age", min_value=1, max_value=150, step=1, help="Enter age")
                new_profession = st.text_input("Profession", help="Enter profession")
                new_category = st.selectbox("Category", ["Artists", "Engineers", "Teachers"], help="Select category")
                if st.form_submit_button("➕ Add Folder"):
                    if new_folder and new_name and new_profession and new_category:
                        if DatabaseManager.add_folder(new_folder.lower(), new_name, new_age, new_profession, new_category):
                            st.success(f"Folder '{new_folder}' created!")
                            st.balloons()
                            st.rerun()
                        else:
                            st.error("Failed to create folder. Check input or try a different name.")
                    else:
                        st.error("Please fill in all fields.")

        with st.expander("✏️ Edit Folder Name"):
            data = DatabaseManager.load_folders()
            folder_choice_name = st.selectbox("Select Folder", [item["folder"] for item in data], key="edit_name_folder")
            current_name = next(item["name"] for item in data if item["folder"] == folder_choice_name)
            with st.form(key="edit_name_form"):
                new_name = st.text_input("New Name", value=current_name, help="Enter the new name for the candidate")
                if st.form_submit_button("💾 Update Name"):
                    if new_name:
                        if DatabaseManager.update_folder_name(folder_choice_name, new_name):
                            st.success(f"Name updated to '{new_name}'!")
                            st.balloons()
                            st.rerun()
                        else:
                            st.error("Failed to update name.")
                    else:
                        st.error("Please enter a valid name.")

        with st.expander("🖼️ Upload Images"):
            data = DatabaseManager.load_folders()
            with st.form(key="upload_images_form"):
                folder_choice = st.selectbox("Select Folder", [item["folder"] for item in data], key="upload_folder")
                download_allowed = st.checkbox("Allow Downloads for New Images", value=True, help="Allow users to download these images")
                uploaded_files = st.file_uploader(
                    "Upload Images", accept_multiple_files=True, type=['jpg', 'jpeg', 'png'], key="upload_files",
                    help=f"Select JPG/PNG images (max {MAX_FILE_SIZE_MB}MB each)"
                )
                submit_button = st.form_submit_button("➡️ Proceed to Edit")

                if submit_button and uploaded_files:
                    valid_files = [f for f in uploaded_files if validate_file(f)]
                    if len(valid_files) != len(uploaded_files):
                        st.warning("Some files were invalid or corrupted and skipped.")
                    if valid_files:
                        st.session_state.upload_previews = valid_files
                        st.session_state.upload_step = 1
                        st.session_state.form_upload_folder = folder_choice
                        st.session_state.form_download_allowed = download_allowed
                        st.rerun()
                    else:
                        st.error("No valid files uploaded. Please check file types and sizes.")
                elif submit_button and not uploaded_files:
                    st.error("Please upload at least one image.")

        with st.expander("🔄 Swap Image"):
            data = DatabaseManager.load_folders()
            folder_choice_swap = st.selectbox("Select Folder", [item["folder"] for item in data], key="swap_folder")
            images = DatabaseManager.get_images(folder_choice_swap)
            if images:
                image_choice = st.selectbox("Select Image to Replace", [img["name"] for img in images], key="swap_image")
                new_image = st.file_uploader("Upload New Image", type=['jpg', 'jpeg', 'png'], key="swap_upload")
                if st.button("🔄 Swap Image", help="Replace the selected image"):
                    if new_image and validate_file(new_image):
                        if DatabaseManager.swap_image(folder_choice_swap, image_choice, new_image):
                            st.success(f"Image '{image_choice}' replaced!")
                            st.balloons()
                            st.rerun()
                        else:
                            st.error("Failed to swap image.")
                    else:
                        st.error("Please upload a valid image.")

        with st.expander("🔒 Download Permissions"):
            data = DatabaseManager.load_folders()
            folder_choice_perm = st.selectbox("Select Folder", [item["folder"] for item in data], key=f"download_folder_{uuid.uuid4()}")
            images = DatabaseManager.get_images(folder_choice_perm)
            if images:
                with st.form(key=f"download_permissions_form_{folder_choice_perm}"):
                    st.write("Toggle Download Permissions:")
                    download_states = {}
                    for img_dict in images:
                        toggle_key = f"download_toggle_{folder_choice_perm}_{img_dict['name']}"
                        download_states[img_dict['name']] = st.checkbox(
                            f"Allow download for {img_dict['name'][:8]}...{img_dict['name'][-4:]}",
                            value=img_dict["download"],
                            key=toggle_key,
                            help=f"Toggle download permission for {img_dict['name']}"
                        )
                    if st.form_submit_button("💾 Apply Permissions"):
                        for img_dict in images:
                            if download_states[img_dict['name']] != img_dict["download"]:
                                DatabaseManager.update_download_permission(folder_choice_perm, img_dict["name"], download_states[img_dict['name']])
                        st.success("Permissions updated!")
                        st.balloons()
                        st.rerun()

# -------------------------------
# Main App UI
# -------------------------------
# Update search query from input
if search_query != st.session_state.search_query:
    st.session_state.search_query = search_query
    st.rerun()

data = DatabaseManager.load_folders(st.session_state.search_query)
survey_data = DatabaseManager.load_survey_data()

# Tabs for navigation
categories = sorted(set(item["category"] for item in data))
tab_names = ["Home", "Gallery"] + categories + ["Help"]
tabs = st.tabs(tab_names)

# Home Tab
with tabs[0]:
    st.markdown("## Welcome to the Photo Gallery! 🎉")
    st.write("Explore images, provide feedback, or manage content as an admin.")
    st.markdown("""
    - **Browse**: View images by category (Artists, Engineers, Teachers).
    - **Search**: Use the top search bar to find folders by name, profession, or category.
    - **Feedback**: Rate and comment on folders.
    - **Admin Tools**: Log in (sidebar) to upload, edit, or manage images and folders.
    """)
    st.markdown("### Average Ratings")
    ratings = []
    folder_names = []
    for f in data:
        if f["folder"] in survey_data and survey_data[f["folder"]]:
            avg_rating = sum(entry["rating"] for entry in survey_data[f["folder"]]) / len(survey_data[f["folder"]])
            ratings.append(avg_rating)
            folder_names.append(f["name"])
    
    if ratings:
        fig = px.bar(
            x=folder_names,
            y=ratings,
            labels={'x': 'Folder', 'y': 'Rating (1-5)'},
            color=ratings,
            color_continuous_scale='Blues',
            range_y=[0, 5]
        )
        fig.update_layout(
            title="Average Ratings per Folder",
            xaxis_title="Folder",
            yaxis_title="Rating (1-5)",
            showlegend=False,
            template="plotly_white" if not st.session_state.dark_mode else "plotly_dark"
        )
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("No survey data available yet.")

# Gallery Tab (for upload step or zoom view)
with tabs[1]:
    if st.session_state.upload_step == 1 and st.session_state.is_author:
        st.subheader("🖼️ Upload Images - Edit & Preview")
        folder_choice = st.session_state.get("form_upload_folder", data[0]["folder"] if data else "")
        valid_files = st.session_state.upload_previews
        edited_data_list = []
        
        for i, file in enumerate(valid_files):
            st.markdown(f"<div class='preview-container'>", unsafe_allow_html=True)
            st.write(f"**Editing: {file.name}**")
            file_data = file.read()
            file.seek(0)
            
            try:
                img = Image.open(io.BytesIO(file_data))
                file_size_mb = len(file_data) / (1024 * 1024)
                st.write(f"Size: {file_size_mb:.2f} MB, Dimensions: {img.width}x{img.height}")
            except Exception as e:
                st.error(f"Failed to load image {file.name}: {str(e)}")
                logger.error(f"Failed to load image {file.name}: {str(e)}")
                st.markdown("</div>", unsafe_allow_html=True)
                continue

            # Display the image for editing
            st.image(file_data, caption="Original Image", use_column_width=True)

            # Edit Controls
            with st.form(key=f"edit_upload_form_{i}"):
                rotate_angle = st.slider("Rotate (degrees)", -180, 180, 0, key=f"upload_rotate_{i}", help="Rotate the image")
                brightness = st.slider("Brightness", 0.0, 2.0, 1.0, step=0.1, key=f"upload_brightness_{i}", help="Adjust brightness")
                contrast = st.slider("Contrast", 0.0, 2.0, 1.0, step=0.1, key=f"upload_contrast_{i}", help="Adjust contrast")
                sharpness = st.slider("Sharpness", 0.0, 2.0, 1.0, step=0.1, key=f"upload_sharpness_{i}", help="Adjust sharpness")
                grayscale = st.checkbox("Grayscale", key=f"upload_grayscale_{i}", help="Convert to grayscale")

                if st.form_submit_button("Apply Edits"):
                    edited_data = file_data
                    if rotate_angle != 0:
                        edited_data = ImageProcessor.rotate_image(edited_data, rotate_angle)
                    if brightness != 1.0:
                        edited_data = ImageProcessor.adjust_brightness(edited_data, brightness)
                    if contrast != 1.0:
                        edited_data = ImageProcessor.adjust_contrast(edited_data, contrast)
                    if sharpness != 1.0:
                        edited_data = ImageProcessor.adjust_sharpness(edited_data, sharpness)
                    if grayscale:
                        edited_data = ImageProcessor.convert_to_grayscale(edited_data)
                    if edited_data:
                        edited_data_list.append(edited_data)
                        st.session_state.upload_previews[i] = io.BytesIO(edited_data)
                        st.success("Edits applied! Preview updated.")
                        st.rerun()

            if st.button("Reset Edits", key=f"reset_upload_{i}", help="Revert to original image"):
                st.session_state.upload_previews[i] = io.BytesIO(file_data)
                st.rerun()

            st.markdown("</div>", unsafe_allow_html=True)

        col1, col2 = st.columns([1, 1])
        with col1:
            if st.button("⬅️ Back to Upload", help="Return to upload selection"):
                st.session_state.upload_step = 0
                st.session_state.upload_previews = []
                st.session_state.form_upload_folder = None
                st.session_state.form_download_allowed = None
                st.rerun()
        with col2:
            if st.button("✅ Upload Images", help="Save all edited images"):
                with st.spinner("Uploading images..."):
                    progress_bar = st.progress(0)
                    for j in range(len(edited_data_list)):
                        progress_bar.progress((j + 1) / len(edited_data_list))
                    DatabaseManager.load_images_to_db(edited_data_list, folder_choice, st.session_state.get("form_download_allowed", True))
                st.success(f"{len(edited_data_list)} image(s) uploaded!")
                st.balloons()
                st.session_state.upload_step = 0
                st.session_state.upload_previews = []
                st.session_state.form_upload_folder = None
                st.session_state.form_download_allowed = None
                st.rerun()
    
    elif st.session_state.zoom_folder:
        folder = st.session_state.zoom_folder
        images = DatabaseManager.get_images(folder)
        idx = st.session_state.zoom_index
        if idx >= len(images):
            idx = 0
            st.session_state.zoom_index = 0
        img_dict = images[idx]

        st.subheader(f"🖼️ Viewing {folder} ({idx+1}/{len(images)})")
        
        # Display the image
        st.image(img_dict["image"], use_container_width=True)

        col1, col2, col3 = st.columns([1, 6, 1])
        with col1:
            if idx > 0 and st.button("◄ Previous", key=f"prev_{folder}", help="View previous image"):
                st.session_state.zoom_index -= 1
                st.rerun()
        with col3:
            if idx < len(images) - 1 and st.button("Next ►", key=f"next_{folder}", help="View next image"):
                st.session_state.zoom_index += 1
                st.rerun()

        if img_dict["download"]:
            mime = "image/jpeg" if img_dict["name"].lower().endswith(('.jpg', '.jpeg')) else "image/png"
            st.download_button("⬇️ Download", data=img_dict["data"], file_name=img_dict["name"], mime=mime, help="Download this image")

        if st.session_state.is_author:
            with st.expander("✏️ Edit Image", expanded=True):
                with st.form(key=f"edit_image_form_{folder}_{img_dict['name']}"):
                    rotate_angle = st.slider("Rotate (degrees)", -180, 180, 0, key=f"rotate_{folder}_{img_dict['name']}", help="Rotate the image")
                    brightness = st.slider("Brightness", 0.0, 2.0, 1.0, step=0.1, key=f"brightness_{folder}_{img_dict['name']}", help="Adjust brightness")
                    contrast = st.slider("Contrast", 0.0, 2.0, 1.0, step=0.1, key=f"contrast_{folder}_{img_dict['name']}", help="Adjust contrast")
                    sharpness = st.slider("Sharpness", 0.0, 2.0, 1.0, step=0.1, key=f"sharpness_{folder}_{img_dict['name']}", help="Adjust sharpness")
                    grayscale = st.checkbox("Grayscale", key=f"grayscale_{folder}_{img_dict['name']}", help="Convert to grayscale")

                    if st.form_submit_button("💾 Apply Edits"):
                        image_id = DatabaseManager.get_image_id(folder, img_dict["name"])
                        if image_id:
                            DatabaseManager.save_image_history(image_id, folder, img_dict["data"])

                        edited_data = img_dict["data"]
                        if rotate_angle != 0:
                            edited_data = ImageProcessor.rotate_image(edited_data, rotate_angle)
                        if brightness != 1.0:
                            edited_data = ImageProcessor.adjust_brightness(edited_data, brightness)
                        if contrast != 1.0:
                            edited_data = ImageProcessor.adjust_contrast(edited_data, contrast)
                        if sharpness != 1.0:
                            edited_data = ImageProcessor.adjust_sharpness(edited_data, sharpness)
                        if grayscale:
                            edited_data = ImageProcessor.convert_to_grayscale(edited_data)

                        if edited_data:
                            conn = DatabaseManager.connect()
                            try:
                                c = conn.cursor()
                                c.execute("UPDATE images SET image_data = ? WHERE folder = ? AND name = ?",
                                          (edited_data, folder, img_dict["name"]))
                                conn.commit()
                                st.success("Image edited successfully!")
                                st.balloons()
                                logger.info(f"Applied edits to image '{img_dict['name']}' in folder '{folder}'")
                                st.rerun()
                            finally:
                                conn.close()
                        else:
                            st.error("Failed to edit image.")

                    if st.button("↩️ Undo Last Edit", help="Revert to the previous version"):
                        if DatabaseManager.undo_image_edit(folder, img_dict["name"]):
                            st.success("Image restored!")
                            st.balloons()
                            st.rerun()
                        else:
                            st.error("No previous version available.")

            if st.button("🗑️ Delete Image", key=f"delete_{folder}_{img_dict['name']}", help="Delete this image"):
                DatabaseManager.delete_image(folder, img_dict["name"])
                st.success("Image deleted!")
                st.balloons()
                st.session_state.zoom_index = max(0, idx - 1)
                if len(DatabaseManager.get_images(folder)) == 0:
                    st.session_state.zoom_folder = None
                    st.session_state.zoom_index = 0
                st.rerun()

        if st.button("⬅️ Back to Gallery", key=f"back_{folder}", help="Return to gallery view"):
            st.session_state.zoom_folder = None
            st.session_state.zoom_index = 0
            st.session_state.crop_coords = None
            st.rerun()

    else:
        st.info("Select a category or use the search bar to explore folders.")

# Category Tabs
for cat, tab in zip(categories, tabs[2:-1]):
    with tab:
        cat_folders = [f for f in data if f["category"] == cat]
        for f in cat_folders:
            st.markdown(
                f'<div class="folder-card" role="region" aria-label="{f["name"]} folder">'
                f'<div class="folder-header">{f["name"]} ({f["age"]}, {f["profession"]})</div>',
                unsafe_allow_html=True
            )

            images = DatabaseManager.get_images(f["folder"])
            if images:
                st.markdown('<div class="image-grid">', unsafe_allow_html=True)
                cols = st.columns(4)
                for idx, img_dict in enumerate(images):
                    with cols[idx % len(cols)]:
                        if st.button("🔍 View", key=f"view_{f['folder']}_{idx}", help=f"View details for image {idx+1}"):
                            st.session_state.zoom_folder = f["folder"]
                            st.session_state.zoom_index = idx
                            st.rerun()
                        st.image(img_dict["thumbnail"], use_container_width=True, caption=f"Image {idx+1}")
                st.markdown('</div>', unsafe_allow_html=True)
            else:
                st.warning(f"No images found for {f['name']}")

            with st.expander(f"📝 Feedback for {f['name']}"):
                with st.form(key=f"survey_form_{f['folder']}"):
                    rating = st.slider("Rating (1-5)", 1, 5, 3, key=f"rating_{f['folder']}", help="Rate this folder")
                    feedback = st.text_area("Feedback", key=f"feedback_{f['folder']}", help="Share your thoughts")
                    if st.form_submit_button("✅ Submit Feedback"):
                        timestamp = datetime.now().isoformat()
                        DatabaseManager.save_survey_data(f["folder"], rating, feedback, timestamp)
                        st.success("Feedback submitted!")
                        st.balloons()
                        st.rerun()

                if f["folder"] in survey_data and survey_data[f["folder"]]:
                    st.write("### Previous Feedback")
                    ratings = [entry['rating'] for entry in survey_data[f["folder"]]]
                    avg_rating = sum(ratings) / len(ratings)
                    st.markdown(f"**Average Rating:** ⭐ {avg_rating:.1f} ({len(ratings)} reviews)")
                    for entry in survey_data[f["folder"]]:
                        cols = st.columns([6, 1])
                        with cols[0]:
                            rating_display = "⭐" * entry["rating"]
                            st.markdown(
                                f"- {rating_display} — {entry['feedback']}  \n"
                                f"<sub>🕒 {entry['timestamp']}</sub>",
                                unsafe_allow_html=True
                            )
                        if st.session_state.is_author:
                            with cols[1]:
                                if st.button("🗑️", key=f"delete_survey_{f['folder']}_{entry['timestamp']}", help="Delete this feedback"):
                                    DatabaseManager.delete_survey_entry(f["folder"], entry["timestamp"])
                                    st.success("Feedback deleted!")
                                    st.balloons()
                                    st.rerun()
                else:
                    st.info("No feedback yet — share your thoughts!")

# Help Tab
with tabs[-1]:
    st.markdown("## 📖 Help & Guide")
    st.markdown("""
    ### Getting Started
    - **Browse**: Use the category tabs or search bar to find folders.
    - **View Images**: Click 🔍 to zoom in on an image.
    - **Provide Feedback**: Rate and comment on folders in the feedback section.
    - **Admin Access**: Log in via the sidebar to manage content.

    ### Admin Tools
    1. **Login**: Enter the admin password in the sidebar.
    2. **Add Folders**: Create new folders with a name, age, profession, and category.
    3. **Upload Images**: Select a folder, upload images, and edit them (rotate, brightness, etc.).
    4. **Edit Images**: In zoom view, apply edits or undo changes.
    5. **Manage Permissions**: Control which images can be downloaded.

    ### Tips
    - Use the dark mode toggle for better visibility.
    - Images must be JPG/PNG and under 5MB.
    """)
