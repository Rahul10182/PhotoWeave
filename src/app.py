from PIL import Image
import streamlit as st
import os
import cv2
import numpy as np
import imageio

cv2.ocl.setUseOpenCL(False)
import warnings
warnings.filterwarnings('ignore')

# Define target dimensions for 16:9 aspect ratio
TARGET_WIDTH = 1280
TARGET_HEIGHT = 720

def standardize_image(image: np.ndarray, target_width: int = TARGET_WIDTH, target_height: int = TARGET_HEIGHT) -> np.ndarray:
    """
    Resizes an image to fit within a 16:9 aspect ratio while maintaining its original aspect ratio.
    Pads the image with black borders if necessary to match the exact target dimensions.

    Parameters:
    - image (np.ndarray): Input image as a NumPy array.
    - target_width (int): Target width of the standardized image (default: 1920).
    - target_height (int): Target height of the standardized image (default: 1080).

    Returns:
    - np.ndarray: The standardized image with the target aspect ratio.
    """
    # Get original dimensions
    h, w = image.shape[:2]
    
    # Compute the new dimensions while preserving the aspect ratio
    scale_factor = min(target_width / w, target_height / h)
    new_width = int(w * scale_factor)
    new_height = int(h * scale_factor)
    
    # Resize the image while maintaining aspect ratio
    resized_image = cv2.resize(image, (new_width, new_height), interpolation=cv2.INTER_AREA)

    # Create a blank canvas with the target dimensions
    standardized_image = np.zeros((target_height, target_width, 3), dtype=np.uint8)

    # Compute centering offsets
    y_offset = (target_height - new_height) // 2
    x_offset = (target_width - new_width) // 2

    # Paste the resized image onto the center of the canvas
    standardized_image[y_offset:y_offset + new_height, x_offset:x_offset + new_width] = resized_image

    return standardized_image


# Image stitching function
def stitch_images(train_image, query_image):
    # Normalize images
    # train_image = standardize_image(train_image)
    # query_image = standardize_image(query_image)

    # Convert images to RGB
    train_photo = cv2.cvtColor(train_image, cv2.COLOR_BGR2RGB)
    train_photo_gray = cv2.cvtColor(train_photo, cv2.COLOR_RGB2GRAY)

    query_photo = cv2.cvtColor(query_image, cv2.COLOR_BGR2RGB)
    query_photo_gray = cv2.cvtColor(query_photo, cv2.COLOR_RGB2GRAY)

    # Feature extraction
    def select_descriptor_methods(image, method='sift'):
        if method == 'sift':
            descriptor = cv2.SIFT_create()
        elif method == 'surf':
            descriptor = cv2.SURF_create()
        elif method == 'brisk':
            descriptor = cv2.BRISK_create()
        elif method == 'orb':
            descriptor = cv2.ORB_create()
        (keypoints, features) = descriptor.detectAndCompute(image, None)
        return (keypoints, features)

    keypoints_train_img, features_train_img = select_descriptor_methods(train_photo_gray, method='sift')
    keypoints_query_img, features_query_img = select_descriptor_methods(query_photo_gray, method='sift')

    # Feature matching
    def create_matching_object(method, crossCheck):
        if method == 'sift' or method == 'surf':
            bf = cv2.BFMatcher(cv2.NORM_L2, crossCheck=crossCheck)
        elif method == 'orb' or method == 'brisk':
            bf = cv2.BFMatcher(cv2.NORM_HAMMING, crossCheck=crossCheck)
        return bf

    def key_points_matching(features_train_img, features_query_img, method):
        bf = create_matching_object(method, crossCheck=True)
        best_matches = bf.match(features_train_img, features_query_img)
        rawMatches = sorted(best_matches, key=lambda x: x.distance)
        return rawMatches

    matches = key_points_matching(features_train_img, features_query_img,method='sift')

    
    # Homography stitching
    def homography_stitching(keypoints_train_img, keypoints_query_img, matches, reprojThresh):
        keypoints_train_img = np.float32([keypoint.pt for keypoint in keypoints_train_img])
        keypoints_query_img = np.float32([keypoint.pt for keypoint in keypoints_query_img])
        if len(matches) > 4:
            points_train = np.float32([keypoints_train_img[m.queryIdx] for m in matches])
            points_query = np.float32([keypoints_query_img[m.trainIdx] for m in matches])
            (H, status) = cv2.findHomography(points_train, points_query, cv2.RANSAC, reprojThresh)
            return (matches, H, status)
        else:
            return None

    M = homography_stitching(keypoints_train_img, keypoints_query_img, matches, reprojThresh=4)
    if M is None:
        return None

    (matches, Homography_Matrix, status) = M

    # Warping and stitching
    width = query_photo.shape[1] + train_photo.shape[1]
    height = max(query_photo.shape[0], train_photo.shape[0])
    result = cv2.warpPerspective(train_photo, Homography_Matrix, (width, height))
    result[0:query_photo.shape[0], 0:query_photo.shape[1]] = query_photo

    return result

# Streamlit app
st.title("Image Stitching App")
st.write("Upload multiple images to stitch them together.")

# File uploaders
uploaded_files = st.file_uploader("Upload images (Train Image and Query Images)", type=["jpg", "jpeg", "png"], accept_multiple_files=True)

if uploaded_files:
    # Read images
    images = [cv2.imdecode(np.frombuffer(uploaded_file.read(), np.uint8), cv2.IMREAD_COLOR) for uploaded_file in uploaded_files]

    # Check if images are loaded correctly
    if any(image is None for image in images):
        st.error("Error loading one or more images. Please check the files.")
    else:
        # Display uploaded images
        st.subheader("Uploaded Images")
        cols = st.columns(len(images))
        for col, img in zip(cols, images):
            col.image(img, use_container_width=True)

        # Stitch images iteratively
        st.subheader("Stitched Image")
        with st.spinner("Stitching images..."):
            stitched_image = images[0]  # Start with the first image
            for i in range(1, len(images)):
                stitched_image = stitch_images(stitched_image, images[i])
                if stitched_image is None:
                    st.error("Error stitching images. Please ensure the images overlap sufficiently.")
                    break

        if stitched_image is not None:
            # Convert result to PIL image for display
            result_image = Image.fromarray(cv2.cvtColor(stitched_image, cv2.COLOR_BGR2RGB))
            st.image(result_image, caption="Stitched Image", use_container_width=True)

            # Download button for the stitched image
            result_path = "stitched_image.jpg"
            imageio.imwrite(result_path, stitched_image)
            with open(result_path, "rb") as file:
                st.download_button(
                    label="Download Stitched Image",
                    data=file,
                    file_name=result_path,
                    mime="image/jpeg"
                )