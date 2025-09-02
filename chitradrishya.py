import streamlit as st
import sqlite3
import os
import base64
import io
import json
from PIL import Image

DB_PATH = "images.db"

# --- Database helpers ---
def get_connection():
    return sqlite3.connect(DB_PATH)

def get_folders():
    with get_connection() as conn:
        cur = conn.cursor()
        cur.execute("SELECT DISTINCT folder FROM images")
        return [row[0] for row in cur.fetchall()]

def get_images_by_folder(folder):
    with get_connection() as conn:
        cur = conn.cursor()
        cur.execute("SELECT id, name, data FROM images WHERE folder=?", (folder,))
        rows = cur.fetchall()
        return [{"id": r[0], "name": r[1], "data": r[2]} for r in rows]

def get_image_by_id(img_id):
    with get_connection() as conn:
        cur = conn.cursor()
        cur.execute("SELECT id, name, data FROM images WHERE id=?", (img_id,))
        row = cur.fetchone()
        if row:
            return {"id": row[0], "name": row[1], "data": row[2]}
        return None

def save_edit(img_id, img_bytes):
    with get_connection() as conn:
        cur = conn.cursor()
        cur.execute("INSERT INTO edits (image_id, data) VALUES (?, ?)", (img_id, img_bytes))
        conn.commit()

def get_edit_history(img_id):
    with get_connection() as conn:
        cur = conn.cursor()
        cur.execute("SELECT id, data FROM edits WHERE image_id=? ORDER BY id DESC", (img_id,))
        return cur.fetchall()

def undo_last_edit(img_id):
    with get_connection() as conn:
        cur = conn.cursor()
        cur.execute("DELETE FROM edits WHERE id=(SELECT id FROM edits WHERE image_id=? ORDER BY id DESC LIMIT 1)", (img_id,))
        conn.commit()

def delete_image(img_id):
    with get_connection() as conn:
        cur = conn.cursor()
        cur.execute("DELETE FROM images WHERE id=?", (img_id,))
        cur.execute("DELETE FROM edits WHERE image_id=?", (img_id,))
        conn.commit()

# --- Utility ---
def image_to_base64(img_bytes):
    return base64.b64encode(img_bytes).decode("utf-8")

def safe_mime(filename):
    ext = filename.lower().split(".")[-1]
    return {
        "jpg": "image/jpeg",
        "jpeg": "image/jpeg",
        "png": "image/png",
        "tif": "image/tiff",
        "tiff": "image/tiff",
        "bmp": "image/bmp"
    }.get(ext, "application/octet-stream")

# --- App Layout ---
st.set_page_config(layout="wide")

if "view" not in st.session_state:
    st.session_state.view = "grid"
if "current_folder" not in st.session_state:
    st.session_state.current_folder = None
if "current_index" not in st.session_state:
    st.session_state.current_index = 0

folders = get_folders()

if st.session_state.view == "grid":
    st.title("Image Grid View")

    folder = st.selectbox("Select Folder", folders, key="folder_select")
    if folder:
        st.session_state.current_folder = folder
        images = get_images_by_folder(folder)

        cols = st.columns(4)
        for i, img_dict in enumerate(images):
            with cols[i % 4]:
                img = Image.open(io.BytesIO(img_dict["data"]))
                st.image(img, caption=img_dict["name"], use_container_width=True)
                if st.button("Zoom", key=f"zoom_{img_dict['id']}"):
                    st.session_state.view = "zoom"
                    st.session_state.current_index = i
                    st.rerun()

elif st.session_state.view == "zoom":
    folder = st.session_state.current_folder
    images = get_images_by_folder(folder)

    if not images:
        st.warning("No images available")
        st.session_state.view = "grid"
        st.rerun()

    if st.session_state.current_index >= len(images):
        st.session_state.current_index = 0

    img_dict = images[st.session_state.current_index]
    img = Image.open(io.BytesIO(img_dict["data"]))

    st.title(f"Zoom View: {img_dict['name']}")

    col1, col2, col3 = st.columns([1, 4, 1])
    with col1:
        if st.button("← Prev"):
            st.session_state.current_index = (st.session_state.current_index - 1) % len(images)
            st.rerun()
    with col3:
        if st.button("Next →"):
            st.session_state.current_index = (st.session_state.current_index + 1) % len(images)
            st.rerun()

    # --- Display with cropping ---
    canvas_width, canvas_height = 600, 400
    base64_image = image_to_base64(img_dict["data"])
    image_id = f"canvas_{img_dict['id']}"

    st.markdown(f"""
        <canvas id="{image_id}" width="{canvas_width}" height="{canvas_height}" 
                style="border:1px solid black; background-color:white;"></canvas>
        <script>
            const img = new Image();
            img.src = "data:image/png;base64,{base64_image}";
            img.onload = function() {{
                const canvas = document.getElementById('{image_id}');
                const ctx = canvas.getContext('2d');
                ctx.drawImage(img, 0, 0, {canvas_width}, {canvas_height});
                if (typeof initCropCanvas === "function") {{
                    initCropCanvas('{image_id}', {canvas_width}, {canvas_height});
                }}
            }};
        </script>
    """, unsafe_allow_html=True)

    crop_coords_input = st.text_input(
        "Crop Coordinates (JSON)",
        value=st.session_state.get("crop_coords", ""),
        key=f"crop_coords_{folder}_{img_dict['name']}"
    )

    if crop_coords_input:
        try:
            st.session_state.crop_coords = json.loads(crop_coords_input)
        except json.JSONDecodeError:
            st.session_state.crop_coords = None
            st.error("Invalid crop coordinates")

    if st.session_state.get("crop_coords"):
        scale_x = img.width / canvas_width if canvas_width else 1
        scale_y = img.height / canvas_height if canvas_height else 1
        crop_box = (
            int(st.session_state.crop_coords["left"] * scale_x),
            int(st.session_state.crop_coords["top"] * scale_y),
            int(st.session_state.crop_coords["right"] * scale_x),
            int(st.session_state.crop_coords["bottom"] * scale_y)
        )
        cropped_img = img.crop(crop_box)
        st.image(cropped_img, caption="Cropped Preview")
        buf = io.BytesIO()
        cropped_img.save(buf, format="PNG")
        save_edit(img_dict["id"], buf.getvalue())

    # --- Buttons ---
    colA, colB, colC = st.columns(3)
    with colA:
        if st.button("Undo Last Edit"):
            undo_last_edit(img_dict["id"])
            st.rerun()
    with colB:
        if st.button("Delete Image"):
            delete_image(img_dict["id"])
            st.session_state.view = "grid"
            st.rerun()
    with colC:
        st.download_button(
            "Download Image",
            data=img_dict["data"],
            file_name=img_dict["name"],
            mime=safe_mime(img_dict["name"])
        )

    if st.button("Back to Grid"):
        st.session_state.view = "grid"
        st.rerun()
