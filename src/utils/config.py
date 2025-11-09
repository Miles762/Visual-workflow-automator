import os
from dotenv import load_dotenv
from pathlib import Path

load_dotenv()

class Config:
    """Configuration management"""
    
    # API Keys
    GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")
    LANGSMITH_API_KEY = os.getenv("LANGSMITH_API_KEY")
    LANGSMITH_PROJECT = os.getenv("LANGSMITH_PROJECT", "dev_spotlight")
    
    
    # Browser Settings
    HEADLESS = os.getenv("HEADLESS", "false").lower() == "true"
    BROWSER_TIMEOUT = int(os.getenv("BROWSER_TIMEOUT", "30000"))
    
    # Output Settings
    BASE_DIR = Path(__file__).parent.parent.parent
    OUTPUT_DIR = BASE_DIR / "outputs" / "datasets"  # Base directory for all outputs
    
    # App URLs mapping - automatically determined, no .env needed
    # URLs are intelligently generated based on app name
    APP_URLS = {
        "LINEAR": "https://linear.app/login",
        "NOTION": "https://www.notion.so/login",
        "ASANA": "https://app.asana.com/login",
    }
    
    @classmethod
    def get_output_dir(cls, app_name: str = None) -> Path:
        """
        Get output directory, optionally organized by app name.
        
        Args:
            app_name: Name of the web app (e.g., "Linear", "Notion")
        
        Returns:
            Path to output directory. If app_name provided, returns:
            outputs/datasets/{app_name_lower}/, otherwise returns:
            outputs/datasets/
        """
        base_output = cls.BASE_DIR / "outputs" / "datasets"
        if app_name:
            # Sanitize app name for filesystem
            app_name_clean = app_name.lower().replace(" ", "_").strip()
            return base_output / app_name_clean
        return base_output
    
    @classmethod
    def get_app_url(cls, app_name: str) -> str:
        """Get URL for an app name dynamically - no .env dependency"""
        app_key = app_name.upper().replace(" ", "_")
        
        # Check APP_URLS dict first
        if app_key in cls.APP_URLS:
            return cls.APP_URLS[app_key]
        
        # Smart fallback: generate URL based on app name
        app_lower = app_name.lower().replace(" ", "")
        
        # Special cases for common apps
        if "trello" in app_lower:
            return "https://trello.com/login"
        elif "jira" in app_lower:
            return "https://id.atlassian.com/login"
        elif "github" in app_lower:
            return "https://github.com/login"
        elif "slack" in app_lower:
            return "https://slack.com/signin#/signin"
        elif "figma" in app_lower:
            return "https://figma.com/login"
        
        # Generic fallback: try common patterns
        # Try with .com first
        return f"https://{app_lower}.com/login"
    
    @classmethod
    def get_app_home_url(cls, app_name: str) -> str:
        """Get home page URL (base URL without /login) for an app"""
        login_url = cls.get_app_url(app_name)
        
        # Remove /login, /signin, etc. from URL to get home page
        home_url = login_url
        for login_path in ["/login", "/signin", "/sign-in", "/auth"]:
            if login_path in home_url:
                home_url = home_url.split(login_path)[0]
                # Also remove query parameters if any
                if "?" in home_url:
                    home_url = home_url.split("?")[0]
                break
        
        return home_url
    
    @classmethod
    def validate(cls):
        """Validate required configuration"""
        if not cls.GOOGLE_API_KEY:
            raise ValueError("GOOGLE_API_KEY not set")
        if not cls.LANGSMITH_API_KEY:
            raise ValueError("LANGSMITH_API_KEY not set")

