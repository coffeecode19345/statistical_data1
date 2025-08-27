import streamlit as st
import os
import json
from datetime import datetime

# -------------------------------
# Data for the six ladies
# -------------------------------
data = [
    {"name": "Xiaojing", "age": 26, "profession": "Graphic Designer", "category": "Artists", "folder": "xiaojing"},
    {"name": "Yuena", "age": 29, "profession": "Painter", "category": "Artists", "folder": "yuena"},
    {"name": "Chunyang", "age": 15, "profession": "Software Developer", "category": "Engineers", "folder": "chunyang"},
    {"name": "Yu", "age": 47, "profession": "Data Scientist", "category": "Engineers", "folder": "yu"},
    {"name": "Yijie", "age": 30, "profession": "Literature Teacher", "category": "Teachers", "folder": "yijie"},
    {"name": "Haoran", "age": 34, "profession": "History Teacher", "category": "Teachers", "folder": "haoran"},
    {"name": "Yajie", "age": 27, "profession": "Musician", "category": "Artists", "folder": "yajie"}  # 
]

SURVEY_FILE = "survey_data.json"

# -------------------------------
# Load & Save survey data
# -------------------------------
def load_survey_data():
    try:
        if os.path.exists(SURVEY_FILE):
            with open(SURVEY_FILE, "r") as f:
                return json.load(f)
        return {item["folder"]: [] for item in data}
    except Exception as e:
        st.error(f"Error loading survey data: {str(e)}")
        return {item["folder"]: [] for item in data}

def save_survey_data(survey_data):
    try:
        with open(SURVEY_FILE, "w") as f:
            json.dump(survey_data, f, indent=4)
    except Exception as e:
        st.error(f"Error saving survey data: {str(e)}")

def delete_survey_entry(folder, timestamp):
    survey_data = load_survey_data()
    if folder in survey_data:
        survey_data[folder] = [entry for entry in survey_data[folder] if entry["timestamp"] != timestamp]
        save_survey_data(survey_data)

# -------------------------------
# CSS Styling + Prevent Right-Click
# -------------------------------
st.markdown("""
    <style>
    .image-container img {
        border: 2px solid #333;
        border-radius: 8px;
        box-shadow: 3px 3px 8px rgba(0, 0, 0, 0.3);
        margin-bottom: 10px;
    }
    /* Prevent right click and dragging on images */
    img {
        pointer-events: none;
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
st.title("📸 Photo Gallery & Survey")

survey_data = load_survey_data()
categories = sorted(set(item["category"] for item in data))
tabs = st.tabs(categories)

# -------------------------------
# Loop through categories
# -------------------------------
for category, tab in zip(categories, tabs):
    with tab:
        st.header(category)
        category_data = [item for item in data if item["category"] == category]

        for item in category_data:
            st.subheader(f"{item['name']} ({item['age']}, {item['profession']})")

            folder_path = item["folder"]
            image_files = [
                f for f in os.listdir(folder_path)
                if f.lower().endswith(('.jpg', '.jpeg', '.png')) and os.path.isfile(os.path.join(folder_path, f))
            ] if os.path.exists(folder_path) else []

            if image_files:
                cols = st.columns(3)  # show 3 images per row
                for idx, image_file in enumerate(image_files):
                    image_path = os.path.join(folder_path, image_file)
                    with cols[idx % 3]:
                        st.markdown('<div class="image-container">', unsafe_allow_html=True)
                        st.image(image_path, use_container_width=True)
                        st.markdown('</div>', unsafe_allow_html=True)
            else:
                st.warning(f"No images found in {folder_path}")

            # -------------------------------
            # Survey form
            # -------------------------------
            with st.expander(f"📝 Survey for {item['name']}"):
                with st.form(key=f"survey_form_{item['folder']}"):
                    rating = st.slider("Rating (1-5)", 1, 5, 3, key=f"rating_{item['folder']}")
                    feedback = st.text_area("Feedback", key=f"feedback_{item['folder']}")
                    if st.form_submit_button("Submit"):
                        timestamp = datetime.now().isoformat()
                        survey_entry = {"rating": rating, "feedback": feedback, "timestamp": timestamp}
                        survey_data.setdefault(item["folder"], []).append(survey_entry)
                        save_survey_data(survey_data)
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
                        if st.button("🗑️ Delete", key=f"delete_{item['folder']}_{entry['timestamp']}"):
                            delete_survey_entry(item["folder"], entry["timestamp"])
                            st.rerun()
            else:
                st.caption("No survey responses yet.")
