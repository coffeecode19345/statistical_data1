import streamlit as st
import os

# Data for the six ladies
data = [
    {"name": "Xiaojing", "age": 26, "profession": "Graphic Designer", "category": "Artists", "folder": "xiaojing"},
    {"name": "Yuena", "age": 29, "profession": "Painter", "category": "Artists", "folder": "yuena"},
    {"name": "Chunyang", "age": 32, "profession": "Software Developer", "category": "Engineers", "folder": "chunyang"},
    {"name": "Yu", "age": 27, "profession": "Data Scientist", "category": "Engineers", "folder": "yu"},
    {"name": "Yijie", "age": 30, "profession": "Literature Teacher", "category": "Teachers", "folder": "yijie"},
    {"name": "Haoran", "age": 34, "profession": "History Teacher", "category": "Teachers", "folder": "haoran"}
]

# Streamlit app
st.title("Photo Gallery")

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
                # Find the first image in the folder
                folder_path = item["folder"]
                image_files = [
                    f for f in os.listdir(folder_path)
                    if f.lower().endswith(('.jpg', '.jpeg', '.png')) and os.path.isfile(os.path.join(folder_path, f))
                ] if os.path.exists(folder_path) else []
                if image_files:
                    image_path = os.path.join(folder_path, image_files[0])
                    try:
                        st.image(image_path, caption=f"{item['name']} ({item['age']}, {item['profession']})", width=150)
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
                            st.success(f"Thank you for rating {item['name']} with {rating} stars! Feedback: {feedback}")
