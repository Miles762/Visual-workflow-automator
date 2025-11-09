"""
LangGraph workflow for Agent B's UI capture system
"""
from langgraph.graph import StateGraph, END
from typing import Dict, Any
from langsmith import traceable
from src.state.workflow_state import WorkflowState
from src.agents.agent_b import AgentB
from src.tools.screenshot_manager import ScreenshotManager
import uuid

class AgentBWorkflow:
    """LangGraph workflow orchestration for Agent B"""
    
    def __init__(self):
        self.agent_b = AgentB()
        self.graph = self._build_graph()
    
    def _build_graph(self) -> StateGraph:
        """Build the LangGraph workflow"""
        
        workflow = StateGraph(WorkflowState)
        
        # Add nodes
        workflow.add_node("analyze_task", self.analyze_task_node)
        workflow.add_node("navigate_to_app", self.navigate_to_app_node)
        workflow.add_node("execute_steps", self.execute_steps_node)
        workflow.add_node("finalize", self.finalize_node)
        
        # Define edges
        workflow.set_entry_point("analyze_task")
        # Add conditional edge from analyze_task to handle errors
        workflow.add_conditional_edges(
            "analyze_task",
            self._check_analyze_result,
            {
                "error": "finalize",
                "continue": "navigate_to_app"
            }
        )
        workflow.add_edge("navigate_to_app", "execute_steps")
        workflow.add_conditional_edges(
            "execute_steps",
            self.should_continue,
            {
                "continue": "execute_steps",
                "complete": "finalize",
                "error": "finalize"
            }
        )
        workflow.add_edge("finalize", END)
        
        return workflow.compile()
    
    def _check_analyze_result(self, state: WorkflowState) -> str:
        """Check if analyze_task_node resulted in an error"""
        status = state.get("status", "")
        if status == "error":
            return "error"
        return "continue"
    
    @traceable(name="analyze_task_node")
    def analyze_task_node(self, state: WorkflowState) -> Dict[str, Any]:
        """Node: Analyze task and create plan"""
        task_query = state["task_query"]
        
        try:
            analysis = self.agent_b.analyze_task(task_query)
            
            # Set guidance mode flag in agent
            is_guidance = analysis.get("is_guidance_mode", False)
            self.agent_b.is_guidance_mode = is_guidance
            
            if is_guidance:
                print("📚 GUIDANCE MODE: Showing how to complete the task (not executing)")
            
            return {
                "app_name": analysis.get("app_name"),
                "app_url": analysis.get("app_url"),
                "parsed_steps": analysis.get("steps", []),
                "task_name": analysis.get("task_name", task_query.replace(" ", "_")[:50]),
                "workflow_id": str(uuid.uuid4()),
                "current_step": 0,
                "status": "analyzing"
            }
        except ValueError as e:
            # Handle app name extraction errors specifically
            error_msg = str(e)
            if "isn't linked to any web app" in error_msg or "Could not determine app name" in error_msg:
                return {
                    "status": "error",
                    "error_message": error_msg,
                    "app_name": None,
                    "app_url": None,
                    "parsed_steps": [],
                    "task_name": task_query.replace(" ", "_")[:50],
                    "workflow_id": str(uuid.uuid4()),
                    "current_step": 0
                }
            else:
                # Re-raise other ValueErrors
                raise
        except Exception as e:
            # Re-raise other exceptions
            raise
    
    @traceable(name="navigate_to_app_node")
    def navigate_to_app_node(self, state: WorkflowState) -> Dict[str, Any]:
        """Node: Navigate to app's base URL"""
        app_url = state.get("app_url", "")
        app_name = state.get("app_name", "")
        
        try:
            result = self.agent_b.navigate_to_app(app_url, app_name)
            
            # Initialize screenshot manager with app_name for organization
            task_name = state.get("task_name", "unknown_task")
            app_name = state.get("app_name", "")
            self.agent_b.screenshot_manager = ScreenshotManager(task_name, app_name)
            
            # Generate explanation for initial state
            task_query = state.get("task_query", "")
            initial_explanation = f"This is the initial view of {app_name}. You have successfully navigated to the application. This screenshot shows the starting point before performing any actions."
            
            # Capture initial state
            if self.agent_b.browser.page and self.agent_b.screenshot_manager:
                screenshot_info = self.agent_b.screenshot_manager.capture(
                    page=self.agent_b.browser.page,
                    state_type="initial",
                    step_number=0,
                    metadata={
                        "url": app_url, 
                        "title": result.get("title", ""),
                        "explanation": initial_explanation,
                        "step": "Navigate to the app"
                    }
                )
                return {
                    "status": "navigating",
                    "current_url": result.get("url", app_url),
                    "screenshots": [screenshot_info],
                    "navigation_history": [{
                        "action": "navigate_to_app",
                        "url": app_url,
                        "result": result
                    }]
                }
            
            return {
                "status": "navigating",
                "current_url": result.get("url", app_url)
            }
        except Exception as e:
            return {
                "status": "error",
                "error_message": str(e)
            }
    
    def _is_optional_step(self, step_description: str) -> bool:
        """
        Single source of truth for optional step detection.
        Checks if a step description contains optional indicators.
        
        Args:
            step_description: The step description text to check
        
        Returns:
            True if step is marked as optional, False otherwise
        """
        if not step_description:
            return False
        step_lower = step_description.lower()
        return "optionally" in step_lower or "optional" in step_lower
    
    def _determine_step_status(self, result: Dict[str, Any], step_description: str, current_step: int) -> Dict[str, Any]:
        """
        Unified error handling for both guidance and execution modes.
        Returns status updates based on action result and step characteristics.
        
        Args:
            result: Result from execute_navigation_step
            step_description: The step description text
            current_step: Current step index (1-based for display)
        
        Returns:
            Dict with 'status' and optionally 'error_message'
        """
        action_result = result.get("action_result", {})
        is_skipped = result.get("skipped", False) or action_result.get("skipped", False)
        
        # Check if step is optional from multiple sources
        is_optional_from_step = self._is_optional_step(step_description)
        is_optional_from_result = action_result.get("reason") in ["optional_failed", "guidance_mode", "optional_field"]
        is_optional = is_optional_from_step or is_optional_from_result
        
        mode = result.get("mode", "execution")
        success = result.get("success", True)
        
        # In guidance mode, skipped actions are expected and OK
        if mode == "guidance":
            if is_skipped or is_optional:
                return {"status": "capturing"}
        
        # In execution mode, skipped actions might need checking
        if mode == "execution":
            if is_skipped and not is_optional:
                # Non-optional skipped action - might be an issue, but continue for now
                return {"status": "capturing"}
        
        # Handle failed actions
        if not success:
            if is_optional:
                # Optional step failed - that's OK, continue
                return {"status": "capturing"}
            else:
                # Non-optional step failed - this is an error
                error_msg = (
                    action_result.get("error") or 
                    result.get("error") or 
                    result.get("message") or 
                    "Step execution failed"
                )
                
                # Build error message
                error_message = f"Step {current_step}: {error_msg}"
                
                # Add action details for execution mode (useful for debugging)
                if mode == "execution":
                    action_info = result.get("action", {})
                    if action_info:
                        action_type = action_info.get('action_type', 'unknown')
                        target = action_info.get('target', 'unknown')
                        error_message += f" (Action: {action_type} on '{target}')"
                
                return {
                    "status": "error",
                    "error_message": error_message
                }
        
        # Success case
        return {"status": "capturing"}
    
    @traceable(name="execute_steps_node")
    def execute_steps_node(self, state: WorkflowState) -> Dict[str, Any]:
        """Node: Execute navigation steps"""
        parsed_steps = state.get("parsed_steps", [])
        current_step = state.get("current_step", 0)
        
        if current_step >= len(parsed_steps):
            return {"status": "completed"}
        
        step = parsed_steps[current_step]
        context = {
            "current_url": state.get("current_url", ""),
            "app_url": state.get("app_url", "")
        }
        
        try:
            result = self.agent_b.execute_navigation_step(step, current_step + 1, context)
            
            updates = {
                "current_step": current_step + 1,
                "current_url": self.agent_b.browser.get_current_url(),
                "navigation_history": [{
                    "step": current_step + 1,
                    "step_description": step,
                    "result": result
                }]
            }
            
            if "screenshot" in result and result["screenshot"]:
                updates["screenshots"] = [result["screenshot"]]
            
            if "state_info" in result and result["state_info"]:
                updates["detected_states"] = [result["state_info"]]
            
            # Unified error handling for both guidance and execution modes
            step_description = parsed_steps[current_step] if current_step < len(parsed_steps) else ""
            status_updates = self._determine_step_status(result, step_description, current_step + 1)
            updates.update(status_updates)
            
            return updates
            
        except Exception as e:
            return {
                "status": "error",
                "error_message": str(e),
                "current_step": current_step + 1
            }
    
    @traceable(name="finalize_node")
    def finalize_node(self, state: WorkflowState) -> Dict[str, Any]:
        """Node: Finalize and cleanup - always creates README.md"""
        try:
            # Always create README.md if we have screenshots or completed workflow
            if (self.agent_b.browser.page and 
                self.agent_b.screenshot_manager):
                
                screenshots = state.get("screenshots", [])
                status = state.get("status", "")
                
                # Create README.md if we have screenshots or workflow completed/capturing
                if screenshots or status in ["completed", "capturing"]:
                    # Create README.md for the task
                    self.agent_b.screenshot_manager.create_readme(
                        state.get("task_query", ""),
                        state.get("parsed_steps", [])
                    )
                
                # Only capture final screenshot if workflow completed successfully
                if status == "completed":
                    final_screenshot = self.agent_b.screenshot_manager.capture(
                        page=self.agent_b.browser.page,
                        state_type="final",
                        step_number=999,
                        metadata={"status": "completed"}
                    )
            
            # Don't close browser here - keep it open for multiple tasks
            # Browser will be closed at the end of main() when user is done
            
            return {
                "status": "completed" if state.get("status") != "error" else "error"
            }
        except Exception as e:
            return {
                "status": "error",
                "error_message": f"Finalization error: {str(e)}"
            }
    
    def should_continue(self, state: WorkflowState) -> str:
        """Conditional edge function"""
        status = state.get("status", "")
        current_step = state.get("current_step", 0)
        parsed_steps = state.get("parsed_steps", [])
        
        if status == "error":
            return "error"
        elif current_step >= len(parsed_steps):
            return "complete"
        else:
            return "continue"
    
    def run(self, task_query: str) -> WorkflowState:
        """Run the workflow"""
        initial_state: WorkflowState = {
            "task_query": task_query,
            "app_name": None,
            "app_url": None,
            "parsed_steps": [],
            "current_step": 0,
            "navigation_history": [],
            "current_url": None,
            "detected_states": [],
            "screenshots": [],
            "status": "analyzing",
            "error_message": None,
            "workflow_id": "",
            "task_name": ""
        }
        
        result = self.graph.invoke(initial_state)
        return result
