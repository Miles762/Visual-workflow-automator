# Agent B - Runtime AI Workflow System

Agent B receives natural-language tasks at runtime, automatically detects the web app from the task, fetches the base URL from `.env`, and captures UI states for workflow documentation.

**Supports**: Linear, Notion, Asana, Trello, Jira, and any web app (configurable via .env)

## How It Works

1. **Task Analysis**: Agent B extracts the app name from the task (e.g., "Linear", "Notion") using an LLM
2. **URL Resolution**: Fetches the base URL from `.env` file (e.g., `LINEAR_URL`, `NOTION_URL`)
3. **Step Planning**: Uses an LLM planner to break the task into step-by-step actionable points
4. **Browser Automation**: Uses Playwright to navigate and interact with the app
5. **State Detection**: Detects UI changes (URL changes, modals, forms, toasts) after each action
6. **Screenshot Capture**: Takes full-page screenshots at each state change
7. **Documentation**: Creates `README.md` with step-by-step documentation and screenshot references

## URL Access Strategy

**How Agent B accesses URLs:**

1. **Initial URL Only**: Agent B determines the app name from task text, then fetches the base URL from `.env` (e.g., "Linear" → `LINEAR_URL` → `https://linear.app`)
2. **Navigate Once**: Goes to that base URL using Playwright
3. **UI-Based Navigation**: After that, ALL navigation is through UI interactions:
   - Clicking buttons (even if they open modals with no URLs)
   - Filling forms (that may not change URLs)
   - Interacting with dropdowns/overlays
4. **State Capture**: Screenshots are taken at each interaction, regardless of whether the URL changed

**Key Insight**: Many important UI states (modals, forms, dropdowns) don't have URLs. Agent B captures them by:
- Detecting DOM changes (modals appearing, forms showing)
- Taking screenshots at each detected state change
- Not relying on URL changes for navigation

## Setup

```bash
# Install dependencies
pip install -r requirements.txt
playwright install chromium

# Set up environment
cp .env.example .env
# Add your API keys to .env:
- GOOGLE_API_KEY (from https://makersuite.google.com/app/apikey)
- LANGSMITH_API_KEY (from https://smith.langchain.com)


# Run
python main.py
```

## Configuration

Edit `main.py` to add tasks for any web app:

```python
tasks = [
    "How do I create a project in Linear?",
    "How do I filter a database in Notion?",
    "How do I create a task in Asana?",
    "How do I create a board in Trello?",
]
```

The system automatically:
- Detects the app name from the task text
- Fetches the corresponding URL from `.env` (e.g., `LINEAR_URL`, `NOTION_URL`)
- Works with any web app (just add `{APP_NAME}_URL` to `.env`)

## Output Structure

```
outputs/3datasets/
├── linear/
│   └── create_project_in_linear/
│       ├── step_0_app.png
│       ├── step_1_open_dashboard.png
│       ├── step_2_click_create_button.png
│       ├── step_3_fill_form.png
│       ├── step_4_success_modal.png
│       └── README.md
```

## Architecture

- **Agent B**: Single agent that handles everything for any web app
- **LangGraph**: Workflow orchestration with nodes and edges
- **Gemini 2.5 Flash**: Task analysis, app detection, step planning, and action determination
- **LangSmith**: Full observability and tracing (all operations are traced)
- **Playwright**: Browser automation
- **State Detection**: Detects UI changes (modals, forms, dropdowns) regardless of URL
- **Runtime Login**: Prompts for credentials at runtime when login is required
- **Dynamic App Detection**: Extracts app name from task and fetches URL from `.env`

## LangSmith Integration

All workflow steps are automatically traced in LangSmith. View traces at:
https://smith.langchain.com

Set `LANGSMITH_PROJECT` in `.env` to organize traces by project.

## Example Workflow

For task: "How do I create a project in Linear?"

1. Agent B extracts app name: "Linear" from task text
2. Fetches URL from `.env`: `LINEAR_URL` → `https://linear.app`
3. Analyzes task and creates step-by-step plan using LLM
4. Navigates to `https://linear.app` (captures initial screenshot as step 0)
5. **If login required**: Prompts for manual login (user completes in browser)
6. Executes each step:
   - Step 1: Finds and clicks "Create Project" button (modal opens - screenshot captured)
   - Step 2: Fills in project name (form visible - screenshot captured)
   - Step 3: Clicks "Create" (success state - screenshot captured)
7. Creates `README.md` with step-by-step documentation and screenshot references

Each screenshot captures the UI state, even when the URL doesn't change.

## Login

When a web app requires login, the system will:
1. Detect login requirement automatically
2. Pause and wait for you to log in manually in the browser window
3. Continue workflow after you press Enter

This works for any web app (Linear, Notion, Asana, etc.)

