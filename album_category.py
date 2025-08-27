import streamlit as st
import pandas as pd

# Sample data for the photo gallery
data = {
    "Artists": [
        {"name": "Xiaojing Zuo", "age": 34, "profession": "Software Engineer", "x2.jpg": "https://via.placeholder.com/150?text=XZ"},
        {"name": "Bob Jones", "age": 34, "profession": "Sculptor", "image": "https://via.placeholder.com/150?text=Bob"},
        {"name": "Clara Lee", "age": 25, "profession": "Photographer", "image": "https://via.placeholder.com/150?text=Clara"},
        {"name": "David Kim", "age": 40, "profession": "Illustrator", "image": "https://via.placeholder.com/150?text=David"}
    ],
    "Engineers": [
        {"name": "Emma Brown", "age": 30, "profession": "Software Engineer", "image": "https://via.placeholder.com/150?text=Emma"},
        {"name": "Frank Wilson", "age": 35, "profession": "Mechanical Engineer", "image": "https://via.placeholder.com/150?text=Frank"},
        {"name": "Grace Chen", "age": 29, "profession": "Civil Engineer", "image": "https://via.placeholder.com/150?text=Grace"}
    ],
    "Teachers": [
        {"name": "Hannah Lee", "age": 45, "profession": "Math Teacher", "image": "https://via.placeholder.com/150?text=Hannah"},
        {"name": "Ian Moore", "age": 38, "profession": "History Teacher", "image": "https://via.placeholder.com/150?text=Ian"}
    ]
}

# Streamlit app
st.title("Photo Gallery with Survey")

# Create tabs for each category
tab_names = list(data.keys())
tabs = st.tabs(tab_names)

# Iterate through tabs
for tab_idx, (tab_name, tab) in enumerate(zip(tab_names, tabs)):
    with tab:
        st.header(tab_name)
        # Create a grid of 2 columns
        cols = st.columns(2)
        for idx, item in enumerate(data[tab_name]):
            col = cols[idx % 2]  # Alternate between columns
            with col:
                # Display image
                st.image(item["image"], caption=f"{item['name']} ({item['age']}, {item['profession']})", width=150)
                # Survey button and form
                button_label = f"Survey for Tab {tab_idx + 1}"
                if st.button(button_label, key=f"survey_{tab_name}_{idx}"):
                    with st.form(key=f"survey_form_{tab_name}_{idx}"):
                        st.write(f"Rate {item['name']}'s profile:")
                        rating = st.slider("Rating (1-5 stars)", 1, 5, 3, key=f"rating_{tab_name}_{idx}")
                        feedback = st.text_area("Feedback", key=f"feedback_{tab_name}_{idx}")
                        submit = st.form_submit_button("Submit Survey")
                        if submit:
                            st.success(f"Thank you for rating {item['name']} with {rating} stars! Feedback: {feedback}")
