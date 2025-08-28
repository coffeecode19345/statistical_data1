import streamlit as st
import sqlite3
import io
from PIL import Image
import uuid
import mimetypes
from datetime import datetime
import os

# -------------------------------
# DB and helper functions
# -------------------------------
DB_PATH = "gallery.db"

def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""CREATE TABLE IF NOT EXISTS folders (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        folder TEXT UNIQUE NOT NULL,
        name TEXT NOT NULL,
        age INTEGER NOT NULL,
        profession TEXT NOT NULL,
        category TEXT NOT NULL
    )""")
    c.execute("""CREATE TABLE IF NOT EXISTS images (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        folder TEXT NOT NULL,
        image_data BLOB NOT NULL,
        download_allowed BOOLEAN NOT NULL DEFAULT 1,
        FOREIGN KEY(folder) REFERENCES folders(folder)
    )""")
    conn.commit()
    conn.close()

def load_folders():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT folder, name, age, profession, category FROM folders")
    folders = [{"folder": r[0], "name": r[1], "age": r[2], "profession": r[3], "category": r[4]} for r in c.fetchall()]
    conn.close()
    return folders

def get_images(folder):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT name, image_data, download_allowed FROM images WHERE folder=?", (folder,))
    images = []
    for r in c.fetchall():
        name, data, download = r
        img = Image.open(io.BytesIO(data))
        images.append({"name": name, "image": img, "data": data, "download": download})
    conn.close()
    return images

def delete_image(folder, name):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("DELETE FROM images WHERE folder=? AND name=?", (folder, name))
    conn.commit()
    conn.close()

# -------------------------------
# Initialize DB
# -------------------------------
init_db()

# -------------------------------
# Session State
# -------------------------------
if "zoom_folder" not in st.session_state:
    st.session_state.zoom_folder = None
if "zoom_index" not in st.session_state:
    st.session_state.zoom_index = 0
if "is_author" not in st.session_state:
    st.session_state.is_author = False

# -------------------------------
# Author login
# -------------------------------
with st.sidebar:
    st.title("Author Login")
    pwd = st.text_input("Password", type="password")
    if st.button("Login"):
        if pwd == "admin123":
            st.session_state.is_author = True
            st.success("Logged in as author!")
        else:
            st.error("Wrong password")
    if st.session_state.is_author and st.button("Logout"):
        st.session_state.is_author = False
        st.success("Logged out")

# -------------------------------
# App UI
# -------------------------------
st.title("📸 Photo Gallery")

folders = load_folders()
categories = sorted(set(f["category"] for f in folders))

# -------------------------------
# Display grid of images (initial view)
# -------------------------------
if st.session_state.zoom_folder is None:
    for cat in categories:
        st.header(cat)
        cat_folders = [f for f in folders if f["category"] == cat]
        for f in cat_folders:
            st.subheader(f"{f['name']} ({f['age']}, {f['profession']})")
            images = get_images(f["folder"])
            if images:
                cols = st.columns(4)
                for idx, img_dict in enumerate(images):
                    col = cols[idx % 4]
                    with col:
                        # Display rectangular grid image
                        st.image(img_dict["image"], use_container_width=True, output_format="JPEG")
                        # Button to zoom
                        if st.button("🔍 View", key=f"view_{f['folder']}_{idx}"):
                            st.session_state.zoom_folder = f["folder"]
                            st.session_state.zoom_index = idx
                            st.experimental_rerun()
            else:
                st.warning("No images in this folder.")

# -------------------------------
# Zoom / slider view
# -------------------------------
else:
    folder = st.session_state.zoom_folder
    images = get_images(folder)
    idx = st.session_state.zoom_index
    img_dict = images[idx]

    st.subheader(f"🔍 Viewing {folder} ({idx+1}/{len(images)})")
    st.image(img_dict["image"], use_container_width=True)

    col1, col2, col3 = st.columns([1,8,1])
    with col1:
        if st.button("◄ Previous") and idx > 0:
            st.session_state.zoom_index -= 1
            st.experimental_rerun()
    with col3:
        if st.button("Next ►") and idx < len(images)-1:
            st.session_state.zoom_index += 1
            st.experimental_rerun()

    # Admin / download controls
    if img_dict["download"]:
        mime, _ = mimetypes.guess_type(img_dict["name"])
        st.download_button("⬇️ Download", data=img_dict["data"], file_name=img_dict["name"], mime=mime)
    if st.session_state.is_author:
        if st.button("🗑️ Delete Image"):
            delete_image(folder, img_dict["name"])
            st.success("Image deleted.")
            # update zoom index
            st.session_state.zoom_index = min(idx, len(images)-2)
            if len(get_images(folder)) == 0:
                st.session_state.zoom_folder = None
                st.session_state.zoom_index = 0
            st.experimental_rerun()
    if st.button("⬅️ Back to Grid"):
        st.session_state.zoom_folder = None
        st.session_state.zoom_index = 0
        st.experimental_rerun()
