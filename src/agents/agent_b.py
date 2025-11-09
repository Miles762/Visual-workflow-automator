"""
Agent B: The main agent that receives tasks, navigates, and captures UI states.
This is the ONLY agent - it handles everything from task analysis to execution.
"""
from langchain_google_genai import ChatGoogleGenerativeAI
# from langchain.prompts import ChatPromptTemplate
from langchain_core.prompts import ChatPromptTemplate
from langsmith import traceable
from typing import Dict, Any, List
import json
import re
from src.utils.config import Config
from src.tools.browser_tools import BrowserManager
from src.tools.state_detector import StateDetector
from src.tools.screenshot_manager import ScreenshotManager

class AgentB:
    """
    Agent B: Receives tasks, navigates apps, executes actions, and captures UI states.
    
    URL Access Strategy:
    1. Determines app from task (e.g., "Linear" → https://linear.app)
    2. Navigates to base URL ONCE
    3. After that, all navigation is UI-based (clicks, interactions)
    4. Executes actions (clicks, fills, keyboard) to trigger UI state changes
    5. Captures states at each interaction (including modals/forms with no URLs)
    
    State Capture:
    - Detects state changes through DOM inspection, not just URL changes
    - Captures modals, forms, dropdowns, success states even when URL doesn't change
    - Takes screenshots after each action to capture the resulting UI state
    """
    
    def __init__(self):
        self.llm = ChatGoogleGenerativeAI(
            model="gemini-2.5-flash",
            google_api_key=Config.GOOGLE_API_KEY,
            temperature=0.3
        )
        self.browser = BrowserManager()
        self.state_detector: StateDetector = None
        self.screenshot_manager: ScreenshotManager = None
        self.is_guidance_mode: bool = False  # Track if we're in guidance mode
        self.current_app: str = None  # Track which app is currently loaded in the browser
    
    def _is_final_action_click(self, target: str, step_description: str = "") -> bool:
        """
        Detect if a click is a final action (create, submit, confirm, etc.) based on button text.
        This is used in guidance mode to skip clicks that would execute the final action.
        
        Args:
            target: The button/element text to check
            step_description: Optional step description for additional context
        
        Returns:
            True if this appears to be a final action button, False otherwise
        """
        if not target:
            return False
        
        target_lower = target.lower()
        step_lower = step_description.lower() if step_description else ""
        
        # Keywords that indicate final/execution actions (most dangerous first)
        final_action_keywords = [
            "submit", "confirm", "save", "publish", "send", "post", 
            "finish", "done", "complete", "apply", "update", "share", 
            "invite", "export", "import", "upload", "download", 
            "activate", "deactivate", "enable", "disable", "approve", 
            "reject", "accept", "decline", "proceed", "finalize", 
            "launch", "deploy", "archive", "delete", "remove"
        ]
        
        # Keywords that might be final actions but need context (less dangerous)
        context_dependent_keywords = ["create", "add", "next", "continue", "cancel"]
        
        # Check step description first for context clues
        # If step explicitly mentions "new" (e.g., "click new project"), it's usually opening a modal
        if "new" in step_lower and "new" in target_lower:
            # "New Project" or "New Task" buttons usually open modals - these are safe to click
            return False
        
        # If step mentions opening/viewing (e.g., "open create modal"), it's safe
        opening_indicators = ["open", "view", "show", "see", "go to", "navigate to", "click on"]
        if any(indicator in step_lower for indicator in opening_indicators):
            # But still check if it's explicitly a final action
            if any(keyword in target_lower for keyword in ["submit", "confirm", "save", "publish"]):
                return True
            # If it's "create" but step says "open", it might be safe (opens modal)
            if "create" in target_lower and "open" in step_lower:
                return False
        
        # Check for explicit final action keywords in target
        for keyword in final_action_keywords:
            if keyword in target_lower:
                return True
        
        # Check context-dependent keywords
        for keyword in context_dependent_keywords:
            if keyword in target_lower:
                # For "create", check if it's part of a multi-word phrase that suggests final action
                # e.g., "Create Project" (final) vs "New Project" button (opens modal)
                if keyword == "create":
                    # If step says "create" directly (e.g., "click create project"), it's final
                    if "create" in step_lower and keyword in target_lower:
                        # But exclude if step says "new" (e.g., "click new project button to create")
                        if "new" not in step_lower:
                            return True
                    # If target is just "create" or "create [something]", it's likely final
                    elif target_lower.startswith("create") or target_lower.endswith("create"):
                        return True
                else:
                    # For other context-dependent keywords, check step context
                    if keyword in step_lower:
                        return True
        
        # Check step description for final action patterns
        final_step_patterns = [
            "click create", "click submit", "click confirm", "click save",
            "press create", "press submit", "final step", "last step",
            "to create", "to submit", "to confirm", "to save",
            "then create", "then submit", "then confirm"
        ]
        
        for pattern in final_step_patterns:
            if pattern in step_lower:
                return True
        
        return False
    
    def _is_guidance_mode(self, task_query: str) -> bool:
        """Determine if task is a question (guidance mode) vs command (execution mode)"""
        task_lower = task_query.lower().strip()
        # Questions that need guidance mode
        guidance_indicators = [
            "how do i", "how to", "how can i", "how do you",
            "what is", "what are", "explain", "show me",
            "tell me", "guide me", "help me", "i want to know"
        ]
        return any(task_lower.startswith(indicator) for indicator in guidance_indicators)
    
    @traceable(name="agent_b_analyze_task")
    def analyze_task(self, task_query: str) -> Dict[str, Any]:
        """
        Step 1: Analyze task to determine app and create action plan.
        This includes determining the starting URL from .env based on app name.
        """
        # Extract app name from task using LLM
        app_name = self._extract_app_name(task_query)
        app_url = Config.get_app_url(app_name)
        
        # Determine if this is guidance mode (question) or execution mode (command)
        is_guidance = self._is_guidance_mode(task_query)
        
        mode_context = "guidance" if is_guidance else "execution"
        mode_instruction = """
IMPORTANT MODE: This is GUIDANCE MODE - the task is a QUESTION asking HOW TO do something.
- Click buttons to OPEN modals/views for screenshots
- DO NOT fill form fields (just show them)
- DO NOT submit/create/delete anything
- Mark optional steps clearly (e.g., "Optionally, select...")
- Goal: Show the user what to do, not actually do it
""" if is_guidance else """
IMPORTANT MODE: This is EXECUTION MODE - the task is a COMMAND to actually perform actions.
- Execute all actions including filling forms and submitting
- Create actual entities (projects, tasks, etc.)
- Goal: Actually complete the task
"""
        
        # Build system message using template variables
        # Escape all JSON braces with double braces so ChatPromptTemplate treats them as literals
        system_message = """You are Agent B, an expert at analyzing web app tasks and creating simple, clear step-by-step guides.

For a given task, determine:
1. The web app name mentioned in the task (e.g., "Linear", "Notion", "Asana", "Trello", "Jira")
2. Simple, concise step-by-step action plan

IMPORTANT: The starting URL is {app_url} (fetched from .env configuration).
After reaching that URL, all navigation happens through UI interactions (clicks, form fills), NOT URLs.

CRITICAL: NEVER include "login" or "sign in" as a step. Login is handled automatically by the system before any steps are executed. Start your steps from the point where the user is already logged in and viewing the app.

{mode_instruction}

Keep steps SIMPLE and CONCISE. Each step should be:
- One clear action (e.g., "Click on Projects in the sidebar")
- Focus on ESSENTIAL steps only
- Don't list every possible field or option
- Group related optional actions together
- Use natural, conversational language
- NEVER include login/sign in steps - assume user is already authenticated

Example of good steps:
- "Go to Projects: Click on Projects in the main sidebar on the left"
- "Click New Project: Find and click the New Project button (usually in the top-right corner)"
- "Name Your Project: Type in the Project Name field (this is required)"
- "Click Create: Optionally add description, team, or dates, then click Create Project"

Respond in JSON:
{{
    "app_name": "{app_name}",
    "app_url": "{app_url}",
    "steps": [
        "Go to [section]: Click on [element] in [location]",
        "Click [button]: Find and click [button name] (usually in [location])",
        "[Action]: [Brief description of what to do]",
        "[Optional action]: You can optionally [do this], but to finish, just [final action]"
    ],
    "task_name": "sanitized_task_name",
    "mode": "{mode_context}"
}}

Steps should be:
- Simple and conversational (like explaining to a friend)
- Focus on the main path, not every possible option
- 3-5 steps maximum for most tasks
- Each step is one clear action with context"""
        
        prompt = ChatPromptTemplate.from_messages([
            ("system", system_message),
            ("user", "Task: {task_query}")
        ])
        
        chain = prompt | self.llm
        response = chain.invoke({
            "task_query": task_query,
            "app_name": app_name,
            "app_url": app_url,
            "mode_instruction": mode_instruction,
            "mode_context": mode_context
        })
        
        # Parse JSON response
        content = response.content
        json_match = re.search(r'\{.*\}', content, re.DOTALL)
        
        if json_match:
            try:
                parsed = json.loads(json_match.group())
                # Ensure app_name and app_url are set correctly
                parsed["app_name"] = app_name
                parsed["app_url"] = Config.get_app_url(app_name)
                parsed["is_guidance_mode"] = is_guidance
                return parsed
            except:
                pass
        
        # Fallback
        return self._fallback_parse(task_query, app_name, app_url)
    
    def _extract_app_name(self, task_query: str) -> str:
        """Extract app name from task query using LLM"""
        # First, try simple pattern matching for common apps
        task_lower = task_query.lower()
        common_apps = {
            "linear": "Linear",
            "notion": "Notion",
            "asana": "Asana",
            "trello": "Trello",
            "jira": "Jira",
            "github": "GitHub",
            "slack": "Slack",
            "figma": "Figma",
        }
        
        for key, app_name in common_apps.items():
            if key in task_lower:
                return app_name
        
        # If not found, use LLM to extract
        prompt = ChatPromptTemplate.from_messages([
            ("system", """Extract the web app name from the task description.

Common apps: Linear, Notion, Asana, Trello, Figma, etc.

Return ONLY the app name (capitalized), nothing else. Examples:
- "how to create a project in Linear" → Linear
- "how to filter a database in Notion" → Notion
- "create a task in Asana" → Asana
"""),
            ("user", "Task: {task_query}\n\nApp name:")
        ])
        
        chain = prompt | self.llm
        response = chain.invoke({"task_query": task_query})
        app_name = response.content.strip()
        
        # Clean up response (remove quotes, extra text, markdown)
        app_name = app_name.strip('"\'`*')
        # Extract first capitalized word
        match = re.search(r'\b([A-Z][a-z]+)\b', app_name)
        if match:
            app_name = match.group(1)
        
        # Capitalize if needed
        if app_name and app_name.lower() in common_apps:
            app_name = common_apps[app_name.lower()]
        
        # Return extracted app name, or raise error if not found (let caller handle it)
        if app_name and len(app_name) > 1:
            return app_name
        else:
            # If we still don't have an app name, raise an error with helpful message
            raise ValueError(
                "The task you mentioned isn't linked to any web app. Please provide a task that mentions a web app (e.g., Linear, Notion, Asana, Trello, Jira)."
            )
    
    def _fallback_parse(self, task_query: str, app_name: str = None, app_url: str = None) -> Dict[str, Any]:
        """Fallback parser"""
        if app_name is None:
            # Try one more time to extract app name
            app_name = self._extract_app_name(task_query)
        
        if app_url is None:
            app_url = Config.get_app_url(app_name)
        
        is_guidance = self._is_guidance_mode(task_query)
        
        return {
            "app_name": app_name,
            "app_url": app_url,
            "steps": [
                "Find the relevant button or action",
                "Complete the required form",
                "Submit and capture success"
            ],
            "task_name": task_query.replace(" ", "_").replace("?", "").replace("'", "")[:50],
            "is_guidance_mode": is_guidance
        }
    
    @traceable(name="agent_b_navigate_to_app")
    def navigate_to_app(self, app_url: str, app_name: str = None) -> Dict[str, Any]:
        """
        Step 2: Navigate to the app's base URL.
        This is the ONLY URL navigation - everything else is UI-based.
        - Same app: Navigate to home page (no login prompt)
        - Different app: Navigate to login page (show login prompt)
        """
        # Check if browser is running, if not start it
        if not self.browser.is_running():
            self.browser.start()
        
        # Check if we're on the same app
        is_same_app = self.current_app and app_name and self.current_app.lower().strip() == app_name.lower().strip()
        
        # Debug output
        if self.current_app:
            print(f"   🔍 Current app: '{self.current_app}', New app: '{app_name}', Same: {is_same_app}")
        
        if is_same_app:
            # Same app - navigate to home page (not login page) and skip login prompt
            home_url = Config.get_app_home_url(app_name)
            print(f"🔄 Same app ({app_name}) - navigating to home page for fresh start...")
            result = self.browser.navigate_to_app(home_url)
            # Override login_required to False for same app
            result["login_required"] = False
        else:
            # Different app (or first time) - navigate to login page
            if self.current_app:
                print(f"🔄 Switching from {self.current_app} to {app_name}...")
            
            # Bring browser to front when switching apps to ensure visibility
            try:
                if self.browser.page:
                    self.browser.page.bring_to_front()
            except Exception:
                # Some platforms may not support bring_to_front, continue anyway
                pass
            
            result = self.browser.navigate_to_app(app_url)
        
        # Initialize or reset state detector for new task
        if self.browser.page:
            self.state_detector = StateDetector(self.browser.page)
            # Reset state detector's previous state to ensure fresh detection
            self.state_detector.previous_url = ""
            self.state_detector.previous_state_signature = ""
        
        # Handle login - wait for manual login (only for different apps)
        login_required_value = result.get("login_required", False)
        
        # Only show login prompt if switching to a different app
        if login_required_value is True and not is_same_app:
            app_display = app_name or "the app"
            print(f"\n🔐 Login required for {app_display}.")
            print("📱 Please log in manually in the browser window.")
            print("⏳ Waiting for you to complete login...")
            print("   Press Enter once you're logged in and ready to continue...")
            input()
            print("✅ Continuing with workflow...\n")
        
        # Update current app after navigation (always set if we have app_name, regardless of success)
        if app_name:
            self.current_app = app_name.strip() if app_name else None
            print(f"   ✅ Current app set to: '{self.current_app}'")
        
        return result
    
    @traceable(name="agent_b_execute_step")
    def execute_navigation_step(self, step: str, step_number: int, context: Dict[str, Any]) -> Dict[str, Any]:
        """
        Execute navigation steps and capture UI states.
        In GUIDANCE MODE: Only clicks to show views/modals, doesn't fill forms or submit.
        In EXECUTION MODE: Performs all actions including fills and submits.
        """
        if not self.browser.page:
            return {"success": False, "error": "Browser not initialized"}
        
        # Skip "Navigate to app" step if already done
        if "navigate" in step.lower() and "app" in step.lower():
            return {
                "success": True,
                "skipped": True,
                "message": "Already navigated to app"
            }
        
        import time
        
        # Check if step is optional
        is_optional = "optionally" in step.lower() or "optional" in step.lower()
        
        # First, try to navigate to show relevant view if needed (e.g., navigate to Projects page)
        # This helps ensure we're in the right context before performing actions
        navigation_result = self._navigate_to_show_view(step, None, context)
        if navigation_result.get("navigated"):
            # Wait for navigation to complete
            time.sleep(2)
        
        # In GUIDANCE MODE: Skip steps that are just listing fields or are too granular
        if self.is_guidance_mode:
            step_lower = step.lower()
            
            # Skip optional steps in guidance mode
            if is_optional:
                print(f"   📸 GUIDANCE MODE: Skipping optional step: {step[:50]}...")
                return {
                    "success": True,
                    "skipped": True,
                    "action": {"action_type": "skip", "reason": "optional_guidance"},
                    "explanation": step,
                    "state_info": None,
                    "screenshot": None,
                    "mode": "guidance"
                }
            
            # Skip steps that are just describing/listing fields (not actionable)
            skip_patterns = [
                "contains fields such as",
                "this modal contains",
                "the modal contains",
                "fields such as:",
                "fields include",
                "such as:",
                "includes fields",
                "will appear",
                "for guidance, do not",
                "would fill",
                "would click",
                "would do",
                "- "  # Steps that are just bullet points describing fields
            ]
            
            # If step is just describing fields without an action, skip it
            if any(pattern in step_lower for pattern in skip_patterns):
                print(f"   📸 Skipping descriptive step: {step[:50]}...")
                return {
                    "success": True,
                    "skipped": True,
                    "action": {"action_type": "skip", "reason": "descriptive"},
                    "explanation": step,
                    "state_info": None,
                    "screenshot": None,
                    "mode": "guidance"
                }
        
        # Determine what action to perform
        action = self._determine_action(step, context)
        action_type = action.get("action_type")
        
        # In GUIDANCE MODE: Skip fills and submits (just show, don't execute)
        if self.is_guidance_mode:
            if action_type == "fill":
                # Only capture screenshot if we haven't already shown the form
                # Skip individual field fills - they're already visible in the modal screenshot
                print(f"   📸 GUIDANCE MODE: Form field '{action.get('target', '')}' is visible in the modal (not filling)")
                time.sleep(0.5)
                action_result = {"success": True, "action_type": "fill", "skipped": True, "reason": "guidance_mode"}
            elif action_type == "submit":
                print(f"   📸 GUIDANCE MODE: Submit button is visible in the modal (not submitting)")
                time.sleep(0.5)
                action_result = {"success": True, "action_type": "submit", "skipped": True, "reason": "guidance_mode"}
            elif action_type == "click":
                # In guidance mode, use smart filtering to skip final action clicks
                target = action.get('target', '')
                
                # Smart filtering: Check if this is a final action button based on text
                is_final_action = self._is_final_action_click(target, step)
                
                # Skip if it's a final action (detected by smart filtering)
                if is_final_action:
                    print(f"   📸 GUIDANCE MODE: Skipping click on '{target}' (detected as final action: create/submit/confirm)")
                    time.sleep(0.5)
                    action_result = {"success": True, "action_type": "click", "skipped": True, "reason": "final_action_guidance"}
                else:
                    print(f"   🔄 Showing: click on '{target}'")
                    action_result = self._execute_action(action)
                    if action_result.get("success"):
                        time.sleep(2)
                        print(f"   ✅ View shown")
                    else:
                        # If optional step fails, don't fail the workflow
                        if is_optional:
                            print(f"   ⚠️  Optional step skipped: {action_result.get('error', 'Unknown error')}")
                            action_result = {"success": True, "skipped": True, "reason": "optional_failed"}
                        else:
                            print(f"   ⚠️  Action failed: {action_result.get('error', 'Unknown error')}")
            else:
                action_result = {"success": True, "action_type": action_type}
        else:
            # EXECUTION MODE: Perform all actions
            action_result = None
            if action_type in ["click", "fill", "keyboard", "submit"]:
                target = action.get('target', '')
                if action_type == "fill":
                    value = action.get('value', '')
                    print(f"   🔄 Executing: {action_type} '{target}' with '{value}'")
                else:
                    print(f"   🔄 Executing: {action_type} on '{target}'")
                action_result = self._execute_action(action)
                
                # Wait for UI to stabilize (modal to appear, form to load, etc.)
                time.sleep(2)  # Wait for animations/transitions
                
                # If action was successful, wait a bit more for complex UI changes
                if action_result.get("success"):
                    time.sleep(1)
                    print(f"   ✅ Action succeeded")
                else:
                    # If optional step fails, don't fail the workflow
                    if is_optional:
                        print(f"   ⚠️  Optional step skipped: {action_result.get('error', 'Unknown error')}")
                        action_result = {"success": True, "skipped": True, "reason": "optional_failed"}
                    else:
                        print(f"   ⚠️  Action failed: {action_result.get('error', 'Unknown error')}")
            elif action_type == "wait":
                # For wait actions, just wait
                print(f"   ⏳ Waiting for state change...")
                action_result = self._execute_action(action)
                time.sleep(2)
            else:
                # For navigation-only steps, just detect current state
                action_result = {"success": True, "action_type": "navigation"}
        
        # Detect current state (after action execution)
        state_info = None
        if self.state_detector:
            state_info = self.state_detector.detect_state_change()
            # Print state detection info for debugging
            if state_info:
                state_type = state_info.get("state_type", "unknown")
                url_changed = state_info.get("url_changed", False)
                has_modals = state_info.get("has_modals", False)
                has_forms = state_info.get("has_forms", False)
                is_success = state_info.get("is_success", False)
                
                state_parts = [f"type: {state_type}"]
                if url_changed:
                    state_parts.append("URL changed")
                if has_modals:
                    state_parts.append("modal visible")
                if has_forms:
                    state_parts.append("form visible")
                if is_success:
                    state_parts.append("success detected")
                
                print(f"   📸 State detected: {', '.join(state_parts)}")
        
        # Generate detailed explanation for this step using LLM
        explanation = self._generate_step_explanation(step, step_number, context, state_info)
        
        # Capture screenshot with explanation
        screenshot_info = None
        if self.screenshot_manager and self.browser.page:
            # Determine state type from detected state
            state_type = "interaction"
            if state_info:
                state_type = state_info.get("state_type", "interaction")
                # Override with more specific types
                if state_info.get("has_modals"):
                    state_type = "modal"
                elif state_info.get("has_forms"):
                    state_type = "form"
                elif state_info.get("is_success"):
                    state_type = "success"
                elif state_info.get("url_changed"):
                    state_type = "navigation"
            
            screenshot_info = self.screenshot_manager.capture(
                page=self.browser.page,
                state_type=state_type,
                step_number=step_number,
                metadata={
                    "step": step,
                    "action": action,
                    "action_result": action_result,
                    "explanation": explanation,
                    "state_info": state_info,
                    "url": self.browser.get_current_url()
                }
            )
        
        return {
            "success": action_result.get("success", True) if action_result else True,
            "action": action,
            "action_result": action_result,
            "explanation": explanation,
            "state_info": state_info,
            "screenshot": screenshot_info,
            "mode": "guidance" if self.is_guidance_mode else "execution"
        }
    
    def _navigate_to_show_view(self, step: str, action: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
        """
        Navigate to show the relevant view without performing the action.
        This helps the user see where they need to perform the action.
        """
        # Try to navigate to show relevant sections if possible
        # For example, if step mentions "Projects", try to navigate to projects view
        try:
            # Extract navigation keywords
            step_lower = step.lower()
            
            # Try to find and navigate to relevant sections (read-only navigation)
            if "project" in step_lower:
                # Try to find Projects link and navigate there (just to show the view)
                try:
                    projects_link = self.browser.page.get_by_text("Projects", exact=False).first
                    if projects_link.is_visible(timeout=5000):
                        projects_link.click(timeout=5000)
                        import time
                        time.sleep(2)
                        return {"navigated": True, "location": "Projects view"}
                except:
                    pass
            
            return {"navigated": False, "location": "current view"}
        except Exception as e:
            return {"navigated": False, "error": str(e)}
    
    @traceable(name="agent_b_generate_explanation")
    def _generate_step_explanation(self, step: str, step_number: int, context: Dict[str, Any], state_info: Dict[str, Any] = None) -> str:
        """Generate detailed explanation for a step using LLM"""
        prompt = ChatPromptTemplate.from_messages([
            ("system", """You are a helpful guide that explains how to perform actions in web applications using screenshots.

For each step, create a clear, detailed explanation that:
1. Describes what the user should see in the screenshot
2. Explains exactly what action they need to perform
3. Points out where to find the relevant UI elements (buttons, fields, etc.)
4. Provides helpful tips or alternatives if applicable

Write in a friendly, instructional tone. Be specific about locations (e.g., "top right", "left sidebar", "in the modal").

Example format:
"This screenshot shows the [location]. To complete this step, you should [action]. Look for [element description] in the [location]. You can also [alternative method] if needed."

Keep explanations concise but complete (2-3 sentences)."""),
            ("user", """Step {step_number}: {step}

Current URL: {current_url}
UI State: {ui_state}

Provide a detailed explanation for this step that will help the user understand what they need to do based on the screenshot.""")
        ])
        
        ui_state_desc = "Unknown"
        if state_info:
            state_type = state_info.get("state_type", "unknown")
            ui_state_desc = f"State: {state_type}"
            if state_info.get("has_modals"):
                ui_state_desc += ", Modal visible"
            if state_info.get("has_forms"):
                ui_state_desc += ", Form visible"
        
        chain = prompt | self.llm
        response = chain.invoke({
            "step_number": step_number,
            "step": step,
            "current_url": context.get("current_url", ""),
            "ui_state": ui_state_desc
        })
        
        return response.content.strip()
    
    @traceable(name="agent_b_determine_action")
    def _determine_action(self, step: str, context: Dict[str, Any]) -> Dict[str, Any]:
        """Use LLM to determine what UI action to take - with semantic understanding"""
        prompt = ChatPromptTemplate.from_messages([
            ("system", """Determine the browser action from a step description. Be FLEXIBLE and SEMANTIC.

IMPORTANT: Understand the INTENT, not just exact text. The UI might use different wording.
For example:
- "Create project" or "New project" → look for "Add project", "Create project", "New project", or similar
- "Add issue" → look for "Create issue", "New issue", "Add issue", etc.
- The target should be SEMANTICALLY SIMILAR, not necessarily exact match

Examples:
- Step: "Click the 'New project' button" → Intent: create/add a new project
  Target suggestions: "Add project", "Create project", "New project", "+ Project"
- Step: "Click on 'Create Project'" → Intent: same as above
  Target suggestions: "Add project", "Create project", "New project"
- Step: "Fill in 'Project name'" → target: "Project name" (exact for form fields)
- Step: "Press the 'C' key" → action_type: "keyboard", target: "c"

Return JSON:
{{
    "action_type": "click|fill|wait|submit|keyboard",
    "target": "Primary target text (but be flexible - could be 'Add project' instead of 'Create project')",
    "target_variants": ["list of alternative texts that mean the same thing"],
    "value": "value for fill actions (optional)",
    "strategy": "semantic|text|role|selector",
    "intent": "what the user is trying to accomplish"
}}

For buttons/actions, provide target_variants with synonyms (e.g., ["Add project", "Create project", "New project"]).
For form fields, use exact text.
Use "semantic" strategy when intent matters more than exact text.
"""),
            ("user", "Step: {step}\nCurrent URL: {current_url}")
        ])
        
        chain = prompt | self.llm
        response = chain.invoke({
            "step": step,
            "current_url": context.get("current_url", "")
        })
        
        # Parse response
        content = response.content
        json_match = re.search(r'\{.*\}', content, re.DOTALL)
        
        if json_match:
            try:
                action = json.loads(json_match.group())
                # Clean up target - remove common words
                if action.get("target"):
                    target = action["target"]
                    # Remove quotes if present
                    target = target.strip("'\"")
                    # Remove common prefixes
                    target = re.sub(r'^(click|press|select|choose)\s+(the\s+)?', '', target, flags=re.IGNORECASE)
                    target = re.sub(r'\s+(button|link|field|input)$', '', target, flags=re.IGNORECASE)
                    action["target"] = target.strip()
                
                # Store variants for flexible matching
                if "target_variants" not in action:
                    action["target_variants"] = []
                if action.get("target") and action["target"] not in action["target_variants"]:
                    action["target_variants"].insert(0, action["target"])
                
                # Use semantic strategy if intent is provided
                if action.get("intent") and not action.get("strategy"):
                    action["strategy"] = "semantic"
                
                return action
            except Exception as e:
                print(f"   ⚠️  LLM parse error, using fallback: {str(e)[:50]}")
                pass
        
        # Fallback: Try to extract from step text directly
        target = step
        # Extract text in quotes
        quote_match = re.search(r"['\"]([^'\"]+)['\"]", step)
        if quote_match:
            target = quote_match.group(1)
        else:
            # Extract after keywords
            match = re.search(r"(?:click|press|select|choose)\s+(?:the\s+)?['\"]?([^'\"]+)['\"]?", step, re.IGNORECASE)
            if match:
                target = match.group(1).strip()
        
        # Clean target
        target = target.strip("'\"")
        target = re.sub(r'\s+(button|link|field|input)$', '', target, flags=re.IGNORECASE)
        
        # Generate semantic variants for common actions (generic approach)
        target_variants = [target]
        target_lower = target.lower()
        
        # Generic action synonyms
        action_synonyms = {
            "create": ["add", "new", "make", "+"],
            "add": ["create", "new", "make", "+"],
            "new": ["create", "add", "make", "+"],
        }
        
        # Extract action and entity
        words = target_lower.split()
        for i, word in enumerate(words):
            if word in action_synonyms:
                synonyms = action_synonyms[word]
                entity = " ".join(words[i+1:]) if i+1 < len(words) else ""
                if entity:
                    for synonym in synonyms:
                        if synonym == "+":
                            target_variants.append(f"+ {entity.capitalize()}")
                        else:
                            target_variants.append(f"{synonym.capitalize()} {entity}")
                    # Also add just the entity
                    target_variants.append(entity.capitalize())
                break
        
        # Remove duplicates
        seen = set()
        unique_variants = []
        for v in target_variants:
            if v.lower() not in seen:
                seen.add(v.lower())
                unique_variants.append(v)
        target_variants = unique_variants
        
        # Default: assume click
        if "fill" in step.lower() or "enter" in step.lower() or "type" in step.lower():
            return {"action_type": "fill", "target": target, "value": "", "strategy": "text"}
        elif "wait" in step.lower():
            return {"action_type": "wait", "target": "", "strategy": "text"}
        elif "press" in step.lower() and "key" in step.lower():
            # Extract keyboard shortcut
            key_match = re.search(r"['\"]?([A-Za-z])['\"]?\s*key", step, re.IGNORECASE)
            if key_match:
                return {"action_type": "keyboard", "target": key_match.group(1).lower(), "strategy": "text"}
        else:
            return {"action_type": "click", "target": target, "target_variants": target_variants, "strategy": "semantic"}
    
    def _execute_action(self, action: Dict[str, Any]) -> Dict[str, Any]:
        """Execute the determined action - with semantic flexibility"""
        action_type = action.get("action_type", "click")
        
        if action_type == "click":
            target = action.get("target", "")
            strategy = action.get("strategy", "auto")
            variants = action.get("target_variants", [target] if target else [])
            
            # If semantic strategy, try all variants
            if strategy == "semantic" and len(variants) > 1:
                print(f"   🔍 Trying semantic variants: {variants[:3]}")
                # Try each variant until one works
                last_result = None
                for variant in variants:
                    result = self.browser.click_element(variant, strategy="auto")
                    last_result = result
                    if result.get("success"):
                        return result
                # If all variants failed, return last error
                return last_result if last_result else {"success": False, "error": f"All variants failed for: {target}"}
            else:
                # Use regular strategy
                return self.browser.click_element(target, strategy)
        elif action_type == "keyboard":
            # Handle keyboard shortcuts
            try:
                key = action.get("target", "")
                print(f"   ⌨️  Pressing keyboard key: '{key}'")
                self.browser.page.keyboard.press(key)
                import time
                time.sleep(1)
                return {"success": True, "action": "keyboard", "key": key}
            except Exception as e:
                return {"success": False, "error": f"Keyboard shortcut failed: {str(e)}"}
        elif action_type == "fill":
            # Get value from action or use a sensible default based on target
            fill_value = action.get("value", "")
            if not fill_value:
                # Generate a sensible test value based on the field name
                target = action.get("target", "").lower()
                if "email" in target:
                    fill_value = "test@example.com"
                elif "name" in target or "title" in target:
                    fill_value = "Test " + action.get("target", "Value")
                elif "description" in target:
                    fill_value = "This is a test description for the workflow."
                elif "project" in target:
                    fill_value = "Test Project"
                else:
                    fill_value = "Test Value"
            
            return self.browser.fill_input(
                action.get("target", ""),
                fill_value
            )
        elif action_type == "wait":
            self.browser.wait_for_state_change()
            return {"success": True}
        elif action_type == "submit":
            # Try to find and click submit button
            submit_result = self.browser.click_element("Submit", strategy="text")
            if not submit_result.get("success"):
                submit_result = self.browser.click_element("Create", strategy="text")
            if not submit_result.get("success"):
                submit_result = self.browser.click_element("Save", strategy="text")
            return submit_result
        else:
            return {"success": False, "error": f"Unknown action type: {action_type}"}
