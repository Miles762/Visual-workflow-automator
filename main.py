#!/usr/bin/env python3
"""
Main entry point - Agent B UI Capture System
"""
import os
from dotenv import load_dotenv
from langsmith import Client
from src.graph.workflow_graph import AgentBWorkflow
from src.utils.config import Config

load_dotenv()
Config.validate()

# Initialize LangSmith
client = Client(api_key=Config.LANGSMITH_API_KEY)

def main():
    """Main function"""
    print("🤖 Agent B - UI Capture System")
    print("=" * 60)
    print("📱 Supports: Linear, Notion, Asana, and more")
    print(f"📊 LangSmith Project: {Config.LANGSMITH_PROJECT}")
    print(f"🔍 View traces: https://smith.langchain.com")
    print("=" * 60)
    
    workflow = AgentBWorkflow()
    task_count = 0
    
    while True:
        # Prompt for task at runtime
        print("\n" + "=" * 60)
        print("📝 Enter a task (or 'quit'/'exit' to finish):")
        print("   Examples:")
        print("   - 'How to create a project in Linear?'")
        print("   - 'How to see my tasks in Asana ?'")
        print("   - 'Create a project in Linear named 'Project1'")
        print("-" * 60)
        
        task = input("> ").strip()
        
        # Check if user wants to quit
        if task.lower() in ['quit', 'exit', 'q', '']:
            break
        
        if not task:
            print("⚠️  Please enter a valid task or 'quit' to exit.")
            continue
        
        task_count += 1
        print(f"\n📋 Task {task_count}: {task}")
        print("-" * 60)
        
        try:
            result = workflow.run(task)
            
            # Check for error status first
            if result.get("status") == "error" and result.get("error_message"):
                print(f"\n❌ {result.get('error_message')}")
                print("\n" + "-" * 60)
                continue_choice = input("Try another task? (y/n): ").strip().lower()
                if continue_choice not in ['y', 'yes']:
                    break
                continue
            
            print(f"\n✅ Status: {result.get('status')}")
            print(f"📸 Screenshots captured: {len(result.get('screenshots', []))}")
            print(f"📍 Output: {Config.OUTPUT_DIR}/{result.get('task_name', 'unknown')}")
            print(f"🌐 App: {result.get('app_name', 'Unknown')}")
            
            if result.get("error_message"):
                print(f"⚠️  Error: {result.get('error_message')}")
            
            print(f"\n📊 Steps executed:")
            for step in result.get("parsed_steps", []):
                print(f"   • {step}")
            
            # Ask if user wants to continue
            print("\n" + "-" * 60)
            continue_choice = input("Continue with another task? (y/n): ").strip().lower()
            if continue_choice not in ['y', 'yes']:
                break
        
        except KeyboardInterrupt:
            print("\n\n⚠️  Interrupted by user. Exiting...")
            break
        except Exception as e:
            print(f"❌ Error: {str(e)}")
            import traceback
            traceback.print_exc()
            
            # Ask if user wants to continue after error
            print("\n" + "-" * 60)
            continue_choice = input("Continue with another task? (y/n): ").strip().lower()
            if continue_choice not in ['y', 'yes']:
                break
    
    # Close browser when all tasks are done
    try:
        workflow.agent_b.browser.close()
    except:
        pass  # Browser might already be closed
    
    print("\n" + "=" * 60)
    if task_count > 0:
        print(f"✨ Completed {task_count} task(s)!")
    else:
        print("✨ No tasks executed.")
    print(f"🔍 View detailed traces in LangSmith")

if __name__ == "__main__":
    main()

