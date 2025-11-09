from typing import TypedDict, List, Optional, Dict, Any
from typing_extensions import Annotated
import operator

class WorkflowState(TypedDict):
    """State for Agent B's UI capture workflow"""
    # Input
    task_query: str  # Task from Agent A (e.g., "How do I create a project in Linear?")
    
    # Task Analysis
    app_name: Optional[str]  # Detected app name
    app_url: Optional[str]  # Starting URL (e.g., https://linear.app)
    parsed_steps: Annotated[List[str], operator.add]  # Actionable steps
    
    # Navigation State
    current_step: int
    current_url: Optional[str]
    navigation_history: Annotated[List[Dict], operator.add]
    
    # UI State Detection
    detected_states: Annotated[List[Dict], operator.add]
    screenshots: Annotated[List[Dict], operator.add]
    
    # Status
    status: str  # "analyzing", "navigating", "capturing", "completed", "error"
    error_message: Optional[str]
    
    # Metadata
    workflow_id: str
    task_name: str  # Sanitized for folder structure

