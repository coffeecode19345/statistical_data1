import streamlit as st
import sqlite3
import os
from datetime import datetime
import io
from PIL import Image
import uuid
import mimetypes
import base64

# -------------------------------
# Helper Functions
# -------------------------------
def image_to_base64(image_data):
    """Convert image data (bytes) to base64 string."""
    return base64.b64encode(image_data).decode('utf-8') if isinstance(image_data, bytes) else image_data.encode('utf-8')

def init_db():
    conn = sqlite3.connect("gallery.db")
    c = conn.cursor()
    # Create folders table
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
    # Create images table
    c.execute("""
        CREATE TABLE IF NOT EXISTS images (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            folder TEXT NOT NULL,
            image_data BLOB NOT NULL,
            download_allowed BOOLEAN NOT NULL DEFAULT 1,
            FOREIGN KEY (folder) REFERENCES folders(folder)
        )
    """)
    # Create surveys table
    c.execute("""
        CREATE TABLE IF NOT EXISTS surveys (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            folder TEXT NOT NULL,
            rating INTEGER NOT NULL,
            feedback TEXT,
            timestamp TEXT NOT NULL,
            FOREIGN KEY (folder) REFERENCES folders(folder)
        )
    """)
    # Initialize default folders
    default_folders = [
        {"name": "Xiaojing", "age": 26, "profession": "Graphic Designer", "category": "Artists", "folder": "xiaojing"},
        {"name": "Yuena", "age": 29, "profession": "Painter", "category": "Artists", "folder": "yuena"},
        {"name": "Chunyang", "age": 15, "profession": "Software Developer", "category": "Engineers", "folder": "chunyang"},
        {"name": "Yu", "age": 47, "profession": "Data Scientist", "category": "Engineers", "folder": "yu"},
        {"name": "Yijie", "age": 30, "profession": "Literature Teacher", "category": "Teachers", "folder": "yijie"},
        {"name": "Haoran", "age": 34, "profession": "History Teacher", "category": "Teachers", "folder": "haoran"},
        {"name": "Yajie", "age": 27, "profession": "Musician", "category": "Artists", "folder": "yajie"},
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

def load_folders():
    conn = sqlite3.connect("gallery.db")
    c = conn.cursor()
    c.execute("SELECT folder, name, age, profession, category FROM folders")
    folders = [{"folder": r[0], "name": r[1], "age": r[2], "profession": r[3], "category": r[4]} for r in c.fetchall()]
    conn.close()
    return folders

def add_folder(folder, name, age, profession, category):
    try:
        conn = sqlite3.connect("gallery.db")
        c = conn.cursor()
        c.execute("""
            INSERT INTO folders (folder, name, age, profession, category)
            VALUES (?, ?, ?, ?, ?)
        """, (folder, name, age, profession, category))
        conn.commit()
        conn.close()
        return True
    except sqlite3.IntegrityError:
        return False  # Folder already exists
    except Exception as e:
        st.error(f"Error adding folder: {str(e)}")
        return False

def load_images_to_db(uploaded_files, folder, download_allowed=True):
    conn = sqlite3.connect("gallery.db")
    c = conn.cursor()
    for uploaded_file in uploaded_files:
        image_data = uploaded_file.read()
        original_filename = uploaded_file.name
        extension = os.path.splitext(original_filename)[1].lower()
        random_filename = f"{uuid.uuid4()}{extension}"
        c.execute("SELECT COUNT(*) FROM images WHERE folder = ? AND name = ?", (folder, random_filename))
        if c.fetchone()[0] == 0:
            c.execute("INSERT INTO images (name, folder, image_data, download_allowed) VALUES (?, ?, ?, ?)",
                      (random_filename, folder, image_data, download_allowed))
    conn.commit()
    conn.close()

def update_download_permission(folder, image_name, download_allowed):
    conn = sqlite3.connect("gallery.db")
    c = conn.cursor()
    c.execute("UPDATE images SET download_allowed = ? WHERE folder = ? AND name = ?",
              (download_allowed, folder, image_name))
    conn.commit()
    conn.close()

def delete_image(folder, image_name):
    conn = sqlite3.connect("gallery.db")
    c = conn.cursor()
    c.execute("DELETE FROM images WHERE folder = ? AND name = ?", (folder, image_name))
    conn.commit()
    conn.close()

def load_survey_data():
    conn = sqlite3.connect("gallery.db")
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

def save_survey_data(folder, rating, feedback, timestamp):
    conn = sqlite3.connect("gallery.db")
    c = conn.cursor()
    c.execute("INSERT INTO surveys (folder, rating, feedback, timestamp) VALUES (?, ?, ?, ?)",
              (folder, rating, feedback, timestamp))
    conn.commit()
    conn.close()

def delete_survey_entry(folder, timestamp):
    conn = sqlite3.connect("gallery.db")
    c = conn.cursor()
    c.execute("DELETE FROM surveys WHERE folder = ? AND timestamp = ?", (folder, timestamp))
    conn.commit()
    conn.close()

def get_images_from_db(folder):
    conn = sqlite3.connect("gallery.db")
    c = conn.cursor()
    c.execute("SELECT name, image_data, download_allowed FROM images WHERE folder = ?", (folder,))
    images = []
    for row in c.fetchall():
        name, image_data, download_allowed = row
        try:
            image = Image.open(io.BytesIO(image_data))
            base64_image = image_to_base64(image_data)
            images.append((name, image, image_data, download_allowed, base64_image))
        except Exception as e:
            st.error(f"Error loading image {name}: {str(e)}")
    conn.close()
    return images

# -------------------------------
# Initialize database
# -------------------------------
init_db()

# -------------------------------
# Author Authentication
# -------------------------------
if "is_author" not in st.session_state:
    st.session_state.is_author = False

st.sidebar.title("Author Login")
with st.sidebar.form(key="login_form"):
    pwd = st.text_input("Password", type="password")
    if st.form_submit_button("Login"):
        if pwd == "admin123":  # Hardcoded for demo; use secure auth in production
            st.session_state.is_author = True
            st.sidebar.success("Logged in as author!")
        else:
            st.sidebar.error("Wrong password")

if st.session_state.is_author:
    if st.sidebar.button("Logout"):
        st.session_state.is_author = False
        st.rerun()

# -------------------------------
# Sidebar for Folder Creation and Image Upload
# -------------------------------
if st.session_state.is_author:
    st.sidebar.title("Manage Folders and Images")
    st.sidebar.subheader("Create New Folder")
    with st.sidebar.form(key="add_folder_form"):
        new_folder = st.text_input("Folder Name (e.g., 'newfolder')")
        new_name = st.text_input("Person Name")
        new_age = st.number_input("Age", min_value=1, max_value=150, step=1)
        new_profession = st.text_input("Profession")
        new_category = st.selectbox("Category", ["Artists", "Engineers", "Teachers"])
        if st.form_submit_button("Add Folder"):
            if new_folder and new_name and new_profession and new_category:
                if add_folder(new_folder.lower(), new_name, new_age, new_profession, new_category):
                    st.sidebar.success(f"Folder '{new_folder}' added successfully!")
                    st.rerun()
                else:
                    st.sidebar.error(f"Folder '{new_folder}' already exists or invalid input.")
            else:
                st.sidebar.error("Please fill in all fields.")

    st.sidebar.subheader("Upload Images")
    data = load_folders()
    folder_choice = st.sidebar.selectbox("Select Folder", [item["folder"] for item in data])
    download_allowed = st.sidebar.checkbox("Allow Downloads for New Images", value=True)
    uploaded_files = st.sidebar.file_uploader("Upload Images", accept_multiple_files=True, type=['jpg', 'jpeg', 'png'])
    if uploaded_files and folder_choice:
        load_images_to_db(uploaded_files, folder_choice, download_allowed)
        st.sidebar.success(f"Images uploaded to {folder_choice} folder in database!")
        st.rerun()

    st.sidebar.subheader("Manage Download Permissions")
    folder_choice = st.sidebar.selectbox("Select Folder for Download Settings", [item["folder"] for item in data], key="download_folder")
    images = get_images_from_db(folder_choice)
    if images:
        st.sidebar.write("Toggle Download Permissions:")
        for image_name, _, _, download_allowed, _ in images:
            toggle_key = f"download_toggle_{folder_choice}_{image_name}"
            current_state = st.sidebar.checkbox(f"Allow download for {image_name[:8]}...{image_name[-4:]}", 
                                              value=download_allowed, 
                                              key=toggle_key)
            if current_state != download_allowed:
                update_download_permission(folder_choice, image_name, current_state)
                st.sidebar.success(f"Download permission updated for {image_name[:8]}...{image_name[-4:]}")
                st.rerun()

# -------------------------------
# CSS for Improved GUI
# -------------------------------
st.markdown("""
    <style>
    .portfolio-container {
        width: 100%;
        max-width: 1200px;
        margin: 0 auto;
        padding: 20px;
    }
    .folder-card {
        background: #f9f9f9;
        border-radius: 8px;
        padding: 15px;
        margin-bottom: 20px;
        box-shadow: 0 4px 8px rgba(0, 0, 0, 0.1);
        transition: transform 0.2s, box-shadow 0.2s;
    }
    .folder-card:hover {
        transform: translateY(-5px);
        box-shadow: 0 6px 12px rgba(0, 0, 0, 0.15);
    }
    .folder-header {
        font-size: 1.5em;
        color: #333;
        margin-bottom: 10px;
    }
    .image-grid {
        display: flex;
        flex-wrap: wrap;
        gap: 10px;
    }
    .grid-image {
        width: 100%;
        max-height: 150px;
        object-fit: cover;
        border-radius: 4px;
        border: 2px solid #ddd;
        box-shadow: 2px 2px 4px rgba(0, 0, 0, 0.1);
        cursor: pointer;
        transition: border-color 0.2s;
    }
    .grid-image:hover {
        border-color: #333;
    }
    .slider-container {
        width: 100%;
        max-width: 800px;
        margin: 20px auto;
        padding: 10px;
        border-radius: 8px;
        background: #fff;
        box-shadow: 0 4px 8px rgba(0, 0, 0, 0.1);
    }
    .slider-image {
        width: 100%;
        max-height: 500px;
        object-fit: contain;
        border-radius: 4px;
        border: 2px solid #333;
    }
    .nav-button {
        background: rgba(0, 0, 0, 0.5);
        color: white;
        border: none;
        padding: 10px;
        cursor: pointer;
        font-size: 24px;
        margin: 5px;
        border-radius: 4px;
    }
    .nav-button:hover {
        background: rgba(0, 0, 0, 0.7);
    }
    img {
        pointer-events: none; /* Prevent right-click and drag */
        -webkit-user-drag: none;
        user-drag: none;
        user-select: none;
    }
    body {
        -webkit-user-select: none;
        -ms-user-select: none;
        user-select: none;
    }
    </style>
""", unsafe_allow_html=True)

# -------------------------------
# App UI
# -------------------------------
st.title("📸 Interactive Photo Gallery & Survey")

data = load_folders()
survey_data = load_survey_data()
categories = sorted(set(item["category"] for item in data))
tabs = st.tabs(categories)

# -------------------------------
# Display folders by category
# -------------------------------
for category, tab in zip(categories, tabs):
    with tab:
        st.header(category)
        category_data = [item for item in data if item["category"] == category]

        for item in category_data:
            with st.container():
                st.markdown(f'<div class="folder-card"><div class="folder-header">{item["name"]} ({item["age"]}, {item["profession"]})</div>', unsafe_allow_html=True)
                images = get_images_from_db(item["folder"])
                if not images:
                    st.warning(f"No images found for {item['folder']} in database")
                    st.markdown('</div>', unsafe_allow_html=True)
                    continue

                # Display images as clickable grid
                cols = st.columns(4)  # 4 images per row
                for idx, (name, img, img_data, download_allowed, base64_image) in enumerate(images):
                    with cols[idx % 4]:
                        st.markdown('<div class="image-grid">', unsafe_allow_html=True)
                        if st.button("", key=f"zoom_{item['folder']}_{idx}", help=f"View {name[:8]}...{name[-4:]}"):
                            st.session_state.zoom_folder = item["folder"]
                            st.session_state.zoom_index = idx
                        st.image(img, use_container_width=True, clamp=True)
                        st.markdown('</div>', unsafe_allow_html=True)

                # Survey form
                with st.expander(f"📝 Survey for {item['name']}"):
                    with st.form(key=f"survey_form_{item['folder']}"):
                        rating = st.slider("Rating (1-5)", 1, 5, 3, key=f"rating_{item['folder']}")
                        feedback = st.text_area("Feedback", key=f"feedback_{item['folder']}")
                        if st.form_submit_button("Submit"):
                            timestamp = datetime.now().isoformat()
                            save_survey_data(item["folder"], rating, feedback, timestamp)
                            st.success("✅ Response recorded")
                            st.rerun()

                # Display survey responses
                if item["folder"] in survey_data and survey_data[item["folder"]]:
                    st.subheader(f"💬 Survey Responses for {item['name']}")
                    for entry in survey_data[item["folder"]]:
                        with st.expander(f"{entry['timestamp']}"):
                            st.write(f"⭐ {entry['rating']} — {entry['feedback']}")
                            if st.session_state.is_author:
                                if st.button("🗑️ Delete", key=f"delete_survey_{item['folder']}_{entry['timestamp']}"):
                                    delete_survey_entry(item["folder"], entry["timestamp"])
                                    st.rerun()
                else:
                    st.caption("No survey responses yet.")

                st.markdown('</div>', unsafe_allow_html=True)

# -------------------------------
# Zoomed slider view
# -------------------------------
if "zoom_folder" in st.session_state:
    folder = st.session_state.zoom_folder
    images = get_images_from_db(folder)
    idx = st.session_state.get("zoom_index", 0)
    if idx >= len(images):
        idx = 0
        st.session_state.zoom_index = 0

    with st.container():
        st.markdown(f'<div class="slider-container">', unsafe_allow_html=True)
        st.subheader(f"🔍 Viewing {folder} ({idx+1}/{len(images)})")
        name, img, img_data, download_allowed, base64_image = images[idx]
        st.image(img, use_container_width=True, clamp=True)

        col1, col2, col3 = st.columns([1, 8, 1])
        with col1:
            if idx > 0:
                if st.button("◄ Previous", key=f"prev_{folder}"):
                    st.session_state.zoom_index = idx - 1
                    st.rerun()
        with col3:
            if idx < len(images) - 1:
                if st.button("Next ►", key=f"next_{folder}"):
                    st.session_state.zoom_index = idx + 1
                    st.rerun()

        mime_type, _ = mimetypes.guess_type(name)
        if download_allowed:
            st.download_button(
                label="⬇️ Download",
                data=img_data,
                file_name=f"{uuid.uuid4()}{os.path.splitext(name)[1].lower()}",
                mime=mime_type,
                key=f"download_{folder}_{name}"
            )
        if st.session_state.is_author:
            if st.button("🗑️ Delete Image", key=f"delete_{folder}_{name}"):
                delete_image(folder, name)
                st.success("Image deleted.")
                st.session_state.zoom_index = max(0, idx - 1)
                if len(get_images_from_db(folder)) == 0:
                    del st.session_state.zoom_folder
                    del st.session_state.zoom_index
                st.rerun()

        st.markdown('</div>', unsafe_allow_html=True)
