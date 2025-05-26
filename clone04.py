#!/usr/bin/env python

import os
import time
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver import ActionChains
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager

# Configuration
BASE_DOWNLOAD_DIR = os.path.abspath("./gdrive_backup")
SESSION_DIR = "/tmp/chrome-user-data"
WAIT_TIME = 3  # Adjust for slower internet

# Setup browser profile
options = webdriver.ChromeOptions()
options.add_argument(f"--user-data-dir={SESSION_DIR}")
options.add_argument("--profile-directory=Default")
options.add_argument("--start-maximized")

options.add_argument('--no-sandbox')
options.add_argument('--disable-dev-shm-usage')
options.add_experimental_option("detach", True)

prefs = {
    "download.prompt_for_download": False,
    "download.directory_upgrade": True,
    "safebrowsing.enabled": True
}
options.add_experimental_option("prefs", prefs)

# driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=options)
driver = webdriver.Chrome(service=Service("/home/yena/Documents/2025/xiao-hu-school-documents/chromedriver-linux64/chromedriver"), options=options)

# Navigate to Google Drive
driver.get("https://drive.google.com/drive/my-drive")
input("Login and press Enter when Drive is ready...")

def sanitize(name):
    return "".join(c for c in name if c.isalnum() or c in " -_").strip()

def is_google_file(tooltip: str):
    """Check if item is a Google Workspace file"""
    google_prefixes = [
        "Google Docs:",
        "Google Sheets:",
        "Google Slides:",
        "Google Forms:",
        "Google Drawings:",
        "Google Sites:"
    ]
    return any(tooltip.startswith(prefix) for prefix in google_prefixes)

def get_google_file_type(tooltip: str):
    """Get the type of Google file for export"""
    if tooltip.startswith("Google Docs:"):
        return "doc"
    elif tooltip.startswith("Google Sheets:"):
        return "sheet"
    elif tooltip.startswith("Google Slides:"):
        return "slide"
    return None

def is_folder(tooltip: str, aria_label: str):
    """Improved folder detection logic"""
    # Skip Google Drive UI elements that aren't real folders
    ui_elements = ['owned by me', 'shared with me', 'recent', 'starred', 'trash', 
                   'my drive', 'computers', 'shared drives', 'priority', 'workspaces']
    
    tooltip_lower = tooltip.lower()
    label_lower = aria_label.lower()
    
    if any(ui_elem in tooltip_lower or ui_elem in label_lower for ui_elem in ui_elements):
        return False
    
    # Check for explicit folder indicators
    if "folder" in tooltip_lower and "google drive folder:" in tooltip_lower:
        return True
    
    # If it's a Google Workspace file, it's definitely not a folder
    if is_google_file(tooltip):
        return False
    
    # If it has a clear file extension, it's likely a file
    common_extensions = ['.pdf', '.doc', '.docx', '.xls', '.xlsx', '.ppt', '.pptx', 
                        '.txt', '.jpg', '.jpeg', '.png', '.gif', '.mp4', '.mp3', 
                        '.zip', '.rar', '.csv', '.json', '.xml', '.html']
    
    if any(ext in tooltip_lower for ext in common_extensions):
        return False
    
    # Default to file if we can't determine (safer than infinite recursion)
    return False

def ensure_download_dir(path):
    prefs = {
        "download.default_directory": path,
        "download.prompt_for_download": False,
        "directory_upgrade": True,
        "safebrowsing.enabled": True
    }
    driver.execute_cdp_cmd("Page.setDownloadBehavior", {"behavior": "allow", "downloadPath": path})

def export_google_file(file_elem, file_type, path, base_name):
    ext_map = {"doc": "docx", "sheet": "xlsx", "slide": "pptx"}
    expected_ext = ext_map[file_type]
    out_file = os.path.join(path, f"{base_name}.{expected_ext}")
    if os.path.exists(out_file):
        print(f"SKIPPED (exists): {out_file}")
        return

    ensure_download_dir(path)

    try:
        # Click to open the document
        ActionChains(driver).key_down(webdriver.common.keys.Keys.CONTROL).click(file_elem).key_up(webdriver.common.keys.Keys.CONTROL).perform()
        time.sleep(WAIT_TIME)

        # Switch to the new tab
        driver.switch_to.window(driver.window_handles[-1])
        
        # Wait for the document to load completely
        time.sleep(5)
        
        # Try multiple selectors for the File menu
        file_menu = None
        selectors = [
            '//div[@aria-label="File"]',
            '//span[text()="File"]',
            '//div[text()="File"]',
            '//*[@id="docs-file-menu"]',
            '//div[@role="menubar"]//div[contains(text(), "File")]',
            '//div[@class="menu-button"]//span[text()="File"]'
        ]
        
        for selector in selectors:
            try:
                file_menu = driver.find_element(By.XPATH, selector)
                break
            except:
                continue
        
        if not file_menu:
            print(f"Could not find File menu for {base_name}")
            return
            
        file_menu.click()
        time.sleep(2)

        # Try to find download option
        download_selectors = [
            '//span[text()="Download"]',
            '//div[text()="Download"]',
            '//*[contains(text(), "Download")]'
        ]
        
        download_menu = None
        for selector in download_selectors:
            try:
                download_menu = driver.find_element(By.XPATH, selector)
                break
            except:
                continue
                
        if not download_menu:
            print(f"Could not find Download option for {base_name}")
            return
            
        # Hover over download to show submenu
        ActionChains(driver).move_to_element(download_menu).perform()
        time.sleep(1)

        # Find the specific format option
        format_selectors = {
            "doc": ['//span[contains(text(), "Microsoft Word")]', '//span[contains(text(), ".docx")]'],
            "sheet": ['//span[contains(text(), "Microsoft Excel")]', '//span[contains(text(), ".xlsx")]'],
            "slide": ['//span[contains(text(), "Microsoft PowerPoint")]', '//span[contains(text(), ".pptx")]']
        }
        
        format_option = None
        for selector in format_selectors.get(file_type, []):
            try:
                format_option = driver.find_element(By.XPATH, selector)
                break
            except:
                continue
                
        if not format_option:
            print(f"Could not find format option for {file_type}: {base_name}")
            return

        format_option.click()
        time.sleep(WAIT_TIME + 3)
        print(f"EXPORTED: {out_file}")
        
    except Exception as e:
        print(f"Error exporting {file_type} '{base_name}': {e}")
    finally:
        # Always try to close the tab and return to main window
        try:
            if len(driver.window_handles) > 1:
                driver.close()
        except:
            pass
        try:
            driver.switch_to.window(driver.window_handles[0])
        except:
            pass

def download_non_google_file(file_elem, path, base_name):
    expected_path = os.path.join(path, base_name)
    if os.path.exists(expected_path):
        print(f"SKIPPED (exists): {expected_path}")
        return

    ensure_download_dir(path)
    try:
        ActionChains(driver).context_click(file_elem).perform()
        time.sleep(1)
        download_btn = driver.find_element(By.XPATH, '//div[text()="Download"]')
        download_btn.click()
        time.sleep(WAIT_TIME)
        print(f"DOWNLOADED: {expected_path}")
    except Exception as e:
        print(f"Download error for {base_name}: {e}")

def process_folder(current_path, depth=0):
    """Process folder with depth tracking to prevent infinite recursion"""
    if depth > 10:  # Safety limit
        print(f"WARNING: Maximum depth reached at {current_path}")
        return
        
    os.makedirs(current_path, exist_ok=True)
    ensure_download_dir(current_path)

    time.sleep(WAIT_TIME)
    file_elems = driver.find_elements(By.XPATH, '//div[@role="main"]//div[@data-tooltip]')

    for elem in file_elems:
        tooltip = elem.get_attribute("data-tooltip")
        label = elem.get_attribute("aria-label")
        if not label or not tooltip:
            continue

        # Skip UI elements
        if any(skip_text in tooltip.lower() for skip_text in ["sort direction", "select", "view", "list view", "grid view"]):
            continue

        print(f"{'  ' * depth}Scanning: {tooltip}")

        clean_name = sanitize(label)
        if not clean_name:  # Skip if name becomes empty after sanitization
            continue
            
        sub_path = os.path.join(current_path, clean_name)

        if is_folder(tooltip, label):
            try:
                print(f"{'  ' * depth}> Entering folder: {clean_name}")
                ActionChains(driver).double_click(elem).perform()
                time.sleep(WAIT_TIME + 2)
                process_folder(sub_path, depth + 1)
                driver.back()
                time.sleep(WAIT_TIME)
            except Exception as e:
                print(f"{'  ' * depth}Folder error for {clean_name}: {e}")
        else:
            file_type = get_google_file_type(tooltip)
            if file_type:
                print(f"{'  ' * depth}> Exporting Google {file_type}: {clean_name}")
                export_google_file(elem, file_type, current_path, clean_name)
            else:
                print(f"{'  ' * depth}> Downloading file: {clean_name}")
                download_non_google_file(elem, current_path, clean_name)

# Start
print("Starting Google Drive backup...")
process_folder(BASE_DOWNLOAD_DIR)
print("All done.")
driver.quit()
