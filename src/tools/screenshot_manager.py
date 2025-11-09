import os
from pathlib import Path
from playwright.sync_api import Page
from typing import Dict, Any
from src.utils.config import Config
from datetime import datetime

class ScreenshotManager:
    """Manages screenshot capture and organization"""
    
    def __init__(self, task_name: str, app_name: str = None):
        """
        Initialize ScreenshotManager.
        
        Args:
            task_name: Name of the task/workflow
            app_name: Name of the web app (e.g., "Linear", "Notion") for organizing outputs
        """
        self.task_name = self._sanitize_task_name(task_name)
        # Get output directory organized by app name
        base_output_dir = Config.get_output_dir(app_name)
        self.output_dir = base_output_dir / self.task_name
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.screenshot_count = 0
        self.app_name = app_name  # Store app name for README
    
    def _sanitize_task_name(self, name: str) -> str:
        """Sanitize task name for filesystem"""
        return "".join(c if c.isalnum() or c in (' ', '-', '_') else '_' for c in name).strip().replace(" ", "_")
    
    def capture(self, page: Page, state_type: str, step_number: int, metadata: Dict[str, Any] = None) -> Dict[str, Any]:
        """Capture full-page screenshot"""
        self.screenshot_count += 1
        
        # Generate descriptive filename based on step and metadata
        step_desc = self._generate_step_description(state_type, metadata)
        # Use step_N format (no zero-padding for consistency with requirements)
        filename = f"step_{step_number}_{step_desc}.png"
        filepath = self.output_dir / filename
        
        # Capture full page screenshot (includes modals, dropdowns, etc.)
        page.screenshot(path=str(filepath), full_page=True)
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        screenshot_info = {
            "step_number": step_number,
            "state_type": state_type,
            "filename": filename,
            "filepath": str(filepath),
            "relative_path": f"{self.task_name}/{filename}",
            "url": page.url,
            "timestamp": timestamp,
            "metadata": metadata or {},
            "step_description": step_desc
        }
        
        return screenshot_info
    
    def _generate_step_description(self, state_type: str, metadata: Dict[str, Any] = None) -> str:
        """Generate a descriptive name for the step screenshot"""
        if metadata:
            step_text = metadata.get("step", "")
            if step_text:
                # Extract key words from step text
                words = step_text.lower().split()
                # Remove common words
                skip_words = {"to", "the", "a", "an", "in", "on", "at", "for", "and", "or", "click", "fill", "navigate"}
                key_words = [w for w in words if w not in skip_words and len(w) > 2]
                if key_words:
                    # Take first 2-3 meaningful words
                    desc = "_".join(key_words[:3])
                    return desc[:30]  # Limit length
        
        # Fallback to state_type
        return state_type
    
    def create_readme(self, task_description: str, steps: list):
        """Create README for the task"""
        readme_file = self.output_dir / "README.md"
        with open(readme_file, 'w', encoding='utf-8') as f:
            f.write(f"# Task: {task_description}\n\n")
            
            # Add app information
            if self.app_name:
                f.write(f"**Application:** {self.app_name}\n\n")
            
            f.write(f"## Steps Executed\n\n")
            for i, step in enumerate(steps, 1):
                f.write(f"{i}. {step}\n")
            
            f.write(f"\n## Screenshots\n\n")
            f.write(f"Total screenshots captured: {self.screenshot_count}\n\n")
            
            # List all screenshots
            screenshot_files = sorted(self.output_dir.glob("step_*.png"))
            if screenshot_files:
                f.write(f"### Screenshot Files\n\n")
                for screenshot_file in screenshot_files:
                    f.write(f"- `{screenshot_file.name}`\n")

