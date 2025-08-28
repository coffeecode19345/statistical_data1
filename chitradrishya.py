import streamlit as st
import sqlite3
import io
from PIL import Image
import uuid
import base64
import mimetypes
from datetime import datetime

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
    # Folders table
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
    # Images table
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
    # Surveys table
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

    # Default folders
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
# Load folders and images
# -------------------------------
def load_folders():
    conn = sqlite3.connect("gallery.db")
    c = conn.cursor()
    c.execute("SELECT folder, name, age, profession, category FROM folders")
    folders = [{"folder": row[0], "name": row[1], "age": row[2], "profession": row[3], "category": row[4]}
               for row in c.fetchall()]
    conn.close()
    return folders

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
# App UI
# -------------------------------
st.title("📸 Photo Gallery")

folders = load_folders()
categories = sorted(set(f["category"] for f in folders))
tabs = st.tabs(categories)

# -------------------------------
# Show all images first
# -------------------------------
for category, tab in zip(categories, tabs):
    with tab:
        st.header(category)
        category_folders = [f for f in folders if f["category"] == category]

        for f in category_folders:
            st.subheader(f"{f['name']} ({f['age']}, {f['profession']})")
            images = get_images_from_db(f["folder"])
            if not images:
                st.warning(f"No images found for {f['folder']}")
                continue

            # Display all images as small gallery first
            cols = st.columns(min(len(images), 4))  # up to 4 per row
            for idx, (name, img, _, _, _) in enumerate(images):
                with cols[idx % 4]:
                    if st.button(f"", key=f"preview_{f['folder']}_{idx}", help="Click to view"):
                        st.session_state[f"zoom_folder"] = f["folder"]
                        st.session_state[f"zoom_index"] = idx
                        st.rerun()
                    st.image(img, use_container_width=True)

# -------------------------------
# Zoomed slider view
# -------------------------------
if "zoom_folder" in st.session_state:
    folder = st.session_state.zoom_folder
    images = get_images_from_db(folder)
    current_index = st.session_state.get("zoom_index", 0)

    st.markdown("---")
    st.subheader(f"🔍 Viewing {folder} ({current_index + 1}/{len(images)})")
    image_name, img, image_data, download_allowed, _ = images[current_index]
    st.image(img, use_container_width=True)

    col1, col2, col3 = st.columns([1, 8, 1])
    with col1:
        if st.button("◄ Previous", key=f"prev_zoom"):
            st.session_state.zoom_index = max(0, current_index - 1)
            st.rerun()
    with col3:
        if st.button("Next ►", key=f"next_zoom"):
            st.session_state.zoom_index = min(len(images) - 1, current_index + 1)
            st.rerun()
