# Setup Guide

## Prerequisites

- **Python 3.11.14 ** 
  - Check your Python version: `python --version` 

## Quick Start

1. **Install dependencies**:
```bash
pip install -r requirements.txt
playwright install chromium
```

2. **Create `.env` file**:
Create a `.env` file in the root directory with:
```env
# Gemini API
GOOGLE_API_KEY=your_gemini_api_key_here

# LangSmith
LANGSMITH_API_KEY=your_langsmith_api_key_here
LANGSMITH_PROJECT=Visual-workflow-automator
LANGSMITH_TRACING=true

# Browser Settings
HEADLESS=false

```

3. **Get API Keys**:
   - **Gemini API**: Get from https://makersuite.google.com/app/apikey
   - **LangSmith**: Sign up at https://smith.langchain.com (free account) and get API key from settings

4. **Run the system**:
```bash
python main.py
```

## Testing

The system comes with example task which you can ask to it

```python
tasks = [
    "How do I create a project in Linear",
    "Creare a proejct in Linear with tilled "Softlight" ",
    "How do I check inbox in Notion?",
]
```


## Viewing Traces

All operations are automatically traced in LangSmith. Visit:
https://smith.langchain.com

Select your project (`Visual-workflow-automator` by default) to see all workflow executions.

