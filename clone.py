#!/usr/bin/env python

import os
import time
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver import ActionChains
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, StaleElementReferenceException, NoSuchElementException
from selenium.webdriver.common.keys import Keys

SCRIPT_VERSION = "24" # Use a string for the version number
print(f"Starting Google Drive Clone Script Version: {SCRIPT_VERSION}")
print("-" * 40) # Add a separator line for clarity

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

# Global variable for the first PDF download attempt diagnostic
_first_pdf_download_attempt = True

# Pre-defined list of UI elements to fully skip
SYSTEM_UI_ELEMENTS_TO_SKIP = [
    'owned by me', 'shared with me', 'recent', 'starred', 'trash', 
    'my drive', 'computers', 'shared drives', 'priority', 'workspaces',
    'sort direction', 'select', 'view', 'list view', 'grid view' 
]

def collect_current_items_in_view(depth: int) -> list[dict]:
    """
    Scans the current view for file/folder items, filters out UI elements and shortcuts,
    and returns a list of attribute dictionaries for processable items.
    """
    print(f"{'  ' * depth}Collecting items in current view...")
    time.sleep(WAIT_TIME) # Allow time for items to load

    current_view_elements = driver.find_elements(By.XPATH, '//div[@role="main"]//div[@data-tooltip]')
    print(f"{'  ' * depth}Found {len(current_view_elements)} potential items in current view scan.")
    
    collected_items_attrs = []
    for elem_idx, initial_elem in enumerate(current_view_elements):
        try:
            tooltip = initial_elem.get_attribute("data-tooltip")
            label = initial_elem.get_attribute("aria-label")

            if not label or not tooltip:
                # print(f"{'  ' * depth}Skipping element with missing tooltip/label (index {elem_idx})")
                continue

            tooltip_lower_for_check = tooltip.lower()
            label_lower_for_check = label.lower() if label else ""

            # Filter UI elements
            if any(skip_text in tooltip_lower_for_check or skip_text in label_lower_for_check for skip_text in SYSTEM_UI_ELEMENTS_TO_SKIP):
                # print(f"{'  ' * depth}Skipping UI element during collection: {tooltip}")
                continue
            
            # Filter Google Drive shortcuts
            if tooltip.startswith("Google Drive shortcut:"):
                # print(f"{'  ' * depth}Skipping Google Drive shortcut during collection: {label}")
                continue
            
            clean_name = sanitize(label) # Sanitize after ensuring it's not a UI/shortcut
            if not clean_name:
                # print(f"{'  ' * depth}Skipping element with empty sanitized name (tooltip: {tooltip}, label: {label})")
                continue
            
            collected_items_attrs.append({
                "tooltip": tooltip,
                "label": label,
                "clean_name": clean_name
            })
        except StaleElementReferenceException:
            print(f"{'  ' * depth}StaleElementReferenceException during item collection for element index {elem_idx}. Skipping this item.")
            continue
        except Exception as e:
            print(f"{'  ' * depth}Unexpected error during item collection for element index {elem_idx}: {e}. Skipping this item.")
            continue
            
    print(f"{'  ' * depth}Collected {len(collected_items_attrs)} processable items from current view.")
    return collected_items_attrs

def escape_xpath_value(value: str) -> str:
    """
    Escapes a string value for safe use in an XPath expression.
    If the value contains no single quotes, it's wrapped in single quotes.
    If the value contains no double quotes, it's wrapped in double quotes.
    If it contains both, it uses concat() to construct the string.
    Example: "foo'bar" becomes concat('foo', "'", 'bar')
    """
    if "'" not in value:
        return f"'{value}'"
    if '"' not in value:
        return f'"{value}"'
    # If both single and double quotes are present, use concat()
    # Example: value = "it's a \"tricky\" string"
    # parts will be ["it", "s a ", tricky, " string"] if split by ' or "
    # We need to handle this carefully. The provided example is specific for splitting by single quote.
    # parts = value.split("'") -> "concat('part1', \"'\", 'part2', ...)"
    
    # Let's refine the concat logic to be more robust for values containing both.
    # The goal is to produce something like concat('part1', "'", 'part2"part2continue', "'", 'part3')
    # or concat("part1", '"', "part2'part2continue", '"', "part3")
    #
    # If we choose to primarily use single quotes for concat parts:
    # Replace all single quotes with , "'" , (comma, single quote in double quotes, comma)
    # then wrap the whole thing in concat('...', result, '...')
    
    # Using the provided robust example:
    # value = "foo'bar\"baz"
    # parts = value.split("'") -> ["foo", "bar\"baz"]
    # result = "concat('foo', \"'\", 'bar\"baz')"
    # This creates concat('foo',"'",'bar"baz') - which is valid XPath.
    parts = value.split("'")
    return "concat('" + "', \"'\", '".join(parts) + "')"

def sanitize(name: str) -> str:
    processed_name = name
    prefix1 = "Google Drive Folder: "
    prefix2 = "Google Drive Folder "
    
    if processed_name.startswith(prefix1):
        processed_name = processed_name[len(prefix1):]
    elif processed_name.startswith(prefix2): # Use elif to ensure only one prefix is stripped if both somehow match (e.g. one is a substring of another)
        processed_name = processed_name[len(prefix2):]
        
    # Existing sanitization logic
    return "".join(c for c in processed_name if c.isalnum() or c in " -_").strip()

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
    tooltip_lower = tooltip.lower()
    # Corrected variable name from label to aria_label and added None check
    label_lower = aria_label.lower() if aria_label else ""
    
    # Check against the global list of UI elements to skip
    # This check helps if is_folder is called in a context where pre-filtering didn't happen,
    # or as a safeguard.
    if any(skip_text in tooltip_lower or skip_text in label_lower for skip_text in SYSTEM_UI_ELEMENTS_TO_SKIP):
        return False # It's a UI element, not a user folder
    
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

    # Explicitly wait for the file_elem to be clickable before any interaction
    wait_clickable_item = WebDriverWait(driver, 20) # 20 second timeout
    try:
        print(f"Waiting for file element '{base_name}' to be clickable (up to 20s).")
        clickable_file_elem = wait_clickable_item.until(EC.element_to_be_clickable(file_elem))
        print(f"File element '{base_name}' is clickable.")
    except TimeoutException:
        print(f"Timeout (20s): File element '{base_name}' was not clickable. Skipping this file.")
        return # Skip this file
    except Exception as e: # Catch other potential errors during clickability wait
        print(f"Error waiting for file element '{base_name}' to be clickable: {e.__class__.__name__} - {e}. Skipping this file.")
        return


    try:
        # Attempt to open the document with a double-click
        print(f"Attempting to open doc '{base_name}' with a double-click.")
        ActionChains(driver).double_click(clickable_file_elem).perform()
        
        # Wait for new tab to open (if any) and switch to it
        # This timeout should be fairly short if a new tab is expected immediately after click.
        # If direct click opens in same tab, number_of_windows_to_be(2) will timeout.
        print(f"Waiting for a new browser window/tab to open for '{base_name}' (up to {WAIT_TIME + 7}s). Current windows: {len(driver.window_handles)}")
        try:
            WebDriverWait(driver, WAIT_TIME + 7).until(EC.number_of_windows_to_be(len(driver.window_handles) +1 if len(driver.window_handles) < 2 else 2 )) # Adapt based on current windows
            print(f"New window/tab detected. Total windows: {len(driver.window_handles)}")
            driver.switch_to.window(driver.window_handles[-1])
            print(f"Switched to new window/tab for '{base_name}'.")
        except TimeoutException:
            print(f"Timeout waiting for a new window/tab after clicking '{base_name}'. Assuming it opened in the same tab or failed to open.")
            # If no new tab, we are still in the main Google Drive tab.
            # The script might not be able to proceed with export if it's same-tab navigation without a page change.
            # For now, let the next step (editor_loaded_locator) try. If that fails, it will be caught.

        # Wait for the document editor to load
        editor_loaded_locator = (By.XPATH, "//*[contains(@class, 'docs-title-inner')] | //*[contains(@class, 'docs-sheet-tab-name')] | //*[contains(@class, 'punch-title-text')] | //*[@id='docs-title-input-label-inner']")
        print(f"Waiting for document editor to load for '{base_name}' (up to 60s)...")
        try:
            WebDriverWait(driver, 60).until(EC.presence_of_element_located(editor_loaded_locator))
            print(f"Document editor loaded for '{base_name}'.")
        except TimeoutException:
            print(f"Timeout (60s) waiting for document editor to load for '{base_name}'. Skipping this file.")
            return

        # Try multiple selectors for the File menu
        file_menu_element = None
        file_menu_selectors = [
            '//div[@aria-label="File"]', 
            '//*[@id="docs-file-menu"]', 
            '//div[text()="File" and @role="menuitem"]', 
            '//span[text()="File" and contains(@class, "menu-button")]'
        ]
        
        # Increased menu item wait time slightly
        wait_clickable_menu = WebDriverWait(driver, 20) 

        print(f"Attempting to find 'File' menu for '{base_name}'...")
        for selector in file_menu_selectors:
            print(f"  Trying File menu selector: {selector}")
            try:
                file_menu_element = wait_clickable_menu.until(EC.element_to_be_clickable((By.XPATH, selector)))
                print(f"  'File' menu found and clickable with selector: {selector}")
                break
            except TimeoutException:
                print(f"  Timeout waiting for 'File' menu with selector: {selector}")
                continue
        
        if not file_menu_element:
            print(f"Could not find or click 'File' menu for '{base_name}' after trying all selectors. Skipping this file.")
            return
            
        file_menu_element.click()
        print("'File' menu clicked.")

        # Wait for "Download" menu item (two-stage: visibility then clickability)
        download_menu_item = None
        download_selectors = [
            '//div[@role="menuitem" and .//span[normalize-space(text())="Download"]]', # Exact text match for "Download" span
            '//span[@aria-label="Download d"]/ancestor::div[@role="menuitem"]',     # Specific aria-label
            # '//div[@role="menuitem" and @id=":68"]', # Dynamic IDs are risky, commented out
            '//div[contains(@class, "goog-menuitem") and .//span[contains(text(), "Download")]]', # Broader fallback
            # Previously used selectors, kept as further fallbacks:
            '//div[@aria-label="Download"]', 
            '//div[text()="Download" and @role="menuitem"]', 
        ]
        
        wait_visible = WebDriverWait(driver, 10)
        # wait_clickable_menu is already defined (20s)

        print(f"Attempting to find 'Download' menu item for '{base_name}'...")
        for selector in download_selectors:
            print(f"  Trying Download menu item selector for visibility: {selector}")
            try:
                dl_item_visible = wait_visible.until(EC.visibility_of_element_located((By.XPATH, selector)))
                print(f"  Download menu item visible with: {selector}. Now waiting for clickability.")
                download_menu_item = wait_clickable_menu.until(EC.element_to_be_clickable(dl_item_visible)) # Pass the visible element
                print(f"  Download menu item clickable with: {selector} (Element: {download_menu_item.tag_name})")
                break 
            except TimeoutException:
                print(f"  Timeout for Download menu item with selector: {selector} (either visibility or clickability).")
                continue
        
        if not download_menu_item:
            print(f"Could not find or make clickable the 'Download' menu item for '{base_name}' after trying all selectors. Skipping this file.")
            return

        # Click the "Download" menu item to open its submenu
        try:
            item_text = download_menu_item.text if hasattr(download_menu_item, 'text') and download_menu_item.text else 'element'
            print(f"Clicking 'Download' menu item: '{item_text}' for '{base_name}'")
            download_menu_item.click()
            time.sleep(1) # Pause for submenu to appear reliably
            print("'Download' menu item clicked.")

            # Use keyboard navigation to select the first format option and press Enter
            actions = ActionChains(driver)
            print("Sending ARROW_DOWN key to select first format option...")
            actions.send_keys(Keys.ARROW_DOWN).perform()
            time.sleep(0.5) # Brief pause for selection to register

            print("Sending ENTER key to activate format option...")
            # Re-initialize ActionChains for the next key press, or chain them.
            # For clarity, creating a new chain or just calling perform on the same is fine.
            ActionChains(driver).send_keys(Keys.ENTER).perform()
            print("ENTER key sent for format option.")

        except Exception as e:
            print(f"Error during 'Download' menu click or keyboard navigation for '{base_name}': {e.__class__.__name__} - {e}. Skipping this file.")
            return

        print(f"Format selection attempted for {base_name}. Waiting for download to initiate...")
        time.sleep(WAIT_TIME + 5) # Increased slightly, download initiation can be slow
        print(f"EXPORTED: {out_file}")
        
    except TimeoutException as te:
        print(f"TimeoutException during export of {file_type} '{base_name}': {te}")
    except Exception as e:
        print(f"Error exporting {file_type} '{base_name}': {e.__class__.__name__} - {e}")
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
    # 1. Skip-if-Exists check at the very beginning
    if os.path.exists(expected_path):
        print(f"SKIPPED (exists): {expected_path}")
        return

    ensure_download_dir(path)

    # 2. Wait for file_elem to be Clickable
    wait_clickable_item = WebDriverWait(driver, 20) # 20s timeout
    clickable_file_elem = None
    try:
        print(f"  Waiting for non-Google file '{base_name}' to be clickable for context-menu (up to 20s).")
        clickable_file_elem = wait_clickable_item.until(EC.element_to_be_clickable(file_elem))
        print(f"  File element '{base_name}' is clickable for context-menu.")
    except TimeoutException:
        print(f"  Timeout (20s): File element '{base_name}' not clickable for context-menu. Skipping.")
        return
    except Exception as e: # Catch other potential errors like StaleElementReferenceException
        print(f"  Error waiting for file '{base_name}' to be clickable: {e.__class__.__name__} - {e}. Skipping.")
        return

    try:
        print(f"  Performing context-click on '{base_name}'.")
        ActionChains(driver).context_click(clickable_file_elem).perform()
        time.sleep(0.5) # Small pause for menu stability
        
        # Use keyboard navigation to select "Download"
        actions = ActionChains(driver)
        print(f"  Sending ARROW_DOWN to navigate context menu for '{base_name}'.")
        # Assuming "Download" is the first or reliably reachable by one ARROW_DOWN.
        # Multiple ARROW_DOWNs can be chained if needed: .send_keys(Keys.ARROW_DOWN).send_keys(Keys.ARROW_DOWN)
        actions.send_keys(Keys.ARROW_DOWN).perform()
        time.sleep(0.5) # Pause for selection to register

        print(f"  Sending ENTER to select 'Download' from context menu for '{base_name}'.")
        ActionChains(driver).send_keys(Keys.ENTER).perform() 
        print("  Context menu 'Download' selected via keyboard.")
        
        # Check for and handle virus scan dialog
        time.sleep(2) # Allow time for dialog to appear
        virus_dialog_handled = False
        try:
            dialog_button_xpath = "//button[@name='ok' and normalize-space(text())='Download anyway']"
            print(f"  Checking for virus scan dialog (up to {WAIT_TIME}s)...")
            
            dialog_confirm_button = WebDriverWait(driver, WAIT_TIME).until(
                EC.element_to_be_clickable((By.XPATH, dialog_button_xpath))
            )
            print("  Virus scan dialog detected. Clicking 'Download anyway'.")
            dialog_confirm_button.click()
            virus_dialog_handled = True
            print("  'Download anyway' clicked.")
        except TimeoutException:
            print("  No virus scan dialog detected, or 'Download anyway' button not found/clickable in time.")
        except Exception as e_dialog:
            print(f"  Exception while trying to handle virus dialog: {e_dialog.__class__.__name__} - {e_dialog}")

        # Wait for download to complete
        global _first_pdf_download_attempt
        is_pdf = base_name.lower().endswith(".pdf") 

        if is_pdf and _first_pdf_download_attempt:
            print(f"  Performing extended wait (20s) for first PDF download: '{base_name}' (Dialog handled: {virus_dialog_handled})")
            time.sleep(20)
            _first_pdf_download_attempt = False
        else:
            effective_wait_time = WAIT_TIME # WAIT_TIME is global
            print(f"  Waiting for download of '{base_name}' to initiate (Dialog handled: {virus_dialog_handled}) (up to {effective_wait_time + 2}s)...")
            time.sleep(effective_wait_time + 2)
        
        print(f"DOWNLOADED: {expected_path}")
            
    except Exception as e:
        print(f"  Download error for '{base_name}': {e.__class__.__name__} - {e}")

def process_folder(current_path, depth=0):
    """Process folder with depth tracking to prevent infinite recursion"""
    print(f"{'  ' * depth}>>> Entering process_folder for path: {current_path} (Depth: {depth})")
    if depth > 10:  # Safety limit
        print(f"{'  ' * depth}WARNING: Maximum depth reached at {current_path}. Returning.")
        return
        
    os.makedirs(current_path, exist_ok=True)
    ensure_download_dir(current_path)

    processed_item_clean_names_this_level = set()
    
    print(f"{'  ' * depth}Performing initial scan of folder: {os.path.basename(current_path) if current_path else 'root'}")
    current_items_to_process_attrs = collect_current_items_in_view(depth)
    print(f"{'  ' * depth}Initial scan found {len(current_items_to_process_attrs)} processable items for {os.path.basename(current_path) if current_path else 'root'}.")
        
    item_idx = 0
    while item_idx < len(current_items_to_process_attrs):
        item_attrs = current_items_to_process_attrs[item_idx]
        # Increment early, as 'continue' might be used, and for clarity with re-scan logic
        item_idx += 1 

        clean_name = item_attrs["clean_name"]
        tooltip = item_attrs["tooltip"]
        label = item_attrs["label"]

        if clean_name in processed_item_clean_names_this_level:
            print(f"{'  ' * depth}Item '{clean_name}' (from list) already processed in this folder context. Skipping.")
            continue
        
        # Safeguard skip for UI/Shortcuts - should have been caught by collect_current_items_in_view
        tooltip_lower = tooltip.lower()
        label_lower = label.lower() if label else ""
        if any(skip_text in tooltip_lower or skip_text in label_lower for skip_text in SYSTEM_UI_ELEMENTS_TO_SKIP):
            print(f"{'  ' * depth}Safeguard skip for UI element: '{clean_name}'. Should have been filtered by collector.")
            processed_item_clean_names_this_level.add(clean_name)
            continue
        if tooltip.startswith("Google Drive shortcut:"):
            print(f"{'  ' * depth}Safeguard skip for Shortcut: '{clean_name}'. Should have been filtered by collector.")
            processed_item_clean_names_this_level.add(clean_name)
            continue

        print(f"{'  ' * depth}Attempting to process item ({item_idx}/{len(current_items_to_process_attrs)}): '{clean_name}' in folder {os.path.basename(current_path) if current_path else 'root'}")
        
        sub_path = os.path.join(current_path, clean_name)

        # Re-locate element before every interaction
        try:
            xpath_safe_tooltip = escape_xpath_value(tooltip)
            xpath_safe_label = escape_xpath_value(label)
            element_xpath = f"//div[@role='main']//div[@data-tooltip={xpath_safe_tooltip} and @aria-label={xpath_safe_label}]"
            
            # Extra logging for root items (depth == 0) when using the combined XPath
            if depth == 0:
                print(f"{'  ' * depth}Attempting to re-locate root item: '{clean_name}' using combined XPath: {element_xpath}")
            
            current_element = driver.find_element(By.XPATH, element_xpath)
            
            if depth == 0:
                print(f"{'  ' * depth}Successfully re-located root item: '{clean_name}'")

        except NoSuchElementException: # Specific exception for not finding the element
            print(f"{'  ' * depth}Could not re-locate element '{clean_name}' (Tooltip: {tooltip}, Label: {label}) using combined XPath.")
            if depth == 0: # Perform diagnostic finds only for root items to limit log verbosity
                print(f"{'  ' * depth}  DIAGNOSTIC FIND for root item '{clean_name}':")
                try:
                    elements_by_tooltip = driver.find_elements(By.XPATH, f"//div[@role='main']//div[@data-tooltip={xpath_safe_tooltip}]")
                    if elements_by_tooltip:
                        print(f"{'  ' * depth}    Found {len(elements_by_tooltip)} element(s) by tooltip only. First 5 labels: {[el.get_attribute('aria-label') for el in elements_by_tooltip[:5]]}")
                    else:
                        print(f"{'  ' * depth}    Found 0 elements by tooltip only.")
                except Exception as diag_e_tooltip:
                    print(f"{'  ' * depth}    Error during diagnostic find by tooltip: {diag_e_tooltip}")

                try:
                    elements_by_label = driver.find_elements(By.XPATH, f"//div[@role='main']//div[@aria-label={xpath_safe_label}]")
                    if elements_by_label:
                        print(f"{'  ' * depth}    Found {len(elements_by_label)} element(s) by label only. First 5 tooltips: {[el.get_attribute('data-tooltip') for el in elements_by_label[:5]]}")
                    else:
                        print(f"{'  ' * depth}    Found 0 elements by label only.")
                except Exception as diag_e_label:
                    print(f"{'  ' * depth}    Error during diagnostic find by label: {diag_e_label}")
            continue # Skip to the next item_attrs in the list
        except Exception as e: # Catch other potential exceptions (e.g., StaleElementReference)
            print(f"{'  ' * depth}An unexpected error ('{e.__class__.__name__}') occurred while re-locating '{clean_name}': {e}. Skipping.")
            continue
            
        # Now determine if it's a folder or file (already skipped UI/shortcuts)
        if is_folder(tooltip, label): # is_folder also uses SYSTEM_UI_ELEMENTS_TO_SKIP as a safeguard
            try:
                print(f"{'  ' * depth}> Entering folder: {clean_name}")
                ActionChains(driver).double_click(current_element).perform()
                time.sleep(WAIT_TIME + 2) # Wait for folder to load
                
                process_folder(sub_path, depth + 1) # RECURSIVE CALL
                
                # After returning from sub-folder, mark this folder as processed for the current level
                processed_item_clean_names_this_level.add(clean_name)
                print(f"{'  ' * depth}Marked sub-folder '{clean_name}' as processed in {os.path.basename(current_path) if current_path else 'root'}.")

                print(f"{'  ' * depth}Finished sub-folder: {clean_name}. Navigating back to parent: {os.path.basename(current_path) if current_path else 'root'}.")
                driver.back()
                
                print(f"{'  ' * depth}  Waiting for parent folder's item list (grid/listbox) to be present after back (up to 15s)...")
                try:
                    WebDriverWait(driver, 15).until(EC.presence_of_element_located((By.XPATH, "//div[@role='grid' or @role='listbox']")))
                    print(f"{'  ' * depth}  Parent folder's item list container is present after back.")
                except TimeoutException:
                    print(f"{'  ' * depth}  Timeout waiting for parent folder's item list container after back.")

                print(f"{'  ' * depth}Refreshing view for parent folder: {os.path.basename(current_path) if current_path else 'root'}.")
                driver.refresh()
                time.sleep(WAIT_TIME) 
                
                print(f"{'  ' * depth}  Waiting for refreshed parent folder's item list (grid/listbox) to be present (up to 15s)...")
                try:
                    WebDriverWait(driver, 15).until(EC.presence_of_element_located((By.XPATH, "//div[@role='grid' or @role='listbox']")))
                    print(f"{'  ' * depth}  Refreshed parent folder's item list container is present.")
                except TimeoutException:
                    print(f"{'  ' * depth}  Timeout waiting for refreshed parent folder's item list container.")
                
                print(f"{'  ' * depth}  Adding extra pause (WAIT_TIME={WAIT_TIME}s) for UI to settle after refresh.")
                time.sleep(WAIT_TIME)
                
                print(f"{'  ' * depth}Re-scanning items in {os.path.basename(current_path) if current_path else 'root'} after returning from sub-folder and refreshing.")
                current_items_to_process_attrs = collect_current_items_in_view(depth) # Re-assign
                print(f"{'  ' * depth}Found {len(current_items_to_process_attrs)} items after refresh. Resetting loop for {os.path.basename(current_path) if current_path else 'root'}.")
                item_idx = 0 # Reset index to re-iterate from the beginning of the *new* list
                continue # Restart the while loop with the fresh list
            except StaleElementReferenceException:
                print(f"{'  ' * depth}StaleElementReferenceException during folder processing for '{clean_name}'. Attempting to recover by going back and rescanning.")
                try:
                    print(f"{'  ' * depth}Attempting to navigate back due to SERE in folder {clean_name}...")
                    print(f"{'  ' * depth}Attempting to navigate back (due to SERE) from folder '{clean_name}'...")
                    driver.back()
                    print(f"{'  ' * depth}  Waiting for item list to stabilize after SERE recovery (up to 15s)...")
                    WebDriverWait(driver, 15).until(EC.presence_of_element_located((By.XPATH, "//div[@role='grid' or @role='listbox']")))
                    time.sleep(WAIT_TIME) # Allow further stabilization
                    # After recovering by going back, we should re-scan the current folder.
                    print(f"{'  ' * depth}Re-scanning items in {os.path.basename(current_path) if current_path else 'root'} after SERE recovery.")
                    current_items_to_process_attrs = collect_current_items_in_view(depth)
                    item_idx = 0 # Reset loop
                    processed_item_clean_names_this_level.clear() # Clear processed for this level as we are re-scanning
                    print(f"{'  ' * depth}Cleared processed items for this level due to SERE recovery and re-scan.")
                    continue
                except Exception as back_e:
                    print(f"{'  ' * depth}Error trying to go back after SERE for '{clean_name}': {back_e}. Skipping item.")
                    processed_item_clean_names_this_level.add(clean_name) # Mark as processed to avoid loop
                    continue # Try next item in the list
            except Exception as e:
                print(f"{'  ' * depth}General folder processing error for '{clean_name}': {e}. Attempting to recover.")
                try:
                    print(f"{'  ' * depth}Attempting to navigate back (due to general error) from folder '{clean_name}'...")
                    driver.back()
                    print(f"{'  ' * depth}  Waiting for item list to stabilize after general error recovery (up to 15s)...")
                    WebDriverWait(driver, 15).until(EC.presence_of_element_located((By.XPATH, "//div[@role='grid' or @role='listbox']")))
                    time.sleep(WAIT_TIME)
                    # After recovering, re-scan the current folder.
                    print(f"{'  ' * depth}Re-scanning items in {os.path.basename(current_path) if current_path else 'root'} after general error recovery.")
                    current_items_to_process_attrs = collect_current_items_in_view(depth)
                    item_idx = 0 # Reset loop
                    processed_item_clean_names_in_this_level.clear() # Clear processed for this level
                    print(f"{'  ' * depth}Cleared processed items for this level due to general error recovery and re-scan.")
                    continue
                except Exception as back_e:
                    print(f"{'  ' * depth}Error trying to go back after general error for '{clean_name}': {back_e}. Skipping item.")
                    processed_item_clean_names_this_level.add(clean_name) # Mark as processed
                    continue # Try next item
        else: # It's a file
            file_type = get_google_file_type(tooltip)
            if file_type:
                print(f"{'  ' * depth}> Exporting Google {file_type}: {clean_name}")
                export_google_file(current_element, file_type, current_path, clean_name)
            else:
                print(f"{'  ' * depth}> Downloading file: {clean_name}")
                download_non_google_file(current_element, current_path, clean_name)
            
            processed_item_clean_names_this_level.add(clean_name)
            print(f"{'  ' * depth}Marked file '{clean_name}' as processed in {os.path.basename(current_path) if current_path else 'root'}.")

    print(f"{'  ' * depth}<<< Exiting process_folder for path: {current_path} (Depth: {depth})")
# Start
print("Starting Google Drive backup...")
process_folder(BASE_DOWNLOAD_DIR)
print("All done.")
driver.quit()
