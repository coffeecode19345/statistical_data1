import streamlit as st
import os
import json
import time
from datetime import datetime

# Data for the six ladies
data = [
    {"name": "Xiaojing", "age": 26, "profession": "Graphic Designer", "category": "Artists", "folder": "xiaojing"},
    {"name": "Yuena", "age": 29, "profession": "Painter", "category": "Artists", "folder": "yuena"},
    {"name": "Chunyang", "age": 32, "profession": "Software Developer", "category": "Engineers", "folder": "chunyang"},
    {"name": "Yu", "age": 27, "profession": "Data Scientist", "category": "Engineers", "folder": "yu"},
    {"name": "Yijie", "age": 30, "profession": "Literature Teacher", "category": "Teachers", "folder": "yijie"},
    {"name": "Haoran", "age": 34, "profession": "History Teacher", "category": "Teachers", "folder": "haoran"}
]

# Initialize session state for image indices
if 'image_indices' not in st.session_state:
    st.session_state.image_indices = {item["folder"]: 0 for item in data}

# Path to survey data JSON file
SURVEY_FILE = "survey_data.json"

# Load survey data from JSON file
def load_survey_data():
    try:
        if os.path.exists(SURVEY_FILE):
            with open(SURVEY_FILE, 'r') as f:
                return json.load(f)
        return {item["folder"]: [] for item in data}  # Initialize empty for each folder
    except Exception as e:
        st.error(f"Error loading survey data: {str(e)}")
        return {item["folder"]: [] for item in data}

# Save survey data to JSON file
def save_survey_data(survey_data):
    try:
        with open(SURVEY_FILE, 'w') as f:
            json.dump(survey_data, f, indent=4)
    except Exception as e:
        st.error(f"Error saving survey data: {str(e)}")

# Delete a survey entry
def delete_survey_entry(folder, timestamp):
    survey_data = load_survey_data()
    if folder in survey_data:
        survey_data[folder] = [entry for entry in survey_data[folder] if entry["timestamp"] != timestamp]
        save_survey_data(survey_data)

# CSS for image styling
st.markdown("""
    <style>
    .image-container img {
        border: 2px solid #333;
        border-radius: 8px;
        box-shadow: 3px 3px 8px rgba(0, 0, 0, 0.3);
        margin-bottom: 10px;
    }
    </style>
""", unsafe_allow_html=True)

# Streamlit app
st.title("Photo Gallery")

# Load survey data
survey_data = load_survey_data()

# Get unique categories
categories = sorted(set(item["category"] for item in data))
tabs = st.tabs(categories)

# Iterate through tabs
for tab_idx, (category, tab) in enumerate(zip(categories, tabs)):
    with tab:
        st.header(category)
        # Filter data for this category
        category_data = [item for item in data if item["category"] == category]
        # Create a 2-column grid
        cols = st.columns(2)
        for idx, item in enumerate(category_data):
            col = cols[idx % 2]  # Alternate between columns
            with col:
                # Find all images in the folder
                folder_path = item["folder"]
                image_files = [
                    f for f in os.listdir(folder_path)
                    if f.lower().endswith(('.jpg', '.jpeg', '.png')) and os.path.isfile(os.path.join(folder_path, f))
                ] if os.path.exists(folder_path) else []
                
                if image_files:
                    # Get current image index for this folder
                    current_index = st.session_state.image_indices.get(item["folder"], 0)
                    # Ensure index is within bounds
                    current_index = current_index % len(image_files)
                    image_path = os.path.join(folder_path, image_files[current_index])
                    try:
                        # Display image with custom styling
                        st.markdown(f'<div class="image-container">', unsafe_allow_html=True)
                        st.image(image_path, caption=f"{item['name']} ({item['age']}, {item['profession']})", width=400)
                        st.markdown('</div>', unsafe_allow_html=True)
                    except Exception as e:
                        st.warning(f"Failed to load image from {image_path}: {str(e)}")
                else:
                    st.warning(f"No image found in folder: {folder_path}")
                
                # Survey button and form
                button_label = f"Survey for {item['name']}"
                if st.button(button_label, key=f"survey_{item['folder']}_{idx}"):
                    with st.form(key=f"survey_form_{item['folder']}_{idx}"):
                        st.write(f"Rate {item['name']}'s profile:")
                        rating = st.slider("Rating (1-5)", 1, 5, 3, key=f"rating_{item['folder']}_{idx}")
                        feedback = st.text_area("Feedback", key=f"feedback_{item['folder']}_{idx}")
                        if st.form_submit_button("Submit"):
                            # Save survey data
                            timestamp = datetime.now().isoformat()
                            survey_entry = {
                                "rating": rating,
                                "feedback": feedback,
                                "timestamp": timestamp
                            }
                            survey_data.setdefault(item["folder"], []).append(survey_entry)
                            save_survey_data(survey_data)
                            st.success(f"Thank you for rating {item['name']} with {rating} stars! Feedback: {feedback}")
                            # Increment image index
                            if image_files:
                                st.session_state.image_indices[item["folder"]] = (current_index + 1) % len(image_files)
                            # Rerun to update image and survey data
                            st.rerun()
                
                # Display saved survey data
                st.subheader(f"Survey Responses for {item['name']}")
                if item["folder"] in survey_data and survey_data[item["folder"]]:
                    for entry in survey_data[item["folder"]]:
                        st.write(f"Rating: {entry['rating']} stars, Feedback: {entry['feedback']} (Submitted: {entry['timestamp']})")
                        if st.button("Delete", key=f"delete_{item['folder']}_{entry['timestamp']}"):
                            delete_survey_entry(item["folder"], entry["timestamp"])
                            st.rerun()
                else:
                    st.write("No survey responses yet.")
