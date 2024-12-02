import time
import pyautogui  # To handle file save dialog if needed
import pyperclip
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import undetected_chromedriver as uc
from selenium_stealth import stealth

"""
* Issues *
- Cloudfare detection

### Process
- Open website (spotifydown.com)
- Wait for .fc-dialog.fc-choice-dialog to be available
- Find and click .fc-button.fc-cta-consent.fc-primary-button
- Loop through links:
    - Find and paste link into .searchInput.bg-spotify-gray.bg-opacity-70.rounded-full.p-3.px-5.w-full.text-gray-300.placeholder\\:text-gray-500.inline-block
    - Find and click .flex.justify-center.items-center.transition.mt-3.w-full.text-center.text-gray-100.cursor-pointer.p-2.rounded-full.bg-button.hover\\:bg-button-active
    - Find and click .w-24.sm\\:w-32.mt-2.p-2.cursor-pointer.bg-button.rounded-full.text-gray-100.hover\\:bg-button-active
    - Find and click .transition.p-2.cursor-pointer.bg-button.hover\\:bg-button-active.text-gray-100.rounded-full
    - Handle file save dialog (remove spotifydown from name, save, etc.)
    - Find and click .text-sm.border-2.cursor-pointer.text-zinc-600.border-zinc-600.hover\\:bg-zinc-500.hover\\:text-black.w-1\\/4.md\\:w-1\\/8.rounded-full.p-1.mx-auto.my-8.text-center
    - Refresh page
    - Repeat loop for all links
"""

# Define the array of links
links = [
    "https://open.spotify.com/track/7HcUEsR0QRtrDaXD55dhJe?si=c8b5853b3b0b4bd2",
    "https://open.spotify.com/track/697LWTeIUFQWu0xJysw2sY?si=0934e838796b4d67",
    "https://open.spotify.com/track/6eOvlMMFOZdpSWaSYMEsem?si=2fb6280a2a5440c1",
    "https://open.spotify.com/track/0XyENlJDsWJTu403wrvs4W?si=ab142cbfa8c9495f",
]

# Function to generate an undetected Selenium WebDriver
def gen_driver():
    try:
        user_agent = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.6167.140 Safari/537.36"
        chrome_options = uc.ChromeOptions()
        chrome_options.add_argument('--headless=new')
        chrome_options.add_argument("--start-maximized")
        chrome_options.add_argument(f"user-agent={user_agent}")
        driver = uc.Chrome(options=chrome_options)
        stealth(driver,
                languages=["en-US", "en"],
                vendor="Google Inc.",
                platform="Win32",
                webgl_vendor="Intel Inc.",
                renderer="Intel Iris OpenGL Engine",
                fix_hairline=True
        )
        return driver
    except Exception as e:
        print("Error in Driver: ", e)

# Generate the WebDriver
driver = gen_driver()

try:
    # Open the website
    driver.get("https://spotifydown.com/")
    wait = WebDriverWait(driver, 20)
    
    for link in links:
        # Wait for page to fully load
        time.sleep(7)

        try:
            # Handle consent dialog
            consent_button = wait.until(EC.element_to_be_clickable(
                (By.CSS_SELECTOR, ".fc-button.fc-cta-consent.fc-primary-button")
            ))
            consent_button.click()
        except:
            pass  # Skip if consent button doesn't appear

        # Find and paste the link into the input field
        input_field = wait.until(EC.presence_of_element_located(
            (By.CSS_SELECTOR, ".searchInput.bg-spotify-gray.bg-opacity-70.rounded-full.p-3.px-5.w-full.text-gray-300.placeholder\\:text-gray-500.inline-block")
        ))
        input_field.clear()
        input_field.send_keys(link)
        
        # Find and click the submit button
        submit_button = wait.until(EC.element_to_be_clickable(
            (By.CSS_SELECTOR, ".flex.justify-center.items-center.transition.mt-3.w-full.text-center.text-gray-100.cursor-pointer.p-2.rounded-full.bg-button.hover\\:bg-button-active")
        ))
        submit_button.click()
        
        # Wait for and click the first "download mp3" button
        download_button_1 = wait.until(EC.element_to_be_clickable(
            (By.CSS_SELECTOR, ".w-24.sm\\:w-32.mt-2.p-2.cursor-pointer.bg-button.rounded-full.text-gray-100.hover\\:bg-button-active")
        ))
        download_button_1.click()
        
        # Wait for and click the second "download mp3" button
        download_button_2 = wait.until(EC.element_to_be_clickable(
            (By.CSS_SELECTOR, ".transition.p-2.cursor-pointer.bg-button.hover\\:bg-button-active.text-gray-100.rounded-full")
        ))
        download_button_2.click()
        
        # Handle file save dialog (if required)
        time.sleep(2)  # Wait for the save dialog
        
        # Get file name
        pyautogui.hotkey("ctrl", "a")
        pyautogui.hotkey("ctrl", "x")
        time.sleep(1)
        file_name = pyperclip.paste()
        file_name = file_name.replace("spotifydown - ", "").strip().title()
        
        pyautogui.write(file_name)  # Type the file name
        pyautogui.press("enter")  # Press "Enter" to save
        
        # Refresh the page for the next link
        driver.get("https://spotifydown.com/")

finally:
    driver.quit()
