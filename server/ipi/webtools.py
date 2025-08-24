import requests
import json
from urllib.parse import urljoin
import utils.auth as auth
session = requests.Session()

# ai_playwright_tools.py
from typing import Optional
from playwright.sync_api import sync_playwright, Page, Locator

_playwright = None
_browser = None
_page: Optional[Page] = None
_playwright_session_settings = {
    "headless": False,
    "timeout_ms": 30000,
    "wait_until": "domcontentloaded",
    "shift_enter_for_newline": True,
    "ignore_tags": ["script", "style"]
}
_KNOWN_ROLES = {
    "button", "link", "textbox", "checkbox", "radio", "combobox", "menuitem", "option",
    "heading", "img", "listitem", "list", "menu", "tab", "tabpanel", "tablist",
    "slider", "switch", "progressbar", "alert", "dialog"
}
_ENGINE_PREFIXES = ("role=", "text=", "css=", "xpath=", "id=", "data-testid=")

def _ensure_page() -> Page:
    """Create (or return) a singleton Playwright browser page."""
    global _playwright, _browser, _page
    if _page is not None:
        return _page
    _playwright = sync_playwright().start()
    _browser = _playwright.chromium.launch(headless=_playwright_session_settings["headless"])
    _page = _browser.new_page()
    return _page

def close_browser() -> str:
    """
    Close the browser session.

    Args:
        None
    """
    global _playwright, _browser, _page
    try:
        if _browser:
            _browser.close()
    finally:
        if _playwright:
            _playwright.stop()
    _playwright = None
    _browser = None
    _page = None
    return "Browser closed"

def _looks_like_css(s: str) -> bool:
    css_chars = set("#.[]>+~:*")
    if any(ch in s for ch in css_chars):
        return True
    return s.islower() and s.replace("-", "").isalnum()

def _strip_quotes(s: str) -> Optional[str]:
    s = s.strip()
    if (len(s) >= 2) and ((s[0] == s[-1] == '"') or (s[0] == s[-1] == "'")):
        return s[1:-1]
    return None

def _locate(target: str, nth: int = 0, exact: Optional[bool] = None) -> Locator:
    page = _ensure_page()
    t = target.strip()

    if t.startswith(_ENGINE_PREFIXES):
        return page.locator(t).nth(nth)

    quoted = _strip_quotes(t)
    if quoted is not None:
        return page.get_by_text(quoted, exact=True if exact is None else exact).nth(nth)

    if _looks_like_css(t):
        loc = page.locator(t)
        try:
            if loc.count() > 0:
                return loc.nth(nth)
        except Exception:
            pass

    try:
        loc = page.get_by_text(t, exact=False if exact is None else exact)
        if loc.count() > 0:
            return loc.nth(nth)
    except Exception:
        pass

    if t in _KNOWN_ROLES:
        return page.get_by_role(t).nth(nth)

    return page.locator(t).nth(nth)

def dynamic_discovery(page) -> str:
    scope = page.locator("body")
    all_elements = []
    candidates = scope.locator("*")
    count = candidates.count()
    ignore_tags = _playwright_session_settings.get("ignore_tags", [])
    seen_content = set()
    
    for i in range(count):
        try:
            handle = candidates.nth(i).element_handle()
            if not handle:
                continue
            
            tag_name = handle.evaluate("el => el.tagName.toLowerCase()")
            if tag_name in ignore_tags:
                continue

            # SOLUTION: Check if element has text-containing children
            has_text_children = handle.evaluate("""
                el => Array.from(el.children).some(child => 
                    child.innerText && child.innerText.trim().length > 0
                )
            """)
            
            # Skip parent elements that just aggregate child text
            if has_text_children:
                continue

            role = handle.get_attribute("role") or tag_name
            text = ' '.join(handle.inner_text().strip().split())
            
            # Check for excessive whitespace bloat
            bloat_chars = text.count('\n') + text.count('\t') + len([m for m in re.finditer(r'  +', text)])
            bloat_percentage = bloat_chars / len(text) if len(text) > 0 else 0
            
            # Skip if empty, duplicate, or too much whitespace bloat
            if (len(text) < 3 or text in seen_content or bloat_percentage > 0.3):
                continue
                
            seen_content.add(text)
            selector = handle.evaluate("""
                el => el.tagName.toLowerCase() + 
                      (el.id ? '#' + el.id : '') + 
                      (el.className ? '.' + el.className.split(' ').slice(0,2).join('.') : '')
            """)
            
            all_elements.append({"role": role, "text": text, "selector": selector, "nth": i})
        except:
            continue

    return all_elements[:40]
# ------------------------------
# Public AI-callable tools
# ------------------------------

def navigate(url: str, wait_until: str = "domcontentloaded", timeout_ms: int = 30000) -> dict:
    """
    Navigate to a webpage and return a dynamic element map. Use this when the user asks about a webpage or provides a URL.

    Args:
        url: The target URL to open.
        wait_until: When navigation is considered complete ("load", "domcontentloaded", "networkidle").
        timeout_ms: Maximum wait time in milliseconds.

    Returns:
        Dictionary with keys:
            url: the page URL
            elements: list of elements with role, text, selector, nth
    """
    page = _ensure_page()
    page.goto(url, wait_until=wait_until, timeout=timeout_ms)
    
    return f"Navigated to {url}. Main elements: {dynamic_discovery(page)}. Use extract_text or extract_html to get full content." 

def click(target: str, nth: int = 0, exact: Optional[bool] = None) -> str:
    """
    Click an element on the page. Good for buttons, links, etc.

    Args:
        target: The element to click (CSS selector, role=..., or text).
        nth: Which matching element to click (0 = first match).
        exact: Whether text matching should be exact.
    """
    loc = _locate(target, nth=nth, exact=exact)
    loc.wait_for(state="visible", timeout=_playwright_session_settings["timeout_ms"])
    loc.click(timeout=_playwright_session_settings["timeout_ms"])
    return f"Clicked: {target} (nth={nth})"

def type_text(target: str, text: str, nth: int = 0,
              exact: Optional[bool] = None, clear: bool = True) -> str:
    """
    Type text into an element. Can be used for forms, inputs, etc.

    Args:
        target: The field to type into (CSS selector, role=..., or text).
        text: The string to type. Add \n to the end of text to simulate pressing Enter.
        nth: Which matching element to target (0 = first match).
        exact: Whether text matching should be exact.
        clear: Whether to clear the field before typing.
    """
    page = _ensure_page()
    loc = _locate(target, nth=nth, exact=exact)
    loc.wait_for(state="visible", timeout=_playwright_session_settings["timeout_ms"])

    if clear:
        loc.fill("", timeout=_playwright_session_settings["timeout_ms"])

    loc.click(timeout=_playwright_session_settings["timeout_ms"])

    if '\n' in text:
        parts = text.split('\n')
        for i, part in enumerate(parts):
            page.keyboard.type(part, delay=0)
            if i < len(parts) - 1:
                if _playwright_session_settings.get("shift_enter_for_newline"):
                    page.keyboard.press("Shift+Enter")
                else:
                    page.keyboard.press("Enter")
        if text.endswith('\n'):
            page.keyboard.press("Enter")
    else:
        page.keyboard.type(text, delay=0)

    return f"Typed into: {target} (nth={nth})"

def extract_text(target: str = "", nth: int = 0, exact: Optional[bool] = None) -> str:
    """
    Get visible text from an element.

    Args:
        target: The element to read text from. If target is "", it will return the text for the whole page.
        nth: Which matching element to read (0 = first match).
        exact: Whether text matching should be exact.
    """
    page = _ensure_page()
    if not target:
        return page.locator('html').inner_text(timeout=_playwright_session_settings["timeout_ms"])
        
    loc = _locate(target, nth=nth, exact=exact)
    loc.wait_for(state="attached", timeout=_playwright_session_settings["timeout_ms"])
    return loc.inner_text(timeout=_playwright_session_settings["timeout_ms"])

def extract_html(target: str = "", nth: int = 0, exact: Optional[bool] = None) -> str:
    """
    Get HTML markup from an element.

    Args:
        target: The element to read HTML from. If target is "", it will return the html for the whole page.
        nth: Which matching element to read (0 = first match).
        exact: Whether text matching should be exact.
    """
    page = _ensure_page()
    if not target:
        return page.content()

    loc = _locate(target, nth=nth, exact=exact)
    loc.wait_for(state="attached", timeout=_playwright_session_settings["timeout_ms"])
    return loc.inner_html(timeout=_playwright_session_settings["timeout_ms"])

def screenshot(target: Optional[str] = None, path: str = "screenshot.png",
               nth: int = 0, exact: Optional[bool] = None) -> str:
    """
    Take a screenshot of the page or an element.

    Args:
        target: Element to screenshot (None for full page).
        path: File path to save the screenshot.
        nth: Which matching element to target (0 = first match).
        exact: Whether text matching should be exact.
    """
    page = _ensure_page()
    if target is None:
        page.screenshot(path=path, full_page=True)
        return f"Page screenshot saved to {path}"
    loc = _locate(target, nth=nth, exact=exact)
    loc.screenshot(path=path)
    return f"Element screenshot saved to {path}"

def wait_for(target: str, state: str = "visible", nth: int = 0, exact: Optional[bool] = None) -> str:
    """
    Wait for an element to reach a given state.

    Args:
        target: The element to wait for.
        state: Desired state ("attached", "detached", "visible", "hidden").
        nth: Which matching element to target (0 = first match).
        exact: Whether text matching should be exact.
    """
    loc = _locate(target, nth=nth, exact=exact)
    loc.wait_for(state=state, timeout=_playwright_session_settings["timeout_ms"])
    return f"Waited for {state}: {target} (nth={nth})"

from duckduckgo_search import DDGS

def web_search(query: str, num_results: int = 5) -> str:
    """
    Performs a web search using DuckDuckGo and returns the top results. This is a broad search and links can be explored further using the navigate tool. Only use this if the user did not provide an URL.

    Args:
        query (str): The search query.
        num_results (int): The number of results to return.

    Returns:
        str: A formatted string of search results or an error message.
    """
    check = auth.authorize("web_search")  # Ensure the user is authorized
    if check:
        return check

    try:
        with DDGS() as ddgs:
            results = [r for r in ddgs.text(query, max_results=num_results)]
        
        if not results:
            return "No results found."

        output = f"Search results for '{query}':\n"
        for i, result in enumerate(results):
            title = result.get('title')
            url = result.get('href')
            body = result.get('body')
            output += f"{i+1}. {title}\n   {url}\n   {body}\n"
        return output
    except Exception as e:
        return f"Error performing search: {e}"

def http_request(method: str, url: str, params: dict = None, data: dict = None, json_data: dict = None, headers: dict = None) -> dict:
    """
    Performs a generic low-level HTTP request. Supports GET, POST, PUT, DELETE, PATCH, HEAD.

    Args:
        method (str): The HTTP method to use.
        url (str): The URL for the request.
        params (dict, optional): URL parameters. Defaults to None.
        data (dict, optional): Form data to send. Defaults to None.
        json_data (dict, optional): JSON data to send. Defaults to None.
        headers (dict, optional): Request headers. Defaults to None.

    Returns:
        dict: A dictionary containing status code, headers, and response body (JSON or text).
    """
    check = auth.authorize("http_request")  # Ensure the user is authorized 
    if check:
        return check
    
    try:
        response = session.request(
            method.upper(),
            url,
            params=params,
            data=data,
            json=json_data,
            headers=headers
        )
        return _format_response(response)
    except Exception as e:
        return {"error": str(e)}

def _format_response(response: requests.Response) -> dict:
    """
    Helper to format a requests.Response object into a dictionary.
    """
    output = {
        "status_code": response.status_code,
        "headers": dict(response.headers),
        "body": None
    }
    try:
        output["body"] = response.json()
    except json.JSONDecodeError:
        output["body"] = response.text
    return output

def download_file(url: str, destination_path: str) -> str:
    """
    Downloads a file from a URL to a specified local path.

    Args:
        url (str): The URL of the file to download.
        destination_path (str): The local path (including filename) to save the file.

    Returns:
        str: A success message or an error message.
    """
    check = auth.authorize("download_file")  # Ensure the user is authorized 
    if check:
        return check
    
    try:
        response = requests.get(url, stream=True)
        response.raise_for_status()
        with open(destination_path, 'wb') as f:
            for chunk in response.iter_content(chunk_size=8192):
                f.write(chunk)
        return f"File downloaded successfully to {destination_path}"
    except Exception as e:
        return f"Error downloading file: {e}"

def manage_session(action: str, key: str = None, value: str = None) -> str:
    """
    Manages the persistent requests.Session and Playwright settings.

    Args:
        action (str): The action to perform. Use action list for available actions.
        key (str, optional): The key for the action.
        value (str, optional): The value for the action.

    Returns:
        str: A string containing the result of the action.

    Actions:
    - 'full reset': Creates a new requests session.
    - 'clear cookies': Clears all requests session cookies.
    - 'set header': Sets a requests session header. Requires 'key' and 'value'.
    - 'remove header': Removes a requests session header. Requires 'key'.
    - 'view cookies': Returns current requests session cookies.
    - 'view headers': Returns current requests session headers.
    - 'set playwright setting': Sets a Playwright setting. Requires 'key' and 'value'.
    - 'view playwright settings': Returns current Playwright settings.
    - 'add_ignore_tag': Adds a tag to the Playwright ignore list. Requires 'value'.
    - 'remove_ignore_tag': Removes a tag from the Playwright ignore list. Requires 'value'.
    - 'list': returns a list of possible actions
    - 'close_browser': closes the browser session
    """
    check = auth.authorize("manage_session")
    if check:
        return check
    
    global session, _playwright_session_settings
    a = action.lower().strip()
    valid_actions = ['full reset', 'clear cookies', 'set header', 'remove header', 'view cookies', 'view headers', 'set playwright setting', 'view playwright settings', 'add_ignore_tag', 'remove_ignore_tag', "list", "close_browser"]

    if a == "list":
        return f"Valid actions are: {valid_actions}"
    elif a == "close_browser":
        return close_browser()
    if a == 'full reset':
        session = requests.Session()
        return "Requests session fully reset."
    elif a == 'clear cookies':
        session.cookies.clear()
        return "Requests session cookies cleared."
    elif a == 'set header':
        if not key or value is None:
            return "Error: Action 'set header' requires a 'key' and 'value'."
        session.headers[key] = value
        return f"Header '{key}' set."
    elif a == 'remove header':
        if not key:
            return "Error: Action 'remove header' requires a 'key'."
        if key in session.headers:
            del session.headers[key]
            return f"Header '{key}' removed."
        else:
            return f"Header '{key}' not found in session."
    elif a == 'view cookies':
        return json.dumps(session.cookies.get_dict())
    elif a == 'view headers':
        return json.dumps(dict(session.headers))
    elif a == 'set playwright setting':
        if not key or value is None:
            return "Error: Action 'set playwright setting' requires a 'key' and 'value'."
        if key in _playwright_session_settings:
            if isinstance(_playwright_session_settings[key], bool):
                _playwright_session_settings[key] = value.lower() in ('true', '1', 'yes')
            elif isinstance(_playwright_session_settings[key], int):
                _playwright_session_settings[key] = int(value)
            else:
                _playwright_session_settings[key] = value
            return f"Playwright setting '{key}' updated."
        else:
            return f"Error: Invalid Playwright setting '{key}'."
    elif a == 'view playwright settings':
        return json.dumps(_playwright_session_settings)
    elif a == 'add_ignore_tag':
        if not value:
            return "Error: Action 'add_ignore_tag' requires a 'value'."
        if value not in _playwright_session_settings["ignore_tags"]:
            _playwright_session_settings["ignore_tags"].append(value)
            return f"Tag '{value}' added to ignore list."
        return f"Tag '{value}' already in ignore list."
    elif a == 'remove_ignore_tag':
        if not value:
            return "Error: Action 'remove_ignore_tag' requires a 'value'."
        if value in _playwright_session_settings["ignore_tags"]:
            _playwright_session_settings["ignore_tags"].remove(value)
            return f"Tag '{value}' removed from ignore list."
        return f"Tag '{value}' not in ignore list."
    else:
        return f"Error: Invalid action '{action}'. Valid actions are: {valid_actions}"
