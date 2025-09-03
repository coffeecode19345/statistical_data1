import streamlit as st
import sqlite3
import io
from PIL import Image
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
    st_javascript = lambda x: ""

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
            image_data = uploaded_file["data"] if isinstance(uploaded_file, dict) else uploaded_file.read()
            extension = os.path.splitext(uploaded_file["file"].name)[1].lower() if isinstance(uploaded_file, dict) else os.path.splitext(uploaded_file.name)[1].lower()
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
    def save_image_history(image_id, folder, image_data):
        conn = DatabaseManager.connect()
        c = conn.cursor()
        timestamp = datetime.now().isoformat()
        c.execute("INSERT INTO image_history (image_id, folder, image_data, timestamp) VALUES (?, ?, ?, ?)",
                  (image_id, folder, image_data, timestamp))
        conn.commit()
        conn.close()

    @staticmethod
    def get_image_id(folder, image_name):
        conn = DatabaseManager.connect()
        c = conn.cursor()
        c.execute("SELECT id FROM images WHERE folder = ? AND name = ?", (folder, image_name))
        result = c.fetchone()
        conn.close()
        return result[0] if result else None

    @staticmethod
    def undo_image_edit(folder, image_name):
        conn = DatabaseManager.connect()
        try:
            c = conn.cursor()
            image_id = DatabaseManager.get_image_id(folder, image_name)
            if not image_id:
                return False
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
                return True
            return False
        finally:
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
                thumbnail = ImageProcessor.generate_thumbnail(img, size=(100, 100))
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
                st.error(f"Error loading image {name}: {str(e)}")
        conn.close()
        return images

class ImageProcessor:
    @staticmethod
    def generate_thumbnail(image, size=(100, 100)):
        img = image.copy()
        img.thumbnail(size)
        return img

    @staticmethod
    def crop_image(image_data, crop_box):
        try:
            img = Image.open(io.BytesIO(image_data)).convert("RGB")
            cropped_img = img.crop(crop_box)
            output = io.BytesIO()
            cropped_img.save(output, format="PNG")
            return output.getvalue()
        except Exception as e:
            st.error("Failed to crop image. Ensure the crop area is valid.")
            return None

    @staticmethod
    def rotate_image(image_data, degrees):
        try:
            img = Image.open(io.BytesIO(image_data)).convert("RGB")
            rotated_img = img.rotate(degrees, expand=True)
            output = io.BytesIO()
            rotated_img.save(output, format="PNG")
            return output.getvalue()
        except Exception as e:
            st.error("Failed to rotate image.")
            return None

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
    st.session_state.crop_coords = {}
if "upload_previews" not in st.session_state:
    st.session_state.upload_previews = []
if "dark_mode" not in st.session_state:
    st.session_state.dark_mode = False
if "search_query" not in st.session_state:
    st.session_state.search_query = ""

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

try:
    restore_is_author = st_javascript("document.getElementById('restore_is_author') ? document.getElementById('restore_is_author').value : ''")
    if restore_is_author == 'true' and not st.session_state.is_author:
        st.session_state.is_author = True
        logger.info("Restored admin login state")
except Exception as e:
    logger.warning(f"Failed to execute st_javascript: {str(e)}")

# -------------------------------
# CSS Styling
# -------------------------------
st.markdown("""
<style>
body {
    font-family: 'Arial', sans-serif;
    background: var(--bg-color, #f9f9f9);
    color: var(--text-color, #333);
}
.header {
    background: var(--header-bg, #ffffff);
    padding: 1rem;
    box-shadow: 0 2px 4px rgba(0,0,0,0.1);
    display: flex;
    justify-content: space-between;
    align-items: center;
}
.folder-card {
    background: var(--card-bg, #ffffff);
    border-radius: 8px;
    padding: 15px;
    margin-bottom: 20px;
    box-shadow: 0 4px 8px rgba(0,0,0,0.1);
}
.folder-header {
    font-size: 1.5em;
    font-weight: bold;
    color: var(--text-color, #333);
    margin-bottom: 10px;
}
.image-grid {
    display: flex;
    flex-wrap: wrap;
    gap: 10px;
}
.image-grid img {
    border-radius: 4px;
    max-width: 100px;
    object-fit: cover;
}
.stButton>button {
    border-radius: 5px;
    padding: 0.5rem 1rem;
}
.canvas-container {
    position: relative;
    margin: 0.5rem 0;
}
#cropCanvas {
    border: 2px solid #007bff;
    border-radius: 5px;
}
:root {
    --bg-color: #f9f9f9;
    --card-bg: #ffffff;
    --text-color: #333;
    --header-bg: #ffffff;
}
.dark-mode {
    --bg-color: #1a1a1a;
    --card-bg: #2d2d2d;
    --text-color: #e0e0e0;
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

if st.session_state.dark_mode:
    st.markdown("""
    <style>
    body {
        --bg-color: #1a1a1a;
        --card-bg: #2d2d2d;
        --text-color: #e0e0e0;
        --header-bg: #2d2d2d;
    }
    </style>
    """, unsafe_allow_html=True)

# -------------------------------
# Header Navigation
# -------------------------------
col1, col2, col3 = st.columns([2, 1, 1])
with col1:
    st.title("📸 Photo Gallery")
with col2:
    search_query = st.text_input("Search folders...", value=st.session_state.search_query, key="search_input", placeholder="Name, profession, or category")
with col3:
    if st.button("🌙 Dark Mode"):
        st.session_state.dark_mode = not st.session_state.dark_mode
        st.rerun()

# -------------------------------
# Sidebar: Admin Controls
# -------------------------------
with st.sidebar:
    st.subheader("🛠️ Admin Tools")
    if not st.session_state.is_author:
        with st.form(key="login_form"):
            pwd = st.text_input("Admin Password", type="password", placeholder="Enter password")
            if st.form_submit_button("🔐 Login"):
                if pwd == ADMIN_PASSWORD:
                    st.session_state.is_author = True
                    st.balloons()
                    st.success("Logged in!")
                    st.markdown("<script>setCookie('is_author', 'true', 1);</script>", unsafe_allow_html=True)
                    st.rerun()
                else:
                    st.error("Wrong password.")
    else:
        if st.button("🔓 Logout"):
            st.session_state.is_author = False
            st.success("Logged out")
            st.markdown("<script>setCookie('is_author', 'false', 1);</script>", unsafe_allow_html=True)
            st.rerun()

        with st.expander("📁 Add Folder"):
            with st.form(key="add_folder_form"):
                new_folder = st.text_input("Folder Name", placeholder="e.g., newfolder")
                new_name = st.text_input("Person Name", placeholder="e.g., Jane Smith")
                new_age = st.number_input("Age", min_value=1, max_value=150, value=30)
                new_profession = st.text_input("Profession", placeholder="e.g., Photographer")
                new_category = st.selectbox("Category", ["Artists", "Engineers", "Teachers"])
                if st.form_submit_button("➕ Add"):
                    if new_folder and new_name and new_profession and new_category:
                        if DatabaseManager.add_folder(new_folder.lower(), new_name, new_age, new_profession, new_category):
                            st.success(f"Folder '{new_folder}' created!")
                            st.rerun()
                    else:
                        st.error("Fill in all fields.")

        with st.expander("🖼️ Upload Photos"):
            data = DatabaseManager.load_folders()
            with st.form(key="upload_images_form"):
                folder_choice = st.selectbox("Select Folder", [item["folder"] for item in data], key="upload_folder")
                download_allowed = st.checkbox("Allow Downloads", value=True)
                uploaded_files = st.file_uploader("Choose Photos", accept_multiple_files=True, type=['jpg', 'png'], key="upload_files")
                col1, col2 = st.columns(2)
                with col1:
                    if st.form_submit_button("✅ Upload"):
                        if uploaded_files:
                            valid_files = [f for f in uploaded_files if validate_file(f)]
                            if valid_files:
                                DatabaseManager.load_images_to_db(valid_files, folder_choice, download_allowed)
                                st.success(f"{len(valid_files)} photo(s) uploaded!")
                                st.balloons()
                                st.rerun()
                            else:
                                st.error("No valid photos. Use JPG/PNG under 5MB.")
                        else:
                            st.error("Select at least one photo.")
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
                                st.rerun()
                        else:
                            st.error("Select at least one photo.")

# -------------------------------
# Main App UI
# -------------------------------
if search_query != st.session_state.search_query:
    st.session_state.search_query = search_query
    st.rerun()

data = DatabaseManager.load_folders(st.session_state.search_query)
survey_data = DatabaseManager.load_survey_data()
categories = sorted(set(item["category"] for item in data))
tab_names = ["Home"] + categories + ["Help"]
tabs = st.tabs(tab_names)

# Home Tab
with tabs[0]:
    st.markdown("## Welcome to the Photo Gallery!")
    st.write("Browse photos by category, leave feedback, or log in to manage content.")
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
        st.info("No ratings yet. Add feedback in the category tabs!")

# Category Tabs
for cat, tab in zip(categories, tabs[1:-1]):
    with tab:
        if st.session_state.upload_step == 1 and st.session_state.is_author:
            st.subheader(f"Editing Photos for {st.session_state.form_upload_folder}")
            valid_files = st.session_state.upload_previews
            st.markdown("### Select Photo")
            cols = st.columns(5)
            selected_index = st.session_state.get("selected_image_index", 0)
            for idx, file_dict in enumerate(valid_files):
                with cols[idx % 5]:
                    thumbnail = ImageProcessor.generate_thumbnail(Image.open(io.BytesIO(file_dict["data"])))
                    base64_thumb = image_to_base64(thumbnail_to_bytes(thumbnail))
                    if st.image(f"data:image/png;base64,{base64_thumb}", caption=file_dict["file"].name[:10], use_column_width=True):
                        st.session_state.selected_image_index = idx
                        st.rerun()

            if valid_files:
                file_dict = valid_files[selected_index]
                st.markdown(f"<div class='edit-container'>", unsafe_allow_html=True)
                with st.container():
                    st.markdown(f"### Editing: {file_dict['file'].name}")
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
                        apply_crop = st.checkbox("Apply Crop")
                        rotate_angle = st.slider("Rotate (degrees)", -180, 180, 0)
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
                            if st.form_submit_button("↩️ Undo"):
                                if st.session_state.edit_history[file_dict["file"].name]:
                                    valid_files[selected_index]["data"] = st.session_state.edit_history[file_dict["file"].name].pop()
                                    st.session_state.upload_previews = valid_files
                                    st.success("Edit undone!")
                                    st.rerun()

                if st.button("🔄 Reset"):
                    valid_files[selected_index]["data"] = file_dict["original_data"]
                    st.session_state.upload_previews = valid_files
                    st.session_state.edit_history[file_dict["file"].name] = []
                    st.session_state.crop_coords[file_dict["file"].name] = {}
                    st.success("Reset to original!")
                    st.rerun()

                st.markdown("</div>", unsafe_allow_html=True)
                col1, col2 = st.columns(2)
                with col1:
                    if st.button("⬅️ Back"):
                        st.session_state.upload_step = 0
                        st.session_state.upload_previews = []
                        st.session_state.form_upload_folder = None
                        st.session_state.form_download_allowed = None
                        st.session_state.edit_history = {}
                        st.session_state.crop_coords = {}
                        st.rerun()
                with col2:
                    if st.button("✅ Save All"):
                        DatabaseManager.load_images_to_db(valid_files, st.session_state.form_upload_folder, st.session_state.form_download_allowed)
                        st.success(f"{len(valid_files)} photo(s) saved!")
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

            st.subheader(f"🔍 Viewing {folder} ({idx+1}/{len(images)})")
            st.image(img_dict["image"], use_container_width=True)

            col1, col2, col3 = st.columns([1, 8, 1])
            with col1:
                if idx > 0 and st.button("◄ Previous"):
                    st.session_state.zoom_index -= 1
                    st.rerun()
            with col3:
                if idx < len(images) - 1 and st.button("Next ►"):
                    st.session_state.zoom_index += 1
                    st.rerun()

            if img_dict["download"]:
                mime, _ = mimetypes.guess_type(img_dict["name"])
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
                        apply_crop = st.checkbox("Apply Crop")
                        rotate_angle = st.slider("Rotate (degrees)", -180, 180, 0)
                        col1, col2 = st.columns(2)
                        with col1:
                            if st.form_submit_button("💾 Save"):
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
                                    c = conn.cursor()
                                    c.execute("UPDATE images SET image_data = ? WHERE folder = ? AND name = ?",
                                              (edited_data, folder, img_dict["name"]))
                                    conn.commit()
                                    conn.close()
                                    st.success("Photo edited!")
                                    st.balloons()
                                    st.rerun()
                        with col2:
                            if st.form_submit_button("↩️ Undo"):
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
            cat_folders = [f for f in data if f["category"] == cat]
            for f in cat_folders:
                st.markdown(
                    f'<div class="folder-card"><div class="folder-header">{f["name"]} ({f["age"]}, {f["profession"]})</div>',
                    unsafe_allow_html=True
                )
                images = DatabaseManager.get_images(f["folder"])
                if images:
                    st.markdown('<div class="image-grid">', unsafe_allow_html=True)
                    for idx, img_dict in enumerate(images):
                        if st.button(f"🔍 View {idx+1}", key=f"view_{f['folder']}_{idx}"):
                            st.session_state.zoom_folder = f["folder"]
                            st.session_state.zoom_index = idx
                            st.rerun()
                        st.image(thumbnail_to_bytes(img_dict["thumbnail"]), use_column_width=True, caption=f"Photo {idx+1}")
                    st.markdown('</div>', unsafe_allow_html=True)
                else:
                    st.warning(f"No photos in {f['name']}")

                with st.expander(f"📝 Feedback for {f['name']}"):
                    with st.form(key=f"survey_form_{f['folder']}"):
                        rating = st.slider("Rating (1-5)", 1, 5, 3, key=f"rating_{f['folder']}")
                        feedback = st.text_area("Comments", key=f"feedback_{f['folder']}", placeholder="Your thoughts...")
                        if st.form_submit_button("✅ Submit"):
                            timestamp = datetime.now().isoformat()
                            DatabaseManager.save_survey_data(f["folder"], rating, feedback, timestamp)
                            st.success("Feedback submitted!")
                            st.rerun()

                    if f["folder"] in survey_data and survey_data[f["folder"]]:
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
                                        st.rerun()

# Help Tab
with tabs[-1]:
    st.markdown("## 📖 Help & Guide")
    st.markdown("""
    ### How to Use
    - **Browse**: Click category tabs to view folders and photos.
    - **Search**: Use the search bar to find folders by name or profession.
    - **View**: Click 🔍 to see a larger photo with navigation.
    - **Feedback**: Rate (1-5 stars) and add comments in each folder.

    ### Admin Guide
    1. **Log In**: Enter the admin password in the sidebar.
    2. **Add Folders**: Fill in name, age, profession, and category.
    3. **Upload Photos**:
       - Select a folder and upload JPG/PNG photos (max 5MB).
       - Click "Upload" to save directly or "Edit & Upload" to crop/rotate.
    4. **Edit Photos**:
       - Select a photo, drag to crop, or rotate.
       - Save edits or undo/reset.
    5. **Manage**: Control download permissions or delete photos/feedback.

    ### Tips
    - Use thumbnails for faster browsing.
    - Ensure crop areas are within the photo.
    - Toggle dark mode for better visibility.
    """)
