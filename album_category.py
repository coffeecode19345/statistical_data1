import streamlit as st
import os

# Sample data for the photo gallery
data = [
    {"name": "Alice Smith", "age": 28, "profession": "Painter", "category": "Artists", "folder": "Alice"},
    {"name": "Bob Jones", "age": 34, "profession": "Sculptor", "category": "Artists", "folder": "Bob"},
    {"name": "Clara Lee", "age": 25, "profession": "Photographer", "category": "Artists", "folder": "Clara"},
    {"name": "Emma Brown", "age": 30, "profession": "Software Engineer", "category": "Engineers", "folder": "Emma"},
    {"name": "Frank Wilson", "age": 35, "profession": "Mechanical Engineer", "category": "Engineers", "folder": "Frank"},
    {"name": "Hannah Lee", "age": 45, "profession": "Math Teacher", "category": "Teachers", "folder": "Hannah"}
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
                # Construct image path
                image_path = os.path.join(item["folder"], "profile.jpg")
                if os.path.exists(image_path):
                    st.image(image_path, caption=f"{item['name']} ({item['age']}, {item['profession']})", width=150)
                else:
                    st.warning(f"Image not found: {image_path}")
                # Survey button and form
                button_label = f"Survey for Tab {tab_idx + 1}"
                if st.button(button_label, key=f"survey_{item['folder']}_{idx}"):
                    with st.form(key=f"survey_form_{item['folder']}_{idx}"):
                        st.write(f"Rate {item['name']}'s profile:")
                        rating = st.slider("Rating (1-5)", 1, 5, 3, key=f"rating_{item['folder']}_{idx}")
                        feedback = st.text_area("Feedback", key=f"feedback_{item['folder']}_{idx}")
                        if st.form_submit_button("Submit"):
                            st.success(f"Thank you for rating {item['name']} with {rating} stars! Feedback: {feedback}")
