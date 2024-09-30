import streamlit as st
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns
import plotly.express as px
import pyautogui
from PIL import Image, ImageChops

# Function to capture the selected screen/application
def capture_screen(application_name=None):
    if application_name:
        # Placeholder for application-specific window capture
        st.warning("Application-specific capture is not implemented. Capturing the entire screen.")
    screenshot = pyautogui.screenshot()
    return screenshot

# Function to find differences between two images
def find_differences(img1, img2):
    diff = ImageChops.difference(img1, img2)
    return diff

# Streamlit App
def main():
    st.title("Screen Capture and Image Comparison Tool")

    st.sidebar.header("Options")

    # 1. Select which screen to capture
    capture_option = st.sidebar.checkbox("Capture Screen")
    application_name = None
    if capture_option:
        application_name = st.sidebar.text_input("Enter Application Name to Capture (Optional)")

    # 2. Select which file to compare
    compare_option = st.sidebar.checkbox("Select File to Compare")
    compare_file = None
    if compare_option:
        uploaded_file = st.sidebar.file_uploader("Choose an image file", type=["png", "jpg", "jpeg", "bmp", "gif"])
        if uploaded_file is not None:
            img2 = Image.open(uploaded_file).convert("RGB")
            st.sidebar.image(img2, caption="Uploaded Image", use_column_width=True)
            compare_file = img2

    # Capture and Compare
    if st.sidebar.button("Run"):
        if capture_option:
            with st.spinner("Capturing screen..."):
                captured_image = capture_screen(application_name)
                captured_image_path = "captured_image.png"
                captured_image.save(captured_image_path)
                st.success("Screen captured successfully!")
        else:
            st.warning("Please select the 'Capture Screen' option to proceed.")

        if compare_option and compare_file:
            with st.spinner("Comparing images..."):
                try:
                    img1 = Image.open("captured_image.png").convert("RGB")
                    diff = find_differences(img1, compare_file)
                    # Highlight differences
                    diff = diff.convert("RGB")
                    diff = np.array(diff)
                    # Enhance differences for better visibility
                    diff = diff * 10  # Adjust the multiplier as needed
                    diff = Image.fromarray(np.uint8(diff))
                    
                    st.success("Images compared successfully!")

                    # 4. Write an output that will show the differences
                    st.subheader("Differences:")
                    st.image(diff, caption="Differences between captured image and selected file", use_column_width=True)
                except Exception as e:
                    st.error(f"Error comparing images: {e}")

        # Display captured image
        if capture_option:
            st.subheader("Captured Image:")
            st.image(captured_image, caption="Captured Screen", use_column_width=True)

        # Optionally display the file to compare
        if compare_option and compare_file:
            st.subheader("Image to Compare:")
            st.image(img2, caption="Selected Image", use_column_width=True)

    # 5. Let the user select which application to capture the screen
    st.sidebar.info("Note: Application-specific screen capture is not fully implemented. The tool captures the entire screen by default.")

if __name__ == "__main__":
        main()