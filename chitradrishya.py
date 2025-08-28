import streamlit as st
import sqlite3
import io
from datetime import datetime
from PIL import Image
import uuid
import mimetypes
import base64

# -------------------------------
# Helper: Convert image to base64
# -------------------------------
def image_to_base64(image_data):
    return base64.b64encode(image_data).decode('utf-8')

# -------------------------------
# Initialize database
# -------------------------------
def init_db():
    conn = sqlite3.connect("gallery.db")
    c = conn.cursor()
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
    conn.commit()

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
# Database operations
# -------------------------------
def load_folders():
    conn = sqlite3.connect("gallery.db")
    c = conn.cursor()
    c.execute("SELECT folder, name, age, profession, category FROM folders")
    folders = [{"folder": r[0], "name": r[1], "age": r[2], "profession": r[3], "category": r[4]} for r in c.fetchall()]
    conn.close()
    return folders

def get_images_from_db(folder):
    conn = sqlite3.connect("gallery.db")
    c = conn.cursor()
    c.execute("SELECT name, image_data, download_allowed FROM images WHERE folder = ?", (folder,))
    images = []
    for name, image_data, download_allowed in c.fetchall():
        try:
            image = Image.open(io.BytesIO(image_data))
            base64_image = image_to_base64(image_data)
            images.append((name, image, image_data, download_allowed, base64_image))
        except:
            continue
    conn.close()
    return images

def save_survey_data(folder, rating, feedback, timestamp):
    conn = sqlite3.connect("gallery.db")
    c = conn.cursor()
    c.execute("INSERT INTO surveys (folder, rating, feedback, timestamp) VALUES (?, ?, ?, ?)",
              (folder, rating, feedback, timestamp))
    conn.commit()
    conn.close()

def load_survey_data():
    conn = sqlite3.connect("gallery.db")
    c = conn.cursor()
    c.execute("SELECT folder, rating, feedback, timestamp FROM surveys")
    survey_data = {}
    for folder, rating, feedback, timestamp in c.fetchall():
        if folder not in survey_data:
            survey_data[folder] = []
        survey_data[folder].append({"rating": rating, "feedback": feedback, "timestamp": timestamp})
    conn.close()
    return survey_data

# -------------------------------
# Initialize DB
# -------------------------------
init_db()

# -------------------------------
# CSS for gallery & prevent download
# -------------------------------
st.markdown("""
<style>
.main-image {
    width: 100%;
    max-height: 80vh;
    object-fit: contain;
    border: 2px solid #333;
    border-radius: 8px;
    margin-bottom: 10px;
}
.thumbnail-container {
    display: flex;
    overflow-x: auto;
    gap: 10px;
    padding: 5px 0;
}
.thumbnail {
    width: 120px;
    height: 120px;
    object-fit: cover;
    border-radius: 4px;
    border: 1px solid #ccc;
    cursor: pointer;
}
.thumbnail:hover {
    border-color: #333;
}
img {
    pointer-events: none;
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

data = load_folders()
survey_data = load_survey_data()
categories = sorted(set(item["category"] for item in data))
tabs = st.tabs(categories)

for category, tab in zip(categories, tabs):
    with tab:
        st.header(category)
        category_data = [item for item in data if item["category"] == category]

        for item in category_data:
            st.subheader(f"{item['name']} ({item['age']}, {item['profession']})")
            images = get_images_from_db(item["folder"])

            if images:
                if f"current_{item['folder']}" not in st.session_state:
                    st.session_state[f"current_{item['folder']}"] = 0
                idx = st.session_state[f"current_{item['folder']}"]
                if idx >= len(images):
                    idx = 0
                    st.session_state[f"current_{item['folder']}"] = 0

                # Main image
                name, image, image_data, download_allowed, base64_image = images[idx]
                st.image(image, use_column_width=True)

                # Navigation
                col1, col2, col3 = st.columns([1,8,1])
                with col1:
                    if st.button("◄ Prev", key=f"prev_{item['folder']}") and idx > 0:
                        st.session_state[f"current_{item['folder']}"] = idx - 1
                        st.rerun()
                with col3:
                    if st.button("Next ►", key=f"next_{item['folder']}") and idx < len(images)-1:
                        st.session_state[f"current_{item['folder']}"] = idx + 1
                        st.rerun()

                # Horizontal thumbnails
                st.markdown('<div class="thumbnail-container">', unsafe_allow_html=True)
                for t_idx, (t_name, t_image, _, _, t_base64) in enumerate(images):
                    if st.button("", key=f"thumb_{item['folder']}_{t_idx}", help=t_name):
                        st.session_state[f"current_{item['folder']}"] = t_idx
                        st.rerun()
                    st.image(t_image, width=80)
                st.markdown('</div>', unsafe_allow_html=True)

            else:
                st.warning(f"No images for {item['folder']}.")

            # Survey Form
            with st.expander(f"📝 Survey for {item['name']}"):
                with st.form(key=f"survey_form_{item['folder']}"):
                    rating = st.slider("Rating (1-5)", 1,5,3)
                    feedback = st.text_area("Feedback")
                    if st.form_submit_button("Submit"):
                        save_survey_data(item['folder'], rating, feedback, datetime.now().isoformat())
                        st.success("✅ Response recorded")
                        st.rerun()

            # Display surveys
            if item['folder'] in survey_data and survey_data[item['folder']]:
                st.subheader(f"💬 Survey Responses for {item['name']}")
                for entry in survey_data[item['folder']]:
                    with st.expander(entry['timestamp']):
                        st.write(f"⭐ {entry['rating']} — {entry['feedback']}")
