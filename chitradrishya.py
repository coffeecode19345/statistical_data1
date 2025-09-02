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
import random
import string
import logging
import json

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv()
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "admin123")  # Fallback for testing
DB_PATH = "gallery.db"
MAX_FILE_SIZE_MB = 5  # Max file size for uploads in MB

# -------------------------------
# Helper Classes
# -------------------------------
class DatabaseManager:
    """Manage SQLite database operations."""
    
    @staticmethod
    def connect():
        return sqlite3.connect(DB_PATH)
    
    @staticmethod
    def init_db():
        """Initialize database with folders, images, and surveys tables."""
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
            {"name": generate_random_name(), "age": 26, "profession": "Graphic Designer", "category": "Artists", "folder": "artist1"},
            {"name": generate_random_name(), "age": 29, "profession": "Painter", "category": "Artists", "folder": "artist2"},
            {"name": generate_random_name(), "age": 30, "profession": "Literature Teacher", "category": "Teachers", "folder": "teacher1"},
            {"name": generate_random_name(), "age": 27, "profession": "Musician", "category": "Artists", "folder": "artist3"},
            {"name": generate_random_name(), "age": 47, "profession": "Data Scientist", "category": "Engineers", "folder": "engineer1"},
            {"name": generate_random_name(), "age": 25, "profession": "Software Developer", "category": "Engineers", "folder": "engineer2"},
            {"name": generate_random_name(), "age": 34, "profession": "History Teacher", "category": "Teachers", "folder": "teacher2"},
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
        logger.info("Database initialized with default folders.")

    @staticmethod
    @st.cache_data
    def load_folders(search_query=""):
        """Load folders from database, optionally filtered by search query."""
        conn = DatabaseManager.connect()
        c = conn.cursor()
        query = "SELECT folder, name, age, profession, category FROM folders WHERE name LIKE ? OR folder LIKE ? OR profession LIKE ? OR category LIKE ?"
        c.execute(query, (f"%{search_query}%", f"%{search_query}%", f"%{search_query}%", f"%{search_query}%"))
        folders = [{"folder": r[0], "name": r[1], "age": r[2], "profession": r[3], "category": r[4]} for r in c.fetchall()]
        conn.close()
        logger.info(f"Loaded {len(folders)} folders with search query: {search_query}")
        return folders

    @staticmethod
    def update_folder_name(folder, new_name):
        """Update the name of a candidate in the folders table."""
        try:
            conn = DatabaseManager.connect()
            c = conn.cursor()
            c.execute("UPDATE folders SET name = ? WHERE folder = ?", (new_name, folder))
            conn.commit()
            conn.close()
            logger.info(f"Updated name for folder '{folder}' to '{new_name}'")
            return True
        except Exception as e:
            logger.error(f"Error updating folder name: {str(e)}")
            st.error(f"Error updating folder name: {str(e)}")
            return False

    @staticmethod
    def add_folder(folder, name, age, profession, category):
        """Add a new folder to the database with validation."""
        if not validate_folder_name(folder):
            logger.warning(f"Invalid folder name: {folder}")
            st.error("Folder name must be 3-20 characters, lowercase alphanumeric or underscores.")
            return False
        try:
            conn = DatabaseManager.connect()
            c = conn.cursor()
            c.execute("""
                INSERT INTO folders (folder, name, age, profession, category)
                VALUES (?, ?, ?, ?, ?)
            """, (folder, name, age, profession, category))
            conn.commit()
            conn.close()
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

    @staticmethod
    def load_images_to_db(edited_data_list, folder, download_allowed=True):
        """Load edited images into the database."""
        conn = DatabaseManager.connect()
        c = conn.cursor()
        for edited_data in edited_data_list:
            extension = ".png"  # Since edits save as PNG
            random_filename = f"{uuid.uuid4()}{extension}"
            c.execute("SELECT COUNT(*) FROM images WHERE folder = ? AND name = ?", (folder, random_filename))
            if c.fetchone()[0] == 0:
                c.execute("INSERT INTO images (name, folder, image_data, download_allowed) VALUES (?, ?, ?, ?)",
                          (random_filename, folder, edited_data, download_allowed))
        conn.commit()
        conn.close()
        logger.info(f"Uploaded {len(edited_data_list)} images to folder '{folder}'")

    @staticmethod
    def swap_image(folder, old_image_name, new_image_file):
        """Replace an existing image with a new uploaded image."""
        try:
            conn = DatabaseManager.connect()
            c = conn.cursor()
            new_image_data = new_image_file.read()
            c.execute("UPDATE images SET image_data = ? WHERE folder = ? AND name = ?",
                      (new_image_data, folder, old_image_name))
            conn.commit()
            conn.close()
            logger.info(f"Swapped image '{old_image_name}' in folder '{folder}'")
            return True
        except Exception as e:
            logger.error(f"Error swapping image: {str(e)}")
            st.error(f"Error swapping image: {str(e)}")
            return False

    @staticmethod
    def save_image_history(image_id, folder, image_data):
        """Save image data to history for undo functionality."""
        try:
            conn = DatabaseManager.connect()
            c = conn.cursor()
            timestamp = datetime.now().isoformat()
            c.execute("INSERT INTO image_history (image_id, folder, image_data, timestamp) VALUES (?, ?, ?, ?)",
                      (image_id, folder, image_data, timestamp))
            conn.commit()
            conn.close()
            logger.info(f"Saved image history for image_id {image_id} in folder '{folder}'")
        except Exception as e:
            logger.error(f"Error saving image history: {str(e)}")

    @staticmethod
    def get_image_id(folder, image_name):
        """Get the image ID from the database."""
        conn = DatabaseManager.connect()
        c = conn.cursor()
        c.execute("SELECT id FROM images WHERE folder = ? AND name = ?", (folder, image_name))
        result = c.fetchone()
        conn.close()
        return result[0] if result else None

    @staticmethod
    def undo_image_edit(folder, image_name):
        """Restore the most recent image data from history."""
        try:
            conn = DatabaseManager.connect()
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
                conn.close()
                return True
            conn.close()
            logger.warning(f"No history found for image '{image_name}' in folder '{folder}'")
            return False
        except Exception as e:
            logger.error(f"Error undoing image edit: {str(e)}")
            st.error(f"Error undoing image edit: {str(e)}")
            return False

    @staticmethod
    def update_download_permission(folder, image_name, download_allowed):
        """Update download permission for an image."""
        conn = DatabaseManager.connect()
        c = conn.cursor()
        c.execute("UPDATE images SET download_allowed = ? WHERE folder = ? AND name = ?",
                  (download_allowed, folder, image_name))
        conn.commit()
        conn.close()
        logger.info(f"Updated download permission for '{image_name}' in folder '{folder}' to {download_allowed}")

    @staticmethod
    def delete_image(folder, name):
        """Delete an image from the database."""
        conn = DatabaseManager.connect()
        c = conn.cursor()
        c.execute("DELETE FROM images WHERE folder = ? AND name = ?", (folder, name))
        conn.commit()
        conn.close()
        logger.info(f"Deleted image '{name}' from folder '{folder}'")

    @staticmethod
    def load_survey_data():
        """Load survey data from database."""
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
        logger.info(f"Loaded survey data for {len(survey_data)} folders")
        return survey_data

    @staticmethod
    def save_survey_data(folder, rating, feedback, timestamp):
        """Save survey data to database."""
        conn = DatabaseManager.connect()
        c = conn.cursor()
        c.execute("INSERT INTO surveys (folder, rating, feedback, timestamp) VALUES (?, ?, ?, ?)",
                  (folder, rating, feedback, timestamp))
        conn.commit()
        conn.close()
        logger.info(f"Saved survey data for folder '{folder}'")

    @staticmethod
    def delete_survey_entry(folder, timestamp):
        """Delete a survey entry from database."""
        conn = DatabaseManager.connect()
        c = conn.cursor()
        c.execute("DELETE FROM surveys WHERE folder = ? AND timestamp = ?", (folder, timestamp))
        conn.commit()
        conn.close()
        logger.info(f"Deleted survey entry for folder '{folder}' at timestamp {timestamp}")

    @staticmethod
    @st.cache_data
    def get_images(folder):
        """Get images from database for a folder."""
        conn = DatabaseManager.connect()
        c = conn.cursor()
        c.execute("SELECT name, image_data, download_allowed FROM images WHERE folder = ?", (folder,))
        images = []
        for r in c.fetchall():
            name, data, download = r
            try:
                img = Image.open(io.BytesIO(data))
                thumbnail = ImageProcessor.generate_thumbnail(img)
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
        conn.close()
        logger.info(f"Loaded {len(images)} images for folder '{folder}'")
        return images

class ImageProcessor:
    """Handle image processing operations."""
    
    @staticmethod
    def generate_thumbnail(image, size=(100, 100)):
        """Generate a thumbnail for an image."""
        img = image.copy()
        img.thumbnail(size)
        return img

    @staticmethod
    def crop_image(image_data, crop_box):
        """Crop an image based on provided coordinates (left, top, right, bottom)."""
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
        """Adjust image brightness (0.0 to 2.0, 1.0 is original)."""
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
        """Adjust image contrast (0.0 to 2.0, 1.0 is original)."""
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
        """Adjust image sharpness (0.0 to 2.0, 1.0 is original)."""
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
# Helper Functions
# -------------------------------
def image_to_base64(image_data):
    """Convert image data (bytes) to base64 string."""
    return base64.b64encode(image_data).decode('utf-8') if isinstance(image_data, bytes) else image_data.encode('utf-8')

def validate_folder_name(folder):
    """Validate folder name: alphanumeric, underscores, lowercase, 3-20 characters."""
    pattern = r"^[a-z0-9_]{3,20}$"
    return bool(re.match(pattern, folder))

def generate_random_name(length=8):
    """Generate a random name for default folders."""
    return ''.join(random.choices(string.ascii_letters, k=length)).capitalize()

def validate_file(file):
    """Validate uploaded file size, type, and integrity."""
    if file.size > MAX_FILE_SIZE_MB * 1024 * 1024:
        st.error(f"File {file.name} exceeds {MAX_FILE_SIZE_MB}MB limit.")
        logger.warning(f"File {file.name} exceeds size limit")
        return False
    if not file.type in ['image/jpeg', 'image/png']:
        st.error(f"File {file.name} is not a supported type (JPG, JPEG, PNG).")
        logger.warning(f"Unsupported file type for {file.name}")
        return False
    try:
        Image.open(file).verify()  # Verify image integrity
        file.seek(0)  # Reset file pointer after verification
    except Exception as e:
        st.error(f"File {file.name} is corrupted or invalid.")
        logger.error(f"Corrupted file {file.name}: {str(e)}")
        return False
    return True

# -------------------------------
# Initialize DB & Session State
# -------------------------------
DatabaseManager.init_db()
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
if "upload_crop_coords" not in st.session_state:
    st.session_state.upload_crop_coords = {}
if "dark_mode" not in st.session_state:
    st.session_state.dark_mode = False

# -------------------------------
# CSS and JavaScript
# -------------------------------
st.markdown("""
<style>
body {
    font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
}
.folder-card {
    background: var(--card-bg, #f9f9f9);
    border-radius: 8px;
    padding: 15px;
    margin-bottom: 20px;
    box-shadow: 0 4px 8px rgba(0,0,0,0.1);
}
.folder-header {
    font-size: 1.5em;
    color: var(--text-color, #333);
    margin-bottom: 10px;
}
.image-grid {
    display: flex;
    flex-wrap: wrap;
    gap: 10px;
}
img {
    border-radius: 4px;
}
.canvas-container {
    position: relative;
    display: inline-block;
}
#cropCanvas {
    border: 2px solid #007bff;
}
.selection-box {
    position: absolute;
    border: 2px dashed #007bff;
    background: rgba(0,123,255,0.2);
    pointer-events: none;
}
.stButton>button {
    margin: 5px;
    border-radius: 4px;
}
.preview-container {
    border: 1px solid var(--border-color, #ddd);
    padding: 15px;
    margin-bottom: 15px;
    border-radius: 8px;
    background: var(--card-bg, #fff);
}
.before-after-container {
    display: flex;
    gap: 10px;
    align-items: center;
}
.before-after-image {
    max-width: 150px;
    border-radius: 4px;
}
:root {
    --card-bg: #f9f9f9;
    --text-color: #333;
    --border-color: #ddd;
}
.dark-mode {
    --card-bg: #2a2a2a;
    --text-color: #e0e0e0;
    --border-color: #555;
}
</style>
<script>
function initCropCanvas(imageId, width, height, isPreview=false, previewIndex=null) {
    const canvas = document.getElementById(imageId);
    const ctx = canvas.getContext('2d');
    let isDragging = false;
    let startX, startY, endX, endY;
    let selectionBox = null;

    function updateSelectionBox() {
        if (selectionBox) {
            selectionBox.style.left = Math.min(startX, endX) + 'px';
            selectionBox.style.top = Math.min(startY, endY) + 'px';
            selectionBox.style.width = Math.abs(endX - startX) + 'px';
            selectionBox.style.height = Math.abs(endY - startY) + 'px';
        }
    }

    canvas.addEventListener('mousedown', (e) => {
        if (!isDragging) {
            isDragging = true;
            const rect = canvas.getBoundingClientRect();
            startX = e.clientX - rect.left;
            startY = e.clientY - rect.top;
            endX = startX;
            endY = startY;

            if (!selectionBox) {
                selectionBox = document.createElement('div');
                selectionBox.className = 'selection-box';
                canvas.parentElement.appendChild(selectionBox);
            }
            updateSelectionBox();
        }
    });

    canvas.addEventListener('mousemove', (e) => {
        if (isDragging) {
            const rect = canvas.getBoundingClientRect();
            endX = Math.min(Math.max(e.clientX - rect.left, 0), canvas.width);
            endY = Math.min(Math.max(e.clientY - rect.top, 0), canvas.height);
            updateSelectionBox();
        }
    });

    canvas.addEventListener('mouseup', () => {
        if (isDragging) {
            isDragging = false;
            const coords = {
                left: Math.min(startX, endX),
                top: Math.min(startY, endY),
                right: Math.max(startX, endX),
                bottom: Math.max(startY, endY)
            };
            const coordsInputId = isPreview ? `upload_crop_coords_${previewIndex}` : 'crop_coords';
            document.getElementById(coordsInputId).value = JSON.stringify(coords);
            if (selectionBox) {
                selectionBox.remove();
                selectionBox = null;
            }
        }
    });

    canvas.addEventListener('keydown', (e) => {
        if (e.key === 'Escape' && selectionBox) {
            selectionBox.remove();
            selectionBox = null;
            isDragging = false;
            document.getElementById(coordsInputId).value = '';
        }
    });
}
function toggleDarkMode() {
    document.body.classList.toggle('dark-mode');
}
</script>
""", unsafe_allow_html=True)

# -------------------------------
# Sidebar: Author Controls
# -------------------------------
with st.sidebar:
    st.title("Author Login")
    with st.form(key="login_form"):
        pwd = st.text_input("Password", type="password", help="Enter the admin password")
        if st.form_submit_button("Login"):
            if pwd == ADMIN_PASSWORD:
                st.session_state.is_author = True
                st.success("Logged in as author!")
                logger.info("Author logged in")
            else:
                st.error("Wrong password")
                logger.warning("Failed login attempt")
    if st.session_state.is_author and st.button("Logout", help="Log out of author mode"):
        st.session_state.is_author = False
        st.success("Logged out")
        logger.info("Author logged out")
        st.rerun()

    # Dark Mode Toggle
    if st.button("Toggle Dark Mode", help="Switch between light and dark themes"):
        st.session_state.dark_mode = not st.session_state.dark_mode
        st.markdown(f"<script>toggleDarkMode();</script>", unsafe_allow_html=True)

    if st.session_state.is_author:
        st.subheader("Manage Folders & Images", help="Manage gallery content")
        
        # Add Folder
        with st.form(key="add_folder_form"):
            new_folder = st.text_input("Folder Name (e.g., 'newfolder')", help="Use lowercase alphanumeric or underscores")
            new_name = st.text_input("Person Name")
            new_age = st.number_input("Age", min_value=1, max_value=150, step=1)
            new_profession = st.text_input("Profession")
            new_category = st.selectbox("Category", ["Artists", "Engineers", "Teachers"], index=0)
            if st.form_submit_button("Add Folder"):
                if new_folder and new_name and new_profession and new_category:
                    if DatabaseManager.add_folder(new_folder.lower(), new_name, new_age, new_profession, new_category):
                        st.success(f"Folder '{new_folder}' added successfully!")
                        st.rerun()
                    else:
                        st.error("Failed to add folder. Check input or try a different folder name.")
                else:
                    st.error("Please fill in all fields.")

        # Edit Folder Name
        with st.expander("Edit Candidate Name"):
            data = DatabaseManager.load_folders()
            folder_choice_name = st.selectbox("Select Folder to Edit Name", [item["folder"] for item in data], key="edit_name_folder")
            current_name = next(item["name"] for item in data if item["folder"] == folder_choice_name)
            with st.form(key="edit_name_form"):
                new_name = st.text_input("New Name", value=current_name, help="Enter the new name for the candidate")
                if st.form_submit_button("Update Name"):
                    if new_name:
                        if DatabaseManager.update_folder_name(folder_choice_name, new_name):
                            st.success(f"Name for '{folder_choice_name}' updated to '{new_name}'!")
                            st.rerun()
                        else:
                            st.error("Failed to update name.")
                    else:
                        st.error("Please enter a valid name.")

        # Enhanced Upload Images with Before-and-After
        with st.expander("Upload Images"):
            folder_choice = st.selectbox("Select Folder", [item["folder"] for item in data], key="upload_folder")
            download_allowed = st.checkbox("Allow Downloads for New Images", value=True)
            uploaded_files = st.file_uploader(
                "Upload Images", accept_multiple_files=True, type=['jpg', 'jpeg', 'png'], key="upload_files",
                help=f"Upload multiple images (JPG, JPEG, PNG). Max {MAX_FILE_SIZE_MB}MB per file."
            )

            if uploaded_files:
                valid_files = [f for f in uploaded_files if validate_file(f)]
                if len(valid_files) != len(uploaded_files):
                    st.warning("Some files were invalid or corrupted and skipped.")
                if valid_files:
                    st.write("**Preview and Edit Uploaded Images**")
                    edited_data_list = []
                    cols = st.columns(2)  # Two-column grid for previews
                    for i, file in enumerate(valid_files):
                        with cols[i % 2]:
                            st.markdown(f"<div class='preview-container'>", unsafe_allow_html=True)
                            st.write(f"**{file.name}**")
                            file_data = file.read()
                            file.seek(0)  # Reset file pointer
                            try:
                                img = Image.open(io.BytesIO(file_data))
                                file_size_mb = file.size / (1024 * 1024)
                                st.write(f"Size: {file_size_mb:.2f} MB, Dimensions: {img.width}x{img.height}")
                                base64_image = image_to_base64(file_data)
                                canvas_width = min(img.width, 300)  # Smaller canvas for previews
                                canvas_height = int(canvas_width * (img.height / img.width))
                                image_id = f"upload_crop_canvas_{i}"
                                st.markdown(
                                    f"""
                                    <div class="canvas-container">
                                        <canvas id="{image_id}" width="{canvas_width}" height="{canvas_height}" aria-label="Click and drag to crop preview image {i+1}"></canvas>
                                        <input type="hidden" id="upload_crop_coords_{i}" name="upload_crop_coords_{i}">
                                    </div>
                                    <script>
                                        const uploadImg{i} = new Image();
                                        uploadImg{i}.src = "data:image/png;base64,{base64_image}";
                                        uploadImg{i}.onload = function() {{
                                            const canvas = document.getElementById('{image_id}');
                                            const ctx = canvas.getContext('2d');
                                            ctx.drawImage(uploadImg{i}, 0, 0, {canvas_width}, {canvas_height});
                                            initCropCanvas('{image_id}', {canvas_width}, {canvas_height}, true, {i});
                                        }};
                                    </script>
                                    """,
                                    unsafe_allow_html=True
                                )

                                # Before-and-After Comparison
                                st.write("**Before and After**")
                                edited_data = file_data
                                before_img = Image.open(io.BytesIO(file_data))
                                before_base64 = image_to_base64(file_data)
                                after_img = before_img.copy()
                                after_data = file_data

                                # Manipulation options
                                rotate_angle = st.slider("Rotate (degrees)", -180, 180, 0, key=f"upload_rotate_{i}")
                                brightness = st.slider("Brightness", 0.0, 2.0, 1.0, step=0.1, key=f"upload_brightness_{i}")
                                contrast = st.slider("Contrast", 0.0, 2.0, 1.0, step=0.1, key=f"upload_contrast_{i}")
                                sharpness = st.slider("Sharpness", 0.0, 2.0, 1.0, step=0.1, key=f"upload_sharpness_{i}")
                                grayscale = st.checkbox("Convert to Grayscale", key=f"upload_grayscale_{i}")

                                # Apply edits for preview
                                crop_coords_input = st.text_input("Crop Coordinates (JSON)", key=f"upload_crop_coords_input_{i}", disabled=True)
                                if crop_coords_input:
                                    try:
                                        crop_coords = json.loads(crop_coords_input)
                                        scale_x = img.width / canvas_width
                                        scale_y = img.height / canvas_height
                                        crop_box = (
                                            int(crop_coords["left"] * scale_x),
                                            int(crop_coords["top"] * scale_y),
                                            int(crop_coords["right"] * scale_x),
                                            int(crop_coords["bottom"] * scale_y)
                                        )
                                        if crop_box[0] < crop_box[2] and crop_box[1] < crop_box[3]:
                                            after_data = ImageProcessor.crop_image(edited_data, crop_box)
                                            if after_data:
                                                after_img = Image.open(io.BytesIO(after_data))
                                    except json.JSONDecodeError:
                                        st.error("Invalid crop coordinates for this preview")
                                if rotate_angle != 0:
                                    after_data = ImageProcessor.rotate_image(after_data, rotate_angle)
                                    if after_data:
                                        after_img = Image.open(io.BytesIO(after_data))
                                if brightness != 1.0:
                                    after_data = ImageProcessor.adjust_brightness(after_data, brightness)
                                    if after_data:
                                        after_img = Image.open(io.BytesIO(after_data))
                                if contrast != 1.0:
                                    after_data = ImageProcessor.adjust_contrast(after_data, contrast)
                                    if after_data:
                                        after_img = Image.open(io.BytesIO(after_data))
                                if sharpness != 1.0:
                                    after_data = ImageProcessor.adjust_sharpness(after_data, sharpness)
                                    if after_data:
                                        after_img = Image.open(io.BytesIO(after_data))
                                if grayscale:
                                    after_data = ImageProcessor.convert_to_grayscale(after_data)
                                    if after_data:
                                        after_img = Image.open(io.BytesIO(after_data))

                                # Display Before-and-After
                                with st.container():
                                    cols = st.columns(2)
                                    with cols[0]:
                                        st.image(before_img, caption="Before", use_container_width=True, clamp=True)
                                    with cols[1]:
                                        st.image(after_img, caption="After", use_container_width=True, clamp=True)

                                # Reset Edits Button
                                if st.button("Reset Edits", key=f"reset_upload_{i}", help="Revert to original image"):
                                    st.session_state.upload_crop_coords[f"upload_crop_coords_input_{i}"] = ""
                                    st.rerun()

                                edited_data_list.append(after_data)
                                st.markdown("</div>", unsafe_allow_html=True)
                            except Exception as e:
                                st.error(f"Error processing {file.name}: {str(e)}")
                                logger.error(f"Error processing {file.name}: {str(e)}")

                    if st.button("Upload Edited Images", help="Save all edited images to the database"):
                        with st.spinner("Uploading images..."):
                            progress_bar = st.progress(0)
                            for j in range(len(edited_data_list)):
                                progress_bar.progress((j + 1) / len(edited_data_list))
                            DatabaseManager.load_images_to_db(edited_data_list, folder_choice, download_allowed)
                        st.success(f"{len(edited_data_list)} image(s) uploaded to '{folder_choice}'!")
                        st.session_state.upload_previews = []
                        st.session_state.upload_crop_coords = {}
                        st.rerun()

        # Image Swap
        with st.expander("Image Swap"):
            folder_choice_swap = st.selectbox("Select Folder for Image Swap", [item["folder"] for item in data], key="swap_folder")
            images = DatabaseManager.get_images(folder_choice_swap)
            if images:
                image_choice = st.selectbox("Select Image to Swap", [img["name"] for img in images], key="swap_image")
                new_image = st.file_uploader("Upload New Image", type=['jpg', 'jpeg', 'png'], key="swap_upload")
                if st.button("Swap Image") and new_image:
                    if validate_file(new_image):
                        if DatabaseManager.swap_image(folder_choice_swap, image_choice, new_image):
                            st.success(f"Image '{image_choice}' swapped in '{folder_choice_swap}'!")
                            st.rerun()
                        else:
                            st.error("Failed to swap image.")
                    else:
                        st.error("Invalid file for swap.")

        # Download Permissions
        with st.expander("Download Permissions"):
            folder_choice_perm = st.selectbox("Select Folder for Download Settings", [item["folder"] for item in data], key=f"download_folder_{uuid.uuid4()}")
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
                    if st.form_submit_button("Apply Download Permissions"):
                        for img_dict in images:
                            if download_states[img_dict['name']] != img_dict["download"]:
                                DatabaseManager.update_download_permission(folder_choice_perm, img_dict["name"], download_states[img_dict['name']])
                        st.success("Download permissions updated!")
                        st.rerun()

# -------------------------------
# Main App UI
# -------------------------------
st.title("📸 Interactive Photo Gallery & Survey")

# Search Bar
search_query = st.text_input(
    "Search by name, folder, profession, or category",
    help="Enter keywords to filter folders",
    placeholder="Search..."
)
data = DatabaseManager.load_folders(search_query)
survey_data = DatabaseManager.load_survey_data()

# Display Rating Chart
def display_rating_chart(survey_data, folders):
    """Display a bar chart of average ratings per folder."""
    ratings = []
    folder_names = []
    for f in folders:
        if f["folder"] in survey_data and survey_data[f["folder"]]:
            avg_rating = sum(entry["rating"] for entry in survey_data[f["folder"]]) / len(survey_data[f["folder"]])
            ratings.append(avg_rating)
            folder_names.append(f["name"])
    
    if ratings:
        st.markdown("### Average Ratings per Folder")
        chart_config = {
            "type": "bar",
            "data": {
                "labels": folder_names,
                "datasets": [{
                    "label": "Average Rating",
                    "data": ratings,
                    "backgroundColor": ["#4CAF50", "#2196F3", "#FF9800", "#F44336", "#9C27B0"],
                    "borderColor": ["#388E3C", "#1976D2", "#F57C00", "#D32F2F", "#7B1FA2"],
                    "borderWidth": 1
                }]
            },
            "options": {
                "scales": {
                    "y": {"beginAtZero": True, "max": 5, "title": {"display": True, "text": "Rating (1-5)"}},
                    "x": {"title": {"display": True, "text": "Folder"}}
                }
            }
        }
        st.markdown("```chartjs\n" + json.dumps(chart_config, indent=2) + "\n```", unsafe_allow_html=True)
    else:
        st.info("No survey data available to display chart.")

display_rating_chart(survey_data, data)

categories = sorted(set(item["category"] for item in data))
tabs = st.tabs(categories)

# Grid View
if st.session_state.zoom_folder is None:
    for cat, tab in zip(categories, tabs):
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
                    cols = st.columns(4)
                    for idx, img_dict in enumerate(images):
                        with cols[idx % 4]:
                            if st.button("🔍 View", key=f"view_{f['folder']}_{idx}", help=f"View details for image {idx+1}"):
                                st.session_state.zoom_folder = f["folder"]
                                st.session_state.zoom_index = idx
                                st.rerun()
                            st.image(img_dict["thumbnail"], use_container_width=True, caption=f"Image {idx+1}")
                else:
                    st.warning(f"No images found for {f['folder']}")

                with st.expander(f"📝 Survey for {f['name']}"):
                    with st.form(key=f"survey_form_{f['folder']}"):
                        rating = st.slider("Rating (1-5)", 1, 5, 3, key=f"rating_{f['folder']}", help="Rate from 1 to 5")
                        feedback = st.text_area("Feedback", key=f"feedback_{f['folder']}", help="Provide your feedback")
                        if st.form_submit_button("Submit"):
                            timestamp = datetime.now().isoformat()
                            DatabaseManager.save_survey_data(f["folder"], rating, feedback, timestamp)
                            st.success("✅ Response recorded")
                            st.rerun()

                    if f["folder"] in survey_data and survey_data[f["folder"]]:
                        st.write("### 📊 Previous Feedback:")
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
                                        st.success("Deleted comment.")
                                        st.rerun()
                    else:
                        st.info("No feedback yet — be the first to leave a comment!")

# Zoom View
else:
    folder = st.session_state.zoom_folder
    images = DatabaseManager.get_images(folder)
    idx = st.session_state.zoom_index
    if idx >= len(images):
        idx = 0
        st.session_state.zoom_index = 0
    img_dict = images[idx]

    st.subheader(f"🔍 Viewing {folder} ({idx+1}/{len(images)})")
    
    # Click-to-Crop Canvas
    if st.session_state.is_author:
        image_id = f"crop_canvas_{folder}_{img_dict['name']}"
        base64_image = img_dict["base64"]
        max_width = 600  # Limit canvas size for performance
        img = img_dict["image"]
        aspect_ratio = img.width / img.height
        canvas_width = min(img.width, max_width)
        canvas_height = int(canvas_width / aspect_ratio)
        st.markdown(
            f"""
            <div class="canvas-container">
                <canvas id="{image_id}" width="{canvas_width}" height="{canvas_height}" aria-label="Click and drag to crop image"></canvas>
                <input type="hidden" id="crop_coords" name="crop_coords">
            </div>
            <script>
                const img = new Image();
                img.src = "data:image/png;base64,{base64_image}";
                img.onload = function() {{
                    const canvas = document.getElementById('{image_id}');
                    const ctx = canvas.getContext('2d');
                    ctx.drawImage(img, 0, 0, {canvas_width}, {canvas_height});
                    initCropCanvas('{image_id}', {canvas_width}, {canvas_height});
                }};
            </script>
            """,
            unsafe_allow_html=True
        )
    else:
        st.image(img_dict["image"], use_container_width=True)

    col1, col2, col3 = st.columns([1, 8, 1])
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
        with st.expander("Edit Image", expanded=True):
            with st.form(key=f"edit_image_form_{folder}_{img_dict['name']}"):
                # Crop Coordinates (populated by JavaScript)
                crop_coords_input = st.text_input("Crop Coordinates (JSON)", key=f"crop_coords_{folder}_{img_dict['name']}", disabled=True)
                if crop_coords_input:
                    try:
                        st.session_state.crop_coords = json.loads(crop_coords_input)
                    except json.JSONDecodeError:
                        st.session_state.crop_coords = None
                        st.error("Invalid crop coordinates")

                # Image Manipulation Options
                rotate_angle = st.slider("Rotate (degrees)", -180, 180, 0, help="Rotate the image")
                brightness = st.slider("Brightness", 0.0, 2.0, 1.0, step=0.1, help="Adjust brightness (1.0 is original)")
                contrast = st.slider("Contrast", 0.0, 2.0, 1.0, step=0.1, help="Adjust contrast (1.0 is original)")
                sharpness = st.slider("Sharpness", 0.0, 2.0, 1.0, step=0.1, help="Adjust sharpness (1.0 is original)")
                grayscale = st.checkbox("Convert to Grayscale", help="Convert image to grayscale")

                if st.form_submit_button("Apply Edits"):
                    # Save original image to history
                    image_id = DatabaseManager.get_image_id(folder, img_dict["name"])
                    if image_id:
                        DatabaseManager.save_image_history(image_id, folder, img_dict["data"])

                    edited_data = img_dict["data"]
                    if st.session_state.crop_coords:
                        # Scale coordinates back to original image size
                        scale_x = img.width / canvas_width
                        scale_y = img.height / canvas_height
                        crop_box = (
                            int(st.session_state.crop_coords["left"] * scale_x),
                            int(st.session_state.crop_coords["top"] * scale_y),
                            int(st.session_state.crop_coords["right"] * scale_x),
                            int(st.session_state.crop_coords["bottom"] * scale_y)
                        )
                        if crop_box[0] < crop_box[2] and crop_box[1] < crop_box[3]:
                            edited_data = ImageProcessor.crop_image(edited_data, crop_box)
                            st.session_state.crop_coords = None  # Reset after cropping
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
                        c = conn.cursor()
                        c.execute("UPDATE images SET image_data = ? WHERE folder = ? AND name = ?",
                                  (edited_data, folder, img_dict["name"]))
                        conn.commit()
                        conn.close()
                        st.success("Image edited successfully!")
                        logger.info(f"Applied edits to image '{img_dict['name']}' in folder '{folder}'")
                        st.rerun()
                    else:
                        st.error("Failed to edit image.")

                if st.button("Undo Last Edit", help="Revert to the previous version of the image"):
                    if DatabaseManager.undo_image_edit(folder, img_dict["name"]):
                        st.success("Image restored to previous version!")
                        st.rerun()
                    else:
                        st.error("No previous version available to undo.")

        if st.button("🗑️ Delete Image", key=f"delete_{folder}_{img_dict['name']}", help="Delete this image"):
            DatabaseManager.delete_image(folder, img_dict["name"])
            st.success("Deleted.")
            st.session_state.zoom_index = max(0, idx - 1)
            if len(DatabaseManager.get_images(folder)) == 0:
                st.session_state.zoom_folder = None
                st.session_state.zoom_index = 0
            st.rerun()

    if st.button("⬅️ Back to Grid", key=f"back_{folder}", help="Return to grid view"):
        st.session_state.zoom_folder = None
        st.session_state.zoom_index = 0
        st.session_state.crop_coords = None
        st.rerun()
