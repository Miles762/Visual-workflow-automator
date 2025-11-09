from playwright.sync_api import sync_playwright, Browser, Page
from typing import Optional, Dict, Any, List
import time
from src.utils.config import Config

class BrowserManager:
    """Manages browser automation - handles URL access and navigation"""
    
    def __init__(self):
        self.playwright = None
        self.browser: Optional[Browser] = None
        self.page: Optional[Page] = None
    
    def start(self):
        """Start browser instance"""
        self.playwright = sync_playwright().start()
        self.browser = self.playwright.chromium.launch(
            headless=Config.HEADLESS,
            args=['--start-maximized']
        )
        context = self.browser.new_context(
            viewport={'width': 1920, 'height': 1080}
        )
        self.page = context.new_page()
    
    def navigate_to_app(self, app_url: str) -> Dict[str, Any]:
        """
        Navigate to the app's base URL.
        This is the ONLY time we use a URL - after this, all navigation is UI-based.
        Always navigates, even if browser is already on a different page/app.
        """
        try:
            print(f"🌐 Navigating to: {app_url}")
            
            # Always navigate, even if already on a page (important when switching apps)
            # Use 'load' instead of 'networkidle' for more reliable navigation across different apps
            self.page.goto(
                app_url, 
                wait_until="load",  # Changed from "networkidle" for more reliable cross-app navigation
                timeout=Config.BROWSER_TIMEOUT
            )
            
            # Wait for page to fully load and any redirects to complete
            time.sleep(2)  # Wait for initial load
            self.page.wait_for_load_state("networkidle", timeout=10000)  # Wait for network to be idle
            time.sleep(1)  # Additional wait for any dynamic content
            
            # Verify navigation happened
            current_url = self.page.url
            print(f"   ✅ Navigation complete")
            
            # Get final URL after any redirects
            final_url = self.page.url
            
            # Check if login is required
            # PRIORITY: Check requested URL FIRST (before any redirects can happen)
            requested_url_lower = str(app_url).lower()
            url_login_indicators = ["/login", "/signin", "/sign-in", "/auth", "login", "signin"]
            requested_url_has_login = any(indicator in requested_url_lower for indicator in url_login_indicators)
            
            # If requested URL has login indicators, ALWAYS require login
            # This ensures consistent behavior even if app redirects immediately after navigation
            if requested_url_has_login:
                login_required = True
            else:
                # Only check page state if URL doesn't indicate login
                login_required_by_page = self._check_login_required()
                login_required = login_required_by_page
            
            # Ensure login_required is explicitly set (not None)
            login_required = bool(login_required)
            
            return {
                "success": True,
                "url": final_url,
                "title": self.page.title(),
                "login_required": login_required,
                "final_url": final_url  # May redirect after login
            }
        except Exception as e:
            # Even on error, check if URL indicates login
            requested_url_lower = str(app_url).lower()
            url_login_indicators = ["/login", "/signin", "/sign-in", "/auth", "login", "signin"]
            requested_url_has_login = any(indicator in requested_url_lower for indicator in url_login_indicators)
            
            return {
                "success": False,
                "error": str(e),
                "url": app_url,
                "login_required": requested_url_has_login  # Still check for login even on error
            }
    
    def _check_login_required(self) -> bool:
        """Check if page requires login"""
        if not self.page:
            return False
        
        # First check URL - if URL contains login indicators, definitely requires login
        current_url = self.page.url.lower()
        url_login_indicators = ["/login", "/signin", "/sign-in", "/auth", "login", "signin"]
        if any(indicator in current_url for indicator in url_login_indicators):
            return True
        
        # Then check DOM elements (fallback for apps that don't use login URLs)
        login_indicators = [
            'input[type="email"]',
            'input[type="password"]',
            'button:has-text("Sign in")',
            'button:has-text("Log in")',
            'a:has-text("Sign in")',
            'a:has-text("Log in")',
            '[data-testid*="login"]',
            '[data-testid*="signin"]'
        ]
        
        for indicator in login_indicators:
            try:
                if self.page.query_selector(indicator):
                    return True
            except:
                pass
        
        return False
    
    def wait_for_manual_login(self) -> Dict[str, Any]:
        """Wait for user to manually complete login in the browser"""
        try:
            # Wait a moment for page to be ready
            time.sleep(2)
            
            # Generic login success detection
            current_url = self.page.url
            
            # Check if we're still on a login page
            login_indicators = ["login", "signin", "sign-in", "sign-in", "auth"]
            is_on_login_page = any(indicator in current_url.lower() for indicator in login_indicators)
            
            if is_on_login_page:
                # Still on login page, user needs to log in
                return {"success": False, "url": current_url}
            
            # Check for common dashboard/nav elements that appear after login
            dashboard_indicators = [
                'nav',
                '[role="navigation"]',
                '[class*="Dashboard"]',
                '[class*="Sidebar"]',
                '[data-testid*="dashboard"]',
                '[data-testid*="nav"]'
            ]
            
            for indicator in dashboard_indicators:
                try:
                    if self.page.query_selector(indicator):
                        return {"success": True, "url": current_url}
                except:
                    pass
            
            # If URL changed from login page, likely logged in
            # (This is a fallback - most apps redirect after login)
            return {"success": True, "url": current_url}
            
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    def click_element(self, selector: str, strategy: str = "auto") -> Dict[str, Any]:
        """
        Click element using multiple strategies.
        After initial URL, all navigation happens through UI clicks.
        """
        try:
            clicked = False
            timeout_ms = 10000  # Increased timeout to 10 seconds
            error_messages = []
            
            # Strategy 1: Try exact text match
            if strategy == "auto" or strategy == "text":
                try:
                    element = self.page.get_by_text(selector, exact=True).first
                    if element.is_visible(timeout=timeout_ms):
                        element.scroll_into_view_if_needed()
                        element.click(timeout=timeout_ms)
                        clicked = True
                        print(f"   ✓ Clicked by exact text: '{selector}'")
                except Exception as e:
                    error_messages.append(f"Exact text failed: {str(e)[:50]}")
            
            # Strategy 2: Try partial/case-insensitive text match
            if not clicked and (strategy == "auto" or strategy == "text"):
                try:
                    element = self.page.get_by_text(selector, exact=False).first
                    if element.is_visible(timeout=timeout_ms):
                        element.scroll_into_view_if_needed()
                        element.click(timeout=timeout_ms)
                        clicked = True
                        print(f"   ✓ Clicked by partial text: '{selector}'")
                except Exception as e:
                    error_messages.append(f"Partial text failed: {str(e)[:50]}")
            
            # Strategy 2.5: Try semantic/fuzzy matching for common synonyms
            if not clicked and strategy == "auto":
                # Try common semantic variations
                semantic_variants = self._get_semantic_variants(selector)
                for variant in semantic_variants:
                    try:
                        # Try exact match first
                        element = self.page.get_by_text(variant, exact=True).first
                        if element.is_visible(timeout=5000):
                            element.scroll_into_view_if_needed()
                            element.click(timeout=timeout_ms)
                            clicked = True
                            print(f"   ✓ Clicked by semantic variant: '{variant}' (was looking for '{selector}')")
                            break
                    except:
                        try:
                            # Try partial match
                            element = self.page.get_by_text(variant, exact=False).first
                            if element.is_visible(timeout=5000):
                                element.scroll_into_view_if_needed()
                                element.click(timeout=timeout_ms)
                                clicked = True
                                print(f"   ✓ Clicked by semantic variant (partial): '{variant}' (was looking for '{selector}')")
                                break
                        except:
                            continue
            
            # Strategy 3: Try by role (button, link, etc.)
            if not clicked and (strategy == "auto" or strategy == "role"):
                try:
                    # Try as button first
                    element = self.page.get_by_role("button", name=selector, exact=False).first
                    if element.is_visible(timeout=timeout_ms):
                        element.scroll_into_view_if_needed()
                        element.click(timeout=timeout_ms)
                        clicked = True
                        print(f"   ✓ Clicked by button role: '{selector}'")
                except:
                    try:
                        # Try as link
                        element = self.page.get_by_role("link", name=selector, exact=False).first
                        if element.is_visible(timeout=timeout_ms):
                            element.scroll_into_view_if_needed()
                            element.click(timeout=timeout_ms)
                            clicked = True
                            print(f"   ✓ Clicked by link role: '{selector}'")
                    except Exception as e:
                        error_messages.append(f"Role match failed: {str(e)[:50]}")
            
            # Strategy 4: Try by aria-label
            if not clicked and strategy == "auto":
                try:
                    element = self.page.locator(f'[aria-label*="{selector}" i]').first
                    if element.is_visible(timeout=timeout_ms):
                        element.scroll_into_view_if_needed()
                        element.click(timeout=timeout_ms)
                        clicked = True
                        print(f"   ✓ Clicked by aria-label: '{selector}'")
                except Exception as e:
                    error_messages.append(f"Aria-label failed: {str(e)[:50]}")
            
            # Strategy 5: Try by data attributes
            if not clicked and strategy == "auto":
                try:
                    # Try data-testid, data-label, etc.
                    selectors_to_try = [
                        f'[data-testid*="{selector.lower().replace(" ", "-")}"]',
                        f'[data-label*="{selector}" i]',
                        f'button:has-text("{selector}")',
                        f'a:has-text("{selector}")',
                    ]
                    for sel in selectors_to_try:
                        try:
                            element = self.page.locator(sel).first
                            if element.is_visible(timeout=5000):
                                element.scroll_into_view_if_needed()
                                element.click(timeout=timeout_ms)
                                clicked = True
                                print(f"   ✓ Clicked by data attribute: '{selector}'")
                                break
                        except:
                            continue
                except Exception as e:
                    error_messages.append(f"Data attributes failed: {str(e)[:50]}")
            
            # Strategy 6: Try as CSS selector (if it looks like a selector)
            if not clicked and (strategy == "auto" or strategy == "selector"):
                if selector.startswith(('.', '#', '[')) or ' ' in selector:
                    try:
                        element = self.page.locator(selector).first
                        if element.is_visible(timeout=timeout_ms):
                            element.scroll_into_view_if_needed()
                            element.click(timeout=timeout_ms)
                            clicked = True
                            print(f"   ✓ Clicked by CSS selector: '{selector}'")
                    except Exception as e:
                        error_messages.append(f"CSS selector failed: {str(e)[:50]}")
            
            # Strategy 7: Try keyboard shortcut if mentioned (e.g., 'C' for create)
            if not clicked and strategy == "auto":
                # Check if selector mentions a keyboard shortcut
                if 'press' in selector.lower() or 'key' in selector.lower():
                    # Extract key from text like "press the 'C' key"
                    import re
                    key_match = re.search(r"['\"]?([A-Za-z])['\"]?\s*key", selector, re.IGNORECASE)
                    if key_match:
                        key = key_match.group(1).lower()
                        try:
                            self.page.keyboard.press(key)
                            time.sleep(1)
                            clicked = True
                            print(f"   ✓ Pressed keyboard shortcut: '{key}'")
                        except Exception as e:
                            error_messages.append(f"Keyboard shortcut failed: {str(e)[:50]}")
            
            if clicked:
                time.sleep(2)  # Wait for UI to update (modal, form, etc.)
                return {
                    "success": True, 
                    "selector": selector,
                    "current_url": self.page.url
                }
            else:
                # Return detailed error
                error_detail = f"Could not find element: '{selector}'. Tried: {', '.join(error_messages[:3])}"
                return {
                    "success": False, 
                    "error": error_detail,
                    "selector": selector,
                    "tried_strategies": len(error_messages)
                }
                
        except Exception as e:
            return {
                "success": False, 
                "error": f"Exception: {str(e)}", 
                "selector": selector
            }
    
    def fill_input(self, label: str, value: str) -> Dict[str, Any]:
        """Fill input field by label or placeholder"""
        try:
            # Try by label
            try:
                self.page.get_by_label(label, exact=False).fill(value, timeout=5000)
                time.sleep(0.5)
                return {"success": True, "label": label, "value": value}
            except:
                pass
            
            # Try by placeholder
            try:
                self.page.get_by_placeholder(label).fill(value, timeout=5000)
                time.sleep(0.5)
                return {"success": True, "label": label, "value": value}
            except:
                pass
            
            # Try by nearby text
            try:
                label_element = self.page.get_by_text(label, exact=False).first
                if label_element:
                    # Find nearby input
                    input_field = label_element.locator("..").locator("input").first
                    if input_field:
                        input_field.fill(value, timeout=5000)
                        time.sleep(0.5)
                        return {"success": True, "label": label, "value": value}
            except:
                pass
            
            return {"success": False, "error": f"Could not find input for: {label}"}
            
        except Exception as e:
            return {"success": False, "error": str(e), "label": label}
    
    def wait_for_state_change(self, timeout: int = 5000) -> bool:
        """Wait for UI state to change (modal, form, etc.)"""
        time.sleep(1)  # Basic wait for animations
        return True
    
    def get_current_url(self) -> str:
        """Get current page URL (may not change for modals/overlays)"""
        return self.page.url if self.page else ""
    
    def get_page_info(self) -> Dict[str, Any]:
        """Get current page information"""
        if not self.page:
            return {}
        
        return {
            "url": self.page.url,
            "title": self.page.title(),
        }
    
    def is_running(self) -> bool:
        """Check if browser is still running"""
        try:
            if self.browser and self.page:
                # Try to access page to see if it's still valid
                _ = self.page.url
                return True
            return False
        except:
            return False
    
    def _get_semantic_variants(self, selector: str) -> List[str]:
        """Generate semantic variants for common action words - generic approach"""
        selector_lower = selector.lower()
        variants = [selector]  # Always include original
        
        # Generic semantic mappings for common action verbs
        action_synonyms = {
            "create": ["add", "new", "make", "+"],
            "add": ["create", "new", "make", "+"],
            "new": ["create", "add", "make", "+"],
            "edit": ["update", "modify", "change"],
            "update": ["edit", "modify", "change"],
            "delete": ["remove", "trash", "archive"],
            "remove": ["delete", "trash", "archive"],
        }
        
        # Extract action verb and entity
        words = selector_lower.split()
        
        # Find action verb (create, add, new, etc.)
        action_verb = None
        entity = None
        
        for word in words:
            if word in action_synonyms:
                action_verb = word
                # Entity is usually the word after the action verb
                word_idx = words.index(word)
                if word_idx + 1 < len(words):
                    entity = " ".join(words[word_idx + 1:])
                break
        
        # If we found an action verb, generate variants
        if action_verb and entity:
            synonyms = action_synonyms.get(action_verb, [])
            for synonym in synonyms:
                # Generate variants: "Add project", "New project", "+ Project"
                if synonym == "+":
                    variants.append(f"+ {entity.capitalize()}")
                else:
                    variants.append(f"{synonym.capitalize()} {entity}")
                    # Also try with just the entity
                    variants.append(entity.capitalize())
        
        # Also try common patterns
        # If selector contains "project", "issue", "task", "board", "card", etc.
        # Try with just the entity name
        common_entities = ["project", "issue", "task", "board", "card", "page", "database", "workspace", "team"]
        for entity_word in common_entities:
            if entity_word in selector_lower:
                # Try entity alone
                variants.append(entity_word.capitalize())
                # Try with "+" prefix
                variants.append(f"+ {entity_word.capitalize()}")
                break
        
        # Remove duplicates while preserving order
        seen = set()
        result = []
        for v in variants:
            v_lower = v.lower()
            if v_lower not in seen:
                seen.add(v_lower)
                result.append(v)
        
        return result[:5]  # Limit to 5 variants
    
    def close(self):
        """Close browser"""
        try:
            if self.browser:
                self.browser.close()
            if self.playwright:
                self.playwright.stop()
        except:
            pass  # Ignore errors if already closed
        finally:
            self.browser = None
            self.page = None
            self.playwright = None

