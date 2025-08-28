import streamlit as st
import sqlite3
import io
from PIL import Image
import uuid
import mimetypes
from datetime import datetime
import base64
import os

DB_PATH = "gallery.db"

# -------------------------------
# Helper Functions
# -------------------------------
def image_to_base64(image_data):
    return base64.b64encode(image_data).decode('utf-8') if isinstance(image_data, bytes) else image_data.encode('utf-8')

def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    # Folders table
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
    # Images table
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
    # Surveys table
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

    default_folders = [
        {"name": "Xiaojing", "age": 26, "profession": "Graphic Designer", "category": "Artists", "folder": "xiaojing"},
        {"name": "Yuena", "age": 29, "profession": "Painter", "category": "Artists", "folder": "yuena"},
        {"name": "Yijie", "age": 30, "profession": "Literature Teacher", "category": "Teachers", "folder": "yijie"},
        {"name": "Yajie", "age": 27, "profession": "Musician", "category": "Artists", "folder": "yajie"},
        {"name": "Yu", "age": 47, "profession": "Data Scientist", "category": "Engineers", "folder": "yu"},
        {"name": "Chunyang", "age": 15, "profession": "Software Developer", "category": "Engineers", "folder": "chunyang"},
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

def load_folders():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT folder, name, age, profession, category FROM folders")
    folders = [{"folder": r[0], "name": r[1], "age": r[2], "profession": r[3], "category": r[4]} for r in c.fetchall()]
    conn.close()
    return folders

def add_folder(folder, name, age, profession, category):
    try:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("""
            INSERT INTO folders (folder, name, age, profession, category)
            VALUES (?, ?, ?, ?, ?)
        """, (folder, name, age, profession, category))
        conn.commit()
        conn.close()
        return True
    except sqlite3.IntegrityError:
        return False
    except Exception as e:
        st.error(f"Error adding folder: {str(e)}")
        return False

def load_images_to_db(uploaded_files, folder, download_allowed=True):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    for uploaded_file in uploaded_files:
        image_data = uploaded_file.read()
        extension = os.path.splitext(uploaded_file.name)[1].lower()
        random_filename = f"{uuid.uuid4()}{extension}"
        # Prevent duplicates
        c.execute("SELECT COUNT(*) FROM images WHERE folder = ? AND name = ?", (folder, random_filename))
        if c.fetchone()[0] == 0:
            c.execute("INSERT INTO images (name, folder, image_data, download_allowed) VALUES (?, ?, ?, ?)",
                      (random_filename, folder, image_data, download_allowed))
    conn.commit()
    conn.close()

def update_download_permission(folder, image_name, download_allowed):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("UPDATE images SET download_allowed = ? WHERE folder = ? AND name = ?",
              (download_allowed, folder, image_name))
    conn.commit()
    conn.close()

def delete_image(folder, name):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("DELETE FROM images WHERE folder = ? AND name = ?", (folder, name))
    conn.commit()
    conn.close()

def load_survey_data():
    conn = sqlite3.connect(DB_PATH)
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
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("INSERT INTO surveys (folder, rating, feedback, timestamp) VALUES (?, ?, ?, ?)",
              (folder, rating, feedback, timestamp))
    conn.commit()
    conn.close()

def delete_survey_entry(folder, timestamp):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("DELETE FROM surveys WHERE folder = ? AND timestamp = ?", (folder, timestamp))
    conn.commit()
    conn.close()

def get_images(folder):
    conn = sqlite3.connect(DB_PATH)
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
if "upload_files" not in st.session_state:
    st.session_state.upload_files = None

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
        st.experimental_rerun()

    if st.session_state.is_author:
        st.title("Manage Folders & Images")

        # Add folder
        st.subheader("Create New Folder")
        with st.form("add_folder_form"):
            new_folder = st.text_input("Folder Name")
            new_name = st.text_input("Person Name")
            new_age = st.number_input("Age", min_value=1, max_value=150)
            new_profession = st.text_input("Profession")
            new_category = st.selectbox("Category", ["Artists", "Engineers", "Teachers"])
            if st.form_submit_button("Add Folder"):
                if add_folder(new_folder.lower(), new_name, new_age, new_profession, new_category):
                    st.success(f"Folder '{new_folder}' added!")
                    st.experimental_rerun()

        # Upload images
        st.subheader("Upload Images")
        data = load_folders()
        folder_choice = st.selectbox("Select Folder", [item["folder"] for item in data])
        st.session_state.upload_files = st.file_uploader(
            "Select images", accept_multiple_files=True, type=['jpg','jpeg','png'], key="upload_files"
        )
        if st.session_state.upload_files:
            if st.button("Upload to DB"):
                load_images_to_db(st.session_state.upload_files, folder_choice)
                st.success(f"{len(st.session_state.upload_files)} image(s) uploaded to '{folder_choice}'")
                st.session_state.upload_files = None
                st.experimental_rerun()

        # Download permissions
        st.subheader("Manage Download Permissions")
        folder_choice_dp = st.selectbox("Select Folder", [item["folder"] for item in data], key="download_folder")
        images = get_images(folder_choice_dp)
        if images:
            with st.form(f"download_form_{folder_choice_dp}"):
                download_states = {}
                for img_dict in images:
                    toggle_key = f"toggle_{folder_choice_dp}_{img_dict['name']}"
                    download_states[img_dict['name']] = st.checkbox(
                        f"{img_dict['name'][:8]}...{img_dict['name'][-4:]}",
                        value=img_dict["download"], key=toggle_key
                    )
                if st.form_submit_button("Apply"):
                    for img_dict in images:
                        if download_states[img_dict['name']] != img_dict["download"]:
                            update_download_permission(folder_choice_dp, img_dict['name'], download_states[img_dict['name']])
                    st.success("Permissions updated!")
                    st.experimental_rerun()

# -------------------------------
# CSS for Improved GUI
# -------------------------------
st.markdown("""
<style>
.folder-card {background:#f9f9f9; border-radius:8px; padding:15px; margin-bottom:20px; box-shadow:0 4px 8px rgba(0,0,0,0.1);}
.folder-card:hover {transform: translateY(-5px); box-shadow:0 6px 12px rgba(0,0,0,0.15);}
.folder-header {font-size:1.5em; color:#333; margin-bottom:10px;}
.image-grid {display:flex; flex-wrap:wrap; gap:10px;}
img {max-height:150px; object-fit:cover; border-radius:4px;}
</style>
""", unsafe_allow_html=True)

# -------------------------------
# Main UI
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
            st.header(cat)
            cat_folders = [f for f in data if f["category"]==cat]
            for f in cat_folders:
                with st.container():
                    st.markdown(f'<div class="folder-card"><div class="folder-header">{f["name"]} ({f["age"]}, {f["profession"]})</div>', unsafe_allow_html=True)
                    images = get_images(f["folder"])
                    if images:
                        cols = st.columns(4)
                        for idx, img_dict in enumerate(images):
                            with cols[idx%4]:
                                st.image(img_dict["image"], use_container_width=True)
                                if st.button("🔍 View", key=f"{f['folder']}_{idx}"):
                                    st.session_state.zoom_folder = f["folder"]
                                    st.session_state.zoom_index = idx
                                    st.experimental_rerun()
                    else:
                        st.warning("No images in this folder")
                    # Survey form
                    with st.expander(f"📝 Survey for {f['name']}"):
                        with st.form(f"survey_form_{f['folder']}"):
                            rating = st.slider("Rating",1,5,3)
                            feedback = st.text_area("Feedback")
                            if st.form_submit_button("Submit"):
                                timestamp = datetime.now().isoformat()
                                save_survey_data(f["folder"], rating, feedback, timestamp)
                                st.success("Response recorded")
                                st.experimental_rerun()
                    # Display survey
                    if f["folder"] in survey_data:
                        for entry in survey_data[f["folder"]]:
                            with st.expander(entry["timestamp"]):
                                st.write(f"⭐ {entry['rating']} — {entry['feedback']}")
                                if st.session_state.is_author:
                                    if st.button("🗑️ Delete", key=f"del_{f['folder']}_{entry['timestamp']}"):
                                        delete_survey_entry(f["folder"], entry["timestamp"])
                                        st.experimental_rerun()
                    st.markdown("</div>", unsafe_allow_html=True)

# Slider / zoom view
else:
    folder = st.session_state.zoom_folder
    images = get_images(folder)
    idx = st.session_state.zoom_index
    img_dict = images[idx]
    st.subheader(f"Viewing {folder} ({idx+1}/{len(images)})")
    st.image(img_dict["image"], use_container_width=True)
    col1, col2, col3 = st.columns([1,8,1])
    with col1:
        if idx>0 and st.button("◄ Previous"):
            st.session_state.zoom_index -= 1
            st.experimental_rerun()
    with col3:
        if idx<len(images)-1 and st.button("Next ►"):
            st.session_state.zoom_index += 1
            st.experimental_rerun()
    if img_dict["download"]:
        mime,_ = mimetypes.guess_type(img_dict["name"])
        st.download_button("⬇️ Download", data=img_dict["data"], file_name=img_dict["name"], mime=mime)
    if st.session_state.is_author:
        if st.button("🗑️ Delete Image"):
            delete_image(folder, img_dict["name"])
            st.success("Deleted")
            st.session_state.zoom_index = max(0, idx-1)
            if len(get_images(folder))==0:
                st.session_state.zoom_folder = None
            st.experimental_rerun()
    if st.button("⬅️ Back to Grid"):
        st.session_state.zoom_folder = None
        st.session_state.zoom_index = 0
        st.experimental_rerun()
