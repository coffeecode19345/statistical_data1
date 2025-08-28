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
# Helper Function for Base64 Conversion
# -------------------------------
def image_to_base64(image_data):
    """Convert image data (bytes) to base64 string."""
    return base64.b64encode(image_data).decode('utf-8')

# -------------------------------
# Database Setup
# -------------------------------
def init_db():
    conn = sqlite3.connect("gallery.db")
    c = conn.cursor()
    # Create folders table
    c.execute("""
        CREATE TABLE IF NOT EXISTS folders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            folder TEXT NOT NULL UNIQUE,
            name TEXT NOT NULL,
            age INTEGER NOT NULL,
            profession TEXT NOT NULL,
            category TEXT NOT NULL
        )
    """)
    # Create images table with corrected syntax
    c.execute("""
        CREATE TABLE IF NOT EXISTS images (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            folder TEXT NOT NULL,
            image_data BLOB NOT NULL,
            download_allowed BOOLEAN NOT NULL DEFAULT 1,
            FOREIGN KEY (folder) REFERENCES folders (folder)
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
            FOREIGN KEY (folder) REFERENCES folders (folder)
        )
    """)
    conn.commit()
    # Initialize default folders if not present
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

# -------------------------------
# Load folders from database
# -------------------------------
def load_folders():
    conn = sqlite3.connect("gallery.db")
    c = conn.cursor()
    c.execute("SELECT folder, name, age, profession, category FROM folders")
    folders = [{"folder": row[0], "name": row[1], "age": row[2], "profession": row[3], "category": row[4]}
               for row in c.fetchall()]
    conn.close()
    return folders

# -------------------------------
# Add new folder to database
# -------------------------------
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

# -------------------------------
# Load images into database with random filenames
# -------------------------------
def load_images_to_db(uploaded_files, folder, download_allowed=True):
    conn = sqlite3.connect("gallery.db")
    c = conn.cursor()
    for uploaded_file in uploaded_files:
        image_data = uploaded_file.read()
        # Generate random filename with original extension
        original_filename = uploaded_file.name
        extension = os.path.splitext(original_filename)[1].lower()
        random_filename = f"{uuid.uuid4()}{extension}"
        # Check if image already exists to avoid duplicates
        c.execute("SELECT COUNT(*) FROM images WHERE folder = ? AND name = ?", (folder, random_filename))
        if c.fetchone()[0] == 0:
            c.execute("INSERT INTO images (name, folder, image_data, download_allowed) VALUES (?, ?, ?, ?)",
                      (random_filename, folder, image_data, download_allowed))
    conn.commit()
    conn.close()

# -------------------------------
# Update download permission
# -------------------------------
def update_download_permission(folder, image_name, download_allowed):
    conn = sqlite3.connect("gallery.db")
    c = conn.cursor()
    c.execute("UPDATE images SET download_allowed = ? WHERE folder = ? AND name = ?",
              (download_allowed, folder, image_name))
    conn.commit()
    conn.close()

# -------------------------------
# Delete image from database
# -------------------------------
def delete_image(folder, image_name):
    conn = sqlite3.connect("gallery.db")
    c = conn.cursor()
    c.execute("DELETE FROM images WHERE folder = ? AND name = ?", (folder, image_name))
    conn.commit()
    conn.close()

# -------------------------------
# Load survey data from database
# -------------------------------
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

# -------------------------------
# Save survey data to database
# -------------------------------
def save_survey_data(folder, rating, feedback, timestamp):
    conn = sqlite3.connect("gallery.db")
    c = conn.cursor()
    c.execute("INSERT INTO surveys (folder, rating, feedback, timestamp) VALUES (?, ?, ?, ?)",
              (folder, rating, feedback, timestamp))
    conn.commit()
    conn.close()

# -------------------------------
# Delete survey entry from database
# -------------------------------
def delete_survey_entry(folder, timestamp):
    conn = sqlite3.connect("gallery.db")
    c = conn.cursor()
    c.execute("DELETE FROM surveys WHERE folder = ? AND timestamp = ?", (folder, timestamp))
    conn.commit()
    conn.close()

# -------------------------------
# Get images from database
# -------------------------------
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
with st.sidebar.form(key="auth_form"):
    password = st.text_input("Enter Author Password", type="password")
    if st.form_submit_button("Login"):
        # Replace with your own password or integrate with a proper auth system
        if password == "admin123":  # Hardcoded for demo; use secure auth in production
            st.session_state.is_author = True
            st.sidebar.success("Logged in as author!")
        else:
            st.sidebar.error("Incorrect password")

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

# -------------------------------
# CSS for Portfolio
# -------------------------------
st.markdown("""
    <style>
    .portfolio-container {
        width: 100%;
        max-width: 800px;
        margin: 0 auto;
    }
    .main-image-container {
        position: relative;
        width: 100%;
        max-height: 400px;
        overflow: hidden;
        border: 2px solid #333;
        border-radius: 8px;
        box-shadow: 3px 3px 8px rgba(0, 0, 0, 0.3);
        margin-bottom: 10px;
    }
    .main-image {
        width: 100%;
        max-height: 400px;
        object-fit: contain;
        cursor: pointer;
    }
    .nav-button {
        background: rgba(0, 0, 0, 0.5);
        color: white;
        border: none;
        padding: 10px;
        cursor: pointer;
        font-size: 24px;
        margin: 5px;
    }
    img {
        pointer-events: none; /* Prevent right-click and drag */
        -webkit-user-drag: none;
        user-drag: none;
        user-select: none;
    }
    </style>
""", unsafe_allow_html=True)

# -------------------------------
# App UI
# -------------------------------
st.title("📸 Photo Gallery & Survey")

data = load_folders() if 'data' not in locals() else data
survey_data = load_survey_data()
categories = sorted(set(item["category"] for item in data))
tabs = st.tabs(categories)

# -------------------------------
# Author Controls for Download Permissions
# -------------------------------
if st.session_state.is_author:
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
# Loop through categories
# -------------------------------
for category, tab in zip(categories, tabs):
    with tab:
        st.header(category)
        category_data = [item for item in data if item["category"] == category]

        for item in category_data:
            st.subheader(f"{item['name']} ({item['age']}, {item['profession']})")

            images = get_images_from_db(item["folder"])
            if images:
                # Initialize session state for current image index
                if f"current_image_{item['folder']}" not in st.session_state:
                    st.session_state[f"current_image_{item['folder']}"] = 0

                current_index = st.session_state[f"current_image_{item['folder']}"]
                if current_index >= len(images):
                    current_index = 0
                    st.session_state[f"current_image_{item['folder']}"] = 0

                # Portfolio Container
                with st.container():
                    # Main Image
                    image_name, image, image_data, download_allowed, base64_image = images[current_index]
                    mime_type, _ = mimetypes.guess_type(image_name)
                    with st.container():
                        st.image(image, use_container_width=True, caption="Click to view full size")
                        if st.button("View Full Size", key=f"zoom_{item['folder']}_{current_index}"):
                            with st.expander("Full Size Image", expanded=True):
                                st.image(image, use_container_width=False, caption="Full size view")

                    # Navigation Buttons
                    col1, col2, col3 = st.columns([1, 8, 1])
                    with col1:
                        if current_index > 0:
                            if st.button("◄", key=f"prev_{item['folder']}"):
                                st.session_state[f"current_image_{item['folder']}"] = current_index - 1
                                st.rerun()
                    with col3:
                        if current_index < len(images) - 1:
                            if st.button("►", key=f"next_{item['folder']}"):
                                st.session_state[f"current_image_{item['folder']}"] = current_index + 1
                                st.rerun()

                    # Download and Delete Buttons
                    extension = os.path.splitext(image_name)[1].lower()
                    download_filename = f"{uuid.uuid4()}{extension}"
                    if download_allowed:
                        if st.download_button(
                            label="⬇️ Download Image",
                            data=image_data,
                            file_name=download_filename,
                            mime=mime_type,
                            key=f"download_image_{item['folder']}_{image_name}"
                        ):
                            st.info(f"Downloading image as {download_filename}")
                    
                    if st.session_state.is_author:
                        if st.button("🗑️ Delete Image", key=f"delete_image_{item['folder']}_{image_name}"):
                            delete_image(item["folder"], image_name)
                            st.success(f"Image deleted from {item['folder']}")
                            if current_index >= len(images) - 1:
                                st.session_state[f"current_image_{item['folder']}"] = max(0, current_index - 1)
                            st.rerun()
            else:
                st.warning(f"No images found for {item['folder']} in database")

            # -------------------------------
            # Survey form
            # -------------------------------
            with st.expander(f"📝 Survey for {item['name']}"):
                with st.form(key=f"survey_form_{item['folder']}"):
                    rating = st.slider("Rating (1-5)", 1, 5, 3, key=f"rating_{item['folder']}")
                    feedback = st.text_area("Feedback", key=f"feedback_{item['folder']}")
                    if st.form_submit_button("Submit"):
                        timestamp = datetime.now().isoformat()
                        save_survey_data(item["folder"], rating, feedback, timestamp)
                        st.success("✅ Response recorded")
                        st.rerun()

            # -------------------------------
            # Display saved survey data
            # -------------------------------
            if item["folder"] in survey_data and survey_data[item["folder"]]:
                st.subheader(f"💬 Survey Responses for {item['name']}")
                for entry in survey_data[item["folder"]]:
                    with st.expander(f"{entry['timestamp']}"):
                        st.write(f"⭐ {entry['rating']} — {entry['feedback']}")
                        if st.button("🗑️ Delete", key=f"delete_survey_{item['folder']}_{entry['timestamp']}"):
                            delete_survey_entry(item["folder"], entry["timestamp"])
                            st.rerun()
            else:
                st.caption("No survey responses yet.")
