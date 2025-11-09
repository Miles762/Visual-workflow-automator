from playwright.sync_api import Page
from typing import Dict, Any, List
import time

class StateDetector:
    """Detects UI state changes - works for both URL and non-URL states"""
    
    def __init__(self, page: Page):
        self.page = page
        self.previous_url = ""
        self.previous_state_signature = ""
    
    def detect_state_change(self) -> Dict[str, Any]:
        """
        Detect UI state changes.
        Key insight: Many states don't have URLs (modals, dropdowns, forms).
        We detect them by DOM changes, not just URL changes.
        """
        current_url = self.page.url
        url_changed = current_url != self.previous_url
        
        # Detect UI elements that indicate state changes
        modals = self._detect_modals()
        forms = self._detect_forms()
        dropdowns = self._detect_dropdowns()
        success_indicators = self._detect_success()
        loading = self._detect_loading()
        
        # Determine state type
        state_type = "interaction"
        if url_changed:
            state_type = "navigation"
        elif modals:
            state_type = "modal"
        elif forms:
            state_type = "form"
        elif dropdowns:
            state_type = "dropdown"
        elif success_indicators:
            state_type = "success"
        elif loading:
            state_type = "loading"
        
        # Create state signature (for detecting when state actually changed)
        state_signature = f"{current_url}_{len(modals)}_{len(forms)}_{len(dropdowns)}"
        state_changed = state_signature != self.previous_state_signature
        
        self.previous_url = current_url
        self.previous_state_signature = state_signature
        
        return {
            "state_type": state_type,
            "state_changed": state_changed,
            "url_changed": url_changed,
            "has_modals": len(modals) > 0,
            "has_forms": len(forms) > 0,
            "has_dropdowns": len(dropdowns) > 0,
            "is_success": len(success_indicators) > 0,
            "is_loading": loading,
            "url": current_url,
            "modals": modals,
            "forms": forms
        }
    
    def _detect_modals(self) -> List[str]:
        """Detect visible modals/dialogs (no URL change)"""
        modals = []
        try:
            modal_selectors = [
                '[role="dialog"]',
                '.modal',
                '[class*="Modal"]',
                '[class*="Dialog"]',
                '[class*="Overlay"]',
                '[class*="Popup"]',
                '[data-testid*="modal"]',
                '[data-testid*="dialog"]'
            ]
            
            for selector in modal_selectors:
                elements = self.page.query_selector_all(selector)
                for el in elements:
                    if el.is_visible():
                        # Get modal text to identify it
                        try:
                            text = el.inner_text()[:50]
                            modals.append(f"{selector}: {text}")
                        except:
                            modals.append(selector)
        except:
            pass
        return modals
    
    def _detect_forms(self) -> List[str]:
        """Detect visible forms"""
        forms = []
        try:
            form_elements = self.page.query_selector_all('form, [role="form"]')
            for form in form_elements:
                if form.is_visible():
                    forms.append("form")
        except:
            pass
        return forms
    
    def _detect_dropdowns(self) -> List[str]:
        """Detect open dropdowns/menus"""
        dropdowns = []
        try:
            dropdown_selectors = [
                '[role="menu"]',
                '[role="listbox"]',
                '[class*="Dropdown"]',
                '[class*="Menu"]',
                'select[open]'
            ]
            for selector in dropdown_selectors:
                elements = self.page.query_selector_all(selector)
                for el in elements:
                    if el.is_visible():
                        dropdowns.append(selector)
        except:
            pass
        return dropdowns
    
    def _detect_success(self) -> List[str]:
        """Detect success indicators"""
        success_indicators = []
        try:
            success_texts = ["success", "created", "saved", "completed", "done"]
            for text in success_texts:
                elements = self.page.get_by_text(text, exact=False)
                if elements.count() > 0:
                    success_indicators.append(text)
        except:
            pass
        return success_indicators
    
    def _detect_loading(self) -> bool:
        """Detect loading state"""
        try:
            loading_selectors = [
                '[class*="Loading"]',
                '[class*="Spinner"]',
                '[aria-busy="true"]',
                '[data-testid*="loading"]'
            ]
            for selector in loading_selectors:
                if self.page.query_selector(selector):
                    return True
        except:
            pass
        return False
    
    def wait_for_state_stable(self, timeout: int = 3000):
        """Wait for UI to stabilize after interaction"""
        time.sleep(1.5)  # Wait for animations/transitions

