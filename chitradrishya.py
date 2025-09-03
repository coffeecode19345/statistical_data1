import streamlit as st
import sqlite3
import io
from PIL import Image
import os
from datetime import datetime
import uuid
import re
import base64
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
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "admin123")  # Fallback for testing
DB_PATH = "gallery.db"
MAX_FILE_SIZE_MB = 5  # Max file size for uploads in MB
FORCE_DB_RESET = os.getenv("FORCE_DB_RESET", "False").lower() == "true"

# -------------------------------
# Helper Functions
# -------------------------------
def image_to_base64(image_data):
    """Convert image data (bytes) to base64 string."""
    if not isinstance(image_data, bytes):
        raise ValueError("image_data must be bytes")
    return base64.b64encode(image_data).decode('utf-8')

def thumbnail_to_bytes(image):
    """Convert PIL Image to bytes."""
    output = io.BytesIO()
    image.save(output, format="PNG")
    return output.getvalue()

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
        Image.open(file).verify()  # Verify image integrity
        file.seek(0)  # Reset file pointer
    except Exception as e:
        st.error(f"File '{file.name}' is invalid or corrupted.")
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
            st.error("Cannot connect to the database. Please try again later.")
            raise

    @staticmethod
    def init_db():
        """Initialize database with required tables."""
        db_dir = os.path.dirname(DB_PATH) or "."
        if not os.access(db_dir, os.W_OK):
            logger.error(f"Directory {db_dir} is not writable")
            st.error("Cannot write to the database directory. Check permissions.")
            raise PermissionError(f"Directory {db_dir} is not writable")

        if FORCE_DB_RESET and os.path.exists(DB_PATH):
            try:
                os.remove(DB_PATH)
                logger.info(f"Deleted existing database file {DB_PATH} due to FORCE_DB_RESET")
            except Exception as e:
                logger.error(f"Failed to delete database file {DB_PATH}: {str(e)}")
                st.error("Failed to reset the database. Please try again.")
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
            st.error("Failed to set up the database. Please try again.")
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
            st.error("Failed to update folder name. Please try again.")
            return False
        finally:
            conn.close()

    @staticmethod
    def add_folder(folder, name, age, profession, category):
        """Add a new folder to the database with validation."""
        if not validate_folder_name(folder):
            logger.warning(f"Invalid folder name: {folder}")
            st.error("Folder name must be 3-20 lowercase letters, numbers, or underscores (e.g., 'artist4').")
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
            st.error(f"Folder '{folder}' already exists. Try a different name.")
            return False
        except Exception as e:
            logger.error(f"Error adding folder: {str(e)}")
            st.error("Failed to create folder. Please try again.")
            return False
        finally:
            conn.close()

    @staticmethod
    def load_images_to_db(image_data_list, folder, download_allowed=True):
        """Load images into the database."""
        conn = DatabaseManager.connect()
        try:
            c = conn.cursor()
            c.execute("SELECT COUNT(*) FROM folders WHERE folder = ?", (folder,))
            if c.fetchone()[0] == 0:
                raise ValueError(f"Folder '{folder}' does not exist")
            for image_data in image_data_list:
                extension = ".png"
                random_filename = f"{uuid.uuid4()}{extension}"
                c.execute("SELECT COUNT(*) FROM images WHERE folder = ? AND name = ?", (folder, random_filename))
                if c.fetchone()[0] == 0:
                    c.execute("INSERT INTO images (name, folder, image_data, download_allowed) VALUES (?, ?, ?, ?)",
                              (random_filename, folder, image_data, download_allowed))
            conn.commit()
            logger.info(f"Uploaded {len(image_data_list)} images to folder '{folder}'")
        except ValueError as e:
            logger.error(f"Error uploading images: {str(e)}")
            st.error(f"Error: {str(e)}")
        except sqlite3.OperationalError as e:
            logger.error(f"Database error during image upload: {str(e)}")
            st.error("Failed to upload images. Please try again.")
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
            st.error("Failed to replace image. Please try again.")
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
            st.error("Failed to undo edit. No previous version available.")
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
                    thumbnail = ImageProcessor.generate_thumbnail(img, size=(80, 80))
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
                    st.error(f"Error loading image {name}. It may be corrupted.")
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
            st.error("Failed to crop image. Ensure the crop area is within the image.")
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
            st.error("Failed to rotate image. Please try again.")
            return None

# -------------------------------
# Initialize DB & Session State
# -------------------------------
try:
    DatabaseManager.init_db()
except sqlite3.OperationalError as e:
    st.error("Failed to set up the database. Please try again.")
    logger.error(f"Database initialization failed: {str(e)}")
    st.stop()

# Initialize session state
if "zoom_folder" not in st.session_state:
    st.session_state.zoom_folder = None
if "zoom_index" not in st.session_state:
    st.session_state.zoom_index = 0
if "is_author" not in st.session_state:
    st.session_state.is_author = False
if "crop_coords" not in st.session_state:
    st.session_state.crop_coords = {}
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
if "edit_history" not in st.session_state:
    st.session_state.edit_history = {}

# JavaScript for persistent login state
st.markdown("""
<script>
function setCookie(name, value, days) {
    let expires = "";
    if (days) {
        let date = new Date();
        date.setTime(date.getTime() + (days * 24 * 60 * 60 * 1000));
        expires = "; expires=" + date.toUTCString();
    }
    document.cookie = name + "=" + value + expires + "; path=/";
}

function getCookie(name) {
    let nameEQ = name + "=";
    let ca = document.cookie.split(';');
    for(let i = 0; i < ca.length; i++) {
        let c = ca[i];
        while (c.charAt(0) == ' ') c = c.substring(1, c.length);
        if (c.indexOf(nameEQ) == 0) return c.substring(nameEQ.length, c.length);
    }
    return null;
}

window.addEventListener('load', function() {
    let isAuthor = getCookie('is_author');
    if (isAuthor === 'true') {
        let input = document.createElement('input');
        input.type = 'hidden';
        input.id = 'restore_is_author';
        input.value = 'true';
        document.body.appendChild(input);
    }
});
</script>
""", unsafe_allow_html=True)

# Check for restored is_author state
try:
    restore_is_author = st_javascript("document.getElementById('restore_is_author') ? document.getElementById('restore_is_author').value : ''")
    if restore_is_author == 'true' and not st.session_state.is_author:
        st.session_state.is_author = True
        logger.info("Restored admin login state from cookie")
except Exception as e:
    logger.warning(f"Failed to execute st_javascript: {str(e)}")

# -------------------------------
# CSS and JavaScript for UI
# -------------------------------
st.markdown("""
<style>
body {
    font-family: 'Arial', sans-serif;
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
}
.header h1 {
    margin: 0;
    font-size: 1.8rem;
    color: var(--text-color, #1a1a1a);
}
.folder-card {
    background: var(--card-bg, #ffffff);
    border-radius: 10px;
    padding: 1rem;
    margin-bottom: 1rem;
    box-shadow: 0 2px 8px rgba(0,0,0,0.1);
}
.folder-header {
    font-size: 1.2rem;
    font-weight: bold;
    color: var(--text-color, #1a1a1a);
    margin-bottom: 0.5rem;
}
.image-grid {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(100px, 1fr));
    gap: 0.5rem;
}
img {
    border-radius: 5px;
    object-fit: cover;
    width: 100%;
}
.edit-container {
    display: flex;
    gap: 1rem;
    padding: 1rem;
    background: var(--card-bg, #ffffff);
    border-radius: 10px;
}
.canvas-container {
    position: relative;
    margin: 0.5rem 0;
}
#cropCanvas {
    border: 2px solid #007bff;
    border-radius: 5px;
}
.stButton>button {
    border-radius: 5px;
    padding: 0.5rem 1rem;
    font-size: 1rem;
}
.stButton>button:hover {
    background-color: #e6f0ff;
}
.thumbnail-grid img {
    cursor: pointer;
    border: 2px solid transparent;
}
.thumbnail-grid img.selected {
    border: 2px solid #007bff;
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
<script>
function initCropCanvas(canvasId, imageId, hiddenInputId) {
    const canvas = document.getElementById(canvasId);
    const ctx = canvas.getContext('2d');
    const img = document.getElementById(imageId);
    let isDrawing = false;
    let startX, startY, endX, endY;

    img.onload = function() {
        canvas.width = img.width;
        canvas.height = img.height;
        ctx.drawImage(img, 0, 0);
    };

    canvas.addEventListener('mousedown', (e) => {
        isDrawing = true;
        const rect = canvas.getBoundingClientRect();
        startX = e.clientX - rect.left;
        startY = e.clientY - rect.top;
        endX = startX;
        endY = startY;
    });

    canvas.addEventListener('mousemove', (e) => {
        if (!isDrawing) return;
        const rect = canvas.getBoundingClientRect();
        endX = e.clientX - rect.left;
        endY = e.clientY - rect.top;

        ctx.clearRect(0, 0, canvas.width, canvas.height);
        ctx.drawImage(img, 0, 0);
        
        ctx.beginPath();
        ctx.setLineDash([5, 5]);
        ctx.strokeStyle = '#007bff';
        ctx.lineWidth = 2;
        ctx.rect(startX, startY, endX - startX, endY - startY);
        ctx.stroke();
    });

    canvas.addEventListener('mouseup', () => {
        isDrawing = false;
        const coords = {
            x: Math.min(startX, endX),
            y: Math.min(startY, endY),
            width: Math.abs(endX - startX),
            height: Math.abs(endY - startY)
        };
        document.getElementById(hiddenInputId).value = JSON.stringify(coords);
    });
}
</script>
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
    search_query = st.text_input("Search folders...", value=st.session_state.search_query, key="search_input", placeholder="Type name, profession, or category")
with col3:
    if st.button("🌙 Toggle Dark Mode"):
        st.session_state.dark_mode = not st.session_state.dark_mode
        st.rerun()

# -------------------------------
# Sidebar: Admin Controls
# -------------------------------
with st.sidebar:
    st.subheader("🛠️ Admin Tools", help="Log in to manage photos and folders")
    if not st.session_state.is_author:
        with st.form(key="login_form"):
            pwd = st.text_input("Admin Password", type="password", placeholder="Enter admin password")
            if st.form_submit_button("🔐 Login"):
                if pwd == ADMIN_PASSWORD:
                    st.session_state.is_author = True
                    st.balloons()
                    st.success("You're logged in as admin!")
                    logger.info("Admin logged in")
                    st.markdown("<script>setCookie('is_author', 'true', 1);</script>", unsafe_allow_html=True)
                    st.rerun()
                else:
                    st.error("Wrong password. Try again.")
                    logger.warning("Failed login attempt")
    else:
        if st.button("🔓 Logout"):
            st.session_state.is_author = False
            st.success("Logged out")
            logger.info("Admin logged out")
            st.markdown("<script>setCookie('is_author', 'false', 1);</script>", unsafe_allow_html=True)
            st.rerun()

        with st.expander("📁 Add New Folder"):
            with st.form(key="add_folder_form"):
                st.markdown("**Create a new folder**")
                new_folder = st.text_input("Folder Name", placeholder="e.g., artist4", help="Use lowercase letters, numbers, or underscores (3-20 characters)")
                new_name = st.text_input("Person Name", placeholder="e.g., Jane Smith")
                new_age = st.number_input("Age", min_value=1, max_value=150, value=30)
                new_profession = st.text_input("Profession", placeholder="e.g., Photographer")
                new_category = st.selectbox("Category", ["Artists", "Engineers", "Teachers"])
                if st.form_submit_button("➕ Add Folder"):
                    if new_folder and new_name and new_profession and new_category:
                        if DatabaseManager.add_folder(new_folder.lower(), new_name, new_age, new_profession, new_category):
                            st.success(f"Folder '{new_folder}' created!")
                            st.balloons()
                            st.rerun()
                        else:
                            st.error("Failed to create folder. Check the folder name.")
                    else:
                        st.error("Please fill in all fields.")

        with st.expander("🖼️ Upload Photos"):
            data = DatabaseManager.load_folders()
            with st.form(key="upload_images_form"):
                folder_choice = st.selectbox("Select Folder", [item["folder"] for item in data], key="upload_folder")
                st.markdown(f"**Uploading to: {folder_choice}**")
                download_allowed = st.checkbox("Allow Downloads", value=True, help="Let others download these photos")
                uploaded_files = st.file_uploader("Choose Photos", accept_multiple_files=True, type=['jpg', 'png'], key="upload_files", help="Select JPG or PNG files (max 5MB each)")
                col1, col2 = st.columns(2)
                with col1:
                    if st.form_submit_button("✅ Upload Now"):
                        if uploaded_files:
                            valid_files = [f for f in uploaded_files if validate_file(f)]
                            if valid_files:
                                with st.spinner("Uploading photos..."):
                                    DatabaseManager.load_images_to_db([f.read() for f in valid_files], folder_choice, download_allowed)
                                st.success(f"{len(valid_files)} photo(s) uploaded to '{folder_choice}'!")
                                st.balloons()
                                st.rerun()
                            else:
                                st.error("No valid photos uploaded. Check file types and sizes.")
                        else:
                            st.error("Please select at least one photo.")
                with col2:
                    if st.form_submit_button("✏️ Edit & Upload"):
                        if uploaded_files:
                            valid_files = [f for f in uploaded_files if validate_file(f)]
                            if valid_files:
                                st.session_state.upload_previews = [
                                    {"file": f, "data": f.read(), "original_data": f.read()} for f in valid_files
                                ]
                                for f in valid_files:
                                    f.seek(0)
                                st.session_state.upload_step = 1
                                st.session_state.form_upload_folder = folder_choice
                                st.session_state.form_download_allowed = download_allowed
                                st.session_state.edit_history = {f["file"].name: [] for f in st.session_state.upload_previews}
                                st.success(f"Ready to edit photos for '{folder_choice}'")
                                st.rerun()
                            else:
                                st.error("No valid photos uploaded. Check file types and sizes.")
                        else:
                            st.error("Please select at least one photo.")

        with st.expander("✏️ Rename Folder"):
            data = DatabaseManager.load_folders()
            folder_choice_name = st.selectbox("Select Folder", [item["folder"] for item in data], key="edit_name_folder")
            current_name = next(item["name"] for item in data if item["folder"] == folder_choice_name)
            with st.form(key="edit_name_form"):
                new_name = st.text_input("New Name", value=current_name, placeholder="e.g., John Doe")
                if st.form_submit_button("💾 Save Name"):
                    if new_name:
                        if DatabaseManager.update_folder_name(folder_choice_name, new_name):
                            st.success(f"Name changed to '{new_name}'!")
                            st.balloons()
                            st.rerun()
                        else:
                            st.error("Failed to change name.")
                    else:
                        st.error("Please enter a name.")

        with st.expander("🔄 Replace Photo"):
            data = DatabaseManager.load_folders()
            folder_choice_swap = st.selectbox("Select Folder", [item["folder"] for item in data], key="swap_folder")
            images = DatabaseManager.get_images(folder_choice_swap)
            if images:
                image_choice = st.selectbox("Select Photo", [img["name"][:8] + "..." + img["name"][-4:] for img in images], key="swap_image")
                new_image = st.file_uploader("Choose New Photo", type=['jpg', 'png'], key="swap_upload")
                if st.button("🔄 Replace Photo"):
                    if new_image and validate_file(new_image):
                        if DatabaseManager.swap_image(folder_choice_swap, images[[img["name"] for img in images].index(image_choice)]["name"], new_image):
                            st.success("Photo replaced!")
                            st.balloons()
                            st.rerun()
                        else:
                            st.error("Failed to replace photo.")
                    else:
                        st.error("Please upload a valid JPG or PNG photo.")

        with st.expander("🔒 Download Permissions"):
            data = DatabaseManager.load_folders()
            folder_choice_perm = st.selectbox("Select Folder", [item["folder"] for item in data], key=f"download_folder_{uuid.uuid4()}")
            images = DatabaseManager.get_images(folder_choice_perm)
            if images:
                with st.form(key=f"download_permissions_form_{folder_choice_perm}"):
                    st.write("Choose which photos can be downloaded:")
                    download_states = {}
                    for img_dict in images:
                        toggle_key = f"download_toggle_{folder_choice_perm}_{img_dict['name']}"
                        download_states[img_dict['name']] = st.checkbox(
                            f"Allow {img_dict['name'][:8]}...{img_dict['name'][-4:]}",
                            value=img_dict["download"],
                            key=toggle_key
                        )
                    if st.form_submit_button("💾 Save Permissions"):
                        for img_dict in images:
                            if download_states[img_dict['name']] != img_dict["download"]:
                                DatabaseManager.update_download_permission(folder_choice_perm, img_dict["name"], download_states[img_dict['name']])
                        st.success("Permissions updated!")
                        st.balloons()
                        st.rerun()

# -------------------------------
# Main App UI
# -------------------------------
if search_query != st.session_state.search_query:
    st.session_state.search_query = search_query
    st.rerun()

data = DatabaseManager.load_folders(st.session_state.search_query)
survey_data = DatabaseManager.load_survey_data()

categories = sorted(set(item["category"] for item in data))
tab_names = ["Home", "Gallery"] + categories + ["Help"]
tabs = st.tabs(tab_names)

# Home Tab
with tabs[0]:
    st.markdown("## Welcome to the Photo Gallery! 🎉")
    st.write("Browse photos, give feedback, or log in as admin to manage content.")
    st.markdown("""
    - **Browse**: Click category tabs (Artists, Engineers, Teachers) to see photos.
    - **Search**: Use the search bar to find folders by name or profession.
    - **Feedback**: Rate folders and add comments.
    - **Admin**: Log in (sidebar) to add or edit photos and folders.
    """)
    st.markdown("### Folder Ratings")
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
            title="Average Ratings",
            xaxis_title="Folder",
            yaxis_title="Rating (1-5)",
            showlegend=False,
            template="plotly_white" if not st.session_state.dark_mode else "plotly_dark"
        )
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("No ratings yet. Add feedback to see ratings here!")

# Gallery Tab (for upload/edit or zoom view)
with tabs[1]:
    if st.session_state.upload_step == 1 and st.session_state.is_author:
        st.subheader(f"🖼️ Editing Photos for {st.session_state.form_upload_folder}")
        valid_files = st.session_state.upload_previews
        
        st.markdown("### Choose a Photo to Edit")
        cols = st.columns(5)
        selected_index = st.session_state.get("selected_image_index", 0)
        for idx, file_dict in enumerate(valid_files):
            with cols[idx % 5]:
                thumbnail = ImageProcessor.generate_thumbnail(Image.open(io.BytesIO(file_dict["data"])), size=(80, 80))
                base64_thumb = image_to_base64(thumbnail_to_bytes(thumbnail))
                caption = file_dict["file"].name[:10] + "..." if len(file_dict["file"].name) > 10 else file_dict["file"].name
                if st.image(
                    f"data:image/png;base64,{base64_thumb}",
                    caption=caption,
                    use_column_width=True,
                    output_format="PNG"
                ):
                    st.session_state.selected_image_index = idx
                    st.rerun()

        if valid_files:
            file_dict = valid_files[selected_index]
            st.markdown(f"<div class='edit-container'>", unsafe_allow_html=True)
            
            with st.container():
                st.markdown(f"### Editing: {file_dict['file'].name}")
                img = Image.open(io.BytesIO(file_dict["data"]))
                st.write(f"Size: {len(file_dict['data']) / (1024 * 1024):.2f} MB, Dimensions: {img.width}x{img.height}")
                
                base64_image = image_to_base64(file_dict["data"])
                canvas_id = f"cropCanvas_{selected_index}"
                image_id = f"editImage_{selected_index}"
                hidden_input_id = f"crop_coords_{selected_index}"
                
                st.markdown(f"""
                <div class='canvas-container'>
                    <canvas id='{canvas_id}'></canvas>
                    <img id='{image_id}' src='data:image/png;base64,{base64_image}' style='display:none;'>
                    <input type='hidden' id='{hidden_input_id}' name='crop_coords'>
                </div>
                <script>
                    initCropCanvas('{canvas_id}', '{image_id}', '{hidden_input_id}');
                </script>
                """, unsafe_allow_html=True)
                
                col1, col2 = st.columns(2)
                with col1:
                    st.markdown("**Original**")
                    st.image(file_dict["original_data"], use_column_width=True)
                with col2:
                    st.markdown("**Edited**")
                    st.image(file_dict["data"], use_column_width=True)
            
            with st.container():
                with st.form(key=f"edit_upload_form_{selected_index}"):
                    st.markdown("### Edit Options")
                    apply_crop = st.checkbox("Apply Crop", key=f"apply_crop_{selected_index}", help="Check to apply the cropped area")
                    rotate_angle = st.slider("Rotate (degrees)", -180, 180, 0, key=f"upload_rotate_{selected_index}", help="Rotate the photo")
                    
                    col1, col2 = st.columns(2)
                    with col1:
                        if st.form_submit_button("💾 Save Edits"):
                            edited_data = file_dict["data"]
                            crop_coords = st.session_state.crop_coords.get(file_dict["file"].name)
                            if apply_crop and crop_coords:
                                edited_data = ImageProcessor.crop_image(edited_data, (
                                    crop_coords["x"], crop_coords["y"],
                                    crop_coords["x"] + crop_coords["width"],
                                    crop_coords["y"] + crop_coords["height"]
                                ))
                            if rotate_angle != 0:
                                edited_data = ImageProcessor.rotate_image(edited_data, rotate_angle)
                            if edited_data:
                                st.session_state.edit_history[file_dict["file"].name].append(file_dict["data"])
                                valid_files[selected_index]["data"] = edited_data
                                st.session_state.upload_previews = valid_files
                                st.success("Edits saved!")
                                st.rerun()
                    
                    with col2:
                        if st.form_submit_button("↩️ Undo Edit"):
                            if st.session_state.edit_history[file_dict["file"].name]:
                                valid_files[selected_index]["data"] = st.session_state.edit_history[file_dict["file"].name].pop()
                                st.session_state.upload_previews = valid_files
                                st.success("Edit undone!")
                                st.rerun()
                            else:
                                st.error("No edits to undo.")

                if st.button("🔄 Reset Photo", key=f"reset_upload_{selected_index}", help="Revert to original photo"):
                    valid_files[selected_index]["data"] = file_dict["original_data"]
                    st.session_state.upload_previews = valid_files
                    st.session_state.edit_history[file_dict["file"].name] = []
                    st.session_state.crop_coords[file_dict["file"].name] = {}
                    st.success("Photo reset to original!")
                    st.rerun()

            st.markdown("</div>", unsafe_allow_html=True)
        
        col1, col2 = st.columns(2)
        with col1:
            if st.button("⬅️ Back to Upload"):
                st.session_state.upload_step = 0
                st.session_state.upload_previews = []
                st.session_state.form_upload_folder = None
                st.session_state.form_download_allowed = None
                st.session_state.edit_history = {}
                st.session_state.crop_coords = {}
                st.rerun()
        with col2:
            if st.button("✅ Save All Photos"):
                with st.spinner("Saving photos..."):
                    edited_data_list = [f["data"] for f in valid_files]
                    DatabaseManager.load_images_to_db(edited_data_list, st.session_state.form_upload_folder, st.session_state.form_download_allowed)
                st.success(f"{len(edited_data_list)} photo(s) saved to '{st.session_state.form_upload_folder}'!")
                st.balloons()
                st.session_state.upload_step = 0
                st.session_state.upload_previews = []
                st.session_state.form_upload_folder = None
                st.session_state.form_download_allowed = None
                st.session_state.edit_history = {}
                st.session_state.crop_coords = {}
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
        st.image(img_dict["image"], use_column_width=True)

        col1, col2, col3 = st.columns([1, 6, 1])
        with col1:
            if idx > 0 and st.button("◄ Previous"):
                st.session_state.zoom_index -= 1
                st.rerun()
        with col3:
            if idx < len(images) - 1 and st.button("Next ►"):
                st.session_state.zoom_index += 1
                st.rerun()

        if img_dict["download"]:
            mime = "image/jpeg" if img_dict["name"].lower().endswith(('.jpg', '.jpeg')) else "image/png"
            st.download_button("⬇️ Download", data=img_dict["data"], file_name=img_dict["name"], mime=mime)

        if st.session_state.is_author:
            with st.expander("✏️ Edit Photo"):
                base64_image = img_dict["base64"]
                canvas_id = f"cropCanvas_zoom_{idx}"
                image_id = f"editImage_zoom_{idx}"
                hidden_input_id = f"crop_coords_zoom_{idx}"
                
                st.markdown(f"""
                <div class='canvas-container'>
                    <canvas id='{canvas_id}'></canvas>
                    <img id='{image_id}' src='data:image/png;base64,{base64_image}' style='display:none;'>
                    <input type='hidden' id='{hidden_input_id}' name='crop_coords'>
                </div>
                <script>
                    initCropCanvas('{canvas_id}', '{image_id}', '{hidden_input_id}');
                </script>
                """, unsafe_allow_html=True)
                
                col1, col2 = st.columns(2)
                with col1:
                    st.markdown("**Original**")
                    st.image(img_dict["data"], use_column_width=True)
                with col2:
                    st.markdown("**Edited**")
                    edited_data = img_dict["data"]
                    crop_coords = st.session_state.crop_coords.get(img_dict["name"])
                    if crop_coords:
                        edited_data = ImageProcessor.crop_image(edited_data, (
                            crop_coords["x"], crop_coords["y"],
                            crop_coords["x"] + crop_coords["width"],
                            crop_coords["y"] + crop_coords["height"]
                        ))
                    st.image(edited_data, use_column_width=True)

                with st.form(key=f"edit_image_form_{folder}_{img_dict['name']}"):
                    apply_crop = st.checkbox("Apply Crop", help="Check to apply the cropped area")
                    rotate_angle = st.slider("Rotate (degrees)", -180, 180, 0, help="Rotate the photo")
                    
                    col1, col2 = st.columns(2)
                    with col1:
                        if st.form_submit_button("💾 Save Edits"):
                            image_id = DatabaseManager.get_image_id(folder, img_dict["name"])
                            if image_id:
                                DatabaseManager.save_image_history(image_id, folder, img_dict["data"])
                            edited_data = img_dict["data"]
                            if apply_crop and crop_coords:
                                edited_data = ImageProcessor.crop_image(edited_data, (
                                    crop_coords["x"], crop_coords["y"],
                                    crop_coords["x"] + crop_coords["width"],
                                    crop_coords["y"] + crop_coords["height"]
                                ))
                            if rotate_angle != 0:
                                edited_data = ImageProcessor.rotate_image(edited_data, rotate_angle)
                            if edited_data:
                                conn = DatabaseManager.connect()
                                try:
                                    c = conn.cursor()
                                    c.execute("UPDATE images SET image_data = ? WHERE folder = ? AND name = ?",
                                              (edited_data, folder, img_dict["name"]))
                                    conn.commit()
                                    st.success("Photo edited!")
                                    st.balloons()
                                    logger.info(f"Applied edits to image '{img_dict['name']}' in folder '{folder}'")
                                    st.rerun()
                                finally:
                                    conn.close()
                    
                    with col2:
                        if st.form_submit_button("↩️ Undo Edit"):
                            if DatabaseManager.undo_image_edit(folder, img_dict["name"]):
                                st.success("Photo restored!")
                                st.balloons()
                                st.rerun()

            if st.button("🗑️ Delete Photo"):
                DatabaseManager.delete_image(folder, img_dict["name"])
                st.success("Photo deleted!")
                st.balloons()
                st.session_state.zoom_index = max(0, idx - 1)
                if len(DatabaseManager.get_images(folder)) == 0:
                    st.session_state.zoom_folder = None
                    st.session_state.zoom_index = 0
                st.rerun()

        if st.button("⬅️ Back to Gallery"):
            st.session_state.zoom_folder = None
            st.session_state.zoom_index = 0
            st.session_state.crop_coords = {}
            st.rerun()

    else:
        st.info("Select a category or search to view photos.")

# Category Tabs
for cat, tab in zip(categories, tabs[2:-1]):
    with tab:
        cat_folders = [f for f in data if f["category"] == cat]
        for f in cat_folders:
            st.markdown(
                f'<div class="folder-card"><div class="folder-header">{f["name"]} ({f["age"]}, {f["profession"]})</div>',
                unsafe_allow_html=True
            )

            images = DatabaseManager.get_images(f["folder"])
            if images:
                st.markdown('<div class="image-grid">', unsafe_allow_html=True)
                cols = st.columns(4)
                for idx, img_dict in enumerate(images):
                    with cols[idx % len(cols)]:
                        if st.button("🔍 View", key=f"view_{f['folder']}_{idx}"):
                            st.session_state.zoom_folder = f["folder"]
                            st.session_state.zoom_index = idx
                            st.rerun()
                        st.image(img_dict["thumbnail"], use_column_width=True, caption=f"Photo {idx+1}")
                st.markdown('</div>', unsafe_allow_html=True)
            else:
                st.warning(f"No photos found for {f['name']}")

            with st.expander(f"📝 Feedback for {f['name']}"):
                with st.form(key=f"survey_form_{f['folder']}"):
                    rating = st.slider("Rating (1-5)", 1, 5, 3, key=f"rating_{f['folder']}", help="Rate this folder (1 = poor, 5 = excellent)")
                    feedback = st.text_area("Comments", key=f"feedback_{f['folder']}", placeholder="Share your thoughts (optional)")
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
                                f"- {rating_display} — {entry['feedback'] or 'No comment'}  \n"
                                f"<sub>🕒 {entry['timestamp']}</sub>",
                                unsafe_allow_html=True
                            )
                        if st.session_state.is_author:
                            with cols[1]:
                                if st.button("🗑️", key=f"delete_survey_{f['folder']}_{entry['timestamp']}"):
                                    DatabaseManager.delete_survey_entry(f["folder"], entry["timestamp"])
                                    st.success("Feedback deleted!")
                                    st.balloons()
                                    st.rerun()
                else:
                    st.info("No feedback yet. Be the first to share!")

# Help Tab
with tabs[-1]:
    st.markdown("## 📖 Help & Guide")
    st.markdown("""
    ### Getting Started
    - **Browse Photos**: Use the category tabs (Artists, Engineers, Teachers) to view folders.
    - **View Photos**: Click 🔍 to see a larger version of a photo.
    - **Search**: Type in the search bar to find folders by name or profession.
    - **Feedback**: Rate folders (1-5 stars) and add comments.

    ### Admin Guide
    1. **Log In**: Enter the admin password in the sidebar to unlock tools.
    2. **Add Folders**: Create new folders with a name, age, profession, and category.
    3. **Upload Photos**:
       - Choose a folder and select JPG/PNG photos (max 5MB each).
       - Click "Upload Now" to save directly or "Edit & Upload" to edit first.
    4. **Edit Photos**:
       - Click a thumbnail to select a photo.
       - Drag on the canvas to crop, or use the rotate slider.
       - Click "Save Edits" to apply changes, or "Undo Edit" to revert.
    5. **Manage Permissions**: Choose which photos others can download.

    ### Tips
    - **File Size**: Photos must be JPG or PNG and under 5MB.
    - **Crop Tool**: Click and drag on the photo to select an area to keep.
    - **Dark Mode**: Toggle for better visibility in low light.
    - **Need Help?**: If you see errors, try refreshing or contact support.
    """)
