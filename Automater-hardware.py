import pyautogui
import time

# Define the array of links
links = ["link1", "link2", "link3"]

# Define positions (coordinates may vary by setup)
input_field_position = (800, 500)      # Coordinates of the input field
submit_button_position = (850, 600)   # Coordinates of the submit button
popup_close_position = (900, 300)     # Coordinates of the popup close button
download_button_1_position = (1000, 700)  # Coordinates of the first download button
download_button_2_position = (1100, 750)  # Coordinates of the second download button
file_name_field_position = (850, 800)     # Coordinates of the file name field in the save dialog
save_button_position = (1000, 850)       # Coordinates of the "Save" button

# Automate browser interaction
for link in links:
    # Open the browser and navigate to the target webpage manually or programmatically
    time.sleep(2)  # Wait for the page to load

    # Click on the input field and type the link
    pyautogui.click(input_field_position)
    pyautogui.write(link)
    
    # Click the submit button
    pyautogui.click(submit_button_position)
    time.sleep(3)  # Wait for the response to load
    
    # Handle potential popup
    if pyautogui.pixelMatchesColor(popup_close_position[0], popup_close_position[1], (255, 255, 255)):  # Example color
        pyautogui.click(popup_close_position)
    
    # Click the first "Download mp3" button
    pyautogui.click(download_button_1_position)
    time.sleep(5)  # Allow time for processing
    
    # Click the final "Download mp3" button
    pyautogui.click(download_button_2_position)
    time.sleep(3)  # Wait for the save dialog to appear
    
    # Enter the file name in the save dialog
    pyautogui.click(file_name_field_position)
    pyautogui.write(f"{link.split('/')[-1]}_file.mp3")  # Name file based on link
    
    # Click the save button
    pyautogui.click(save_button_position)
    time.sleep(2)  # Wait for the download to start
