import os
import sys
from datetime import datetime
from google import genai

TIMESTAMP_FILE = os.path.expanduser("~/.fantasy_last_run")

def should_run_today() -> bool:
    today_str = datetime.now().strftime("%Y-%m-%d")
    if os.path.exists(TIMESTAMP_FILE):
        with open(TIMESTAMP_FILE, "r") as f:
            last_date = f.read().strip()
            if last_date == today_str:
                return False
    return True

def mark_completed():
    today_str = datetime.now().strftime("%Y-%m-%d")
    with open(TIMESTAMP_FILE, "w") as f:
        f.write(today_str)

def main():
    if not should_run_today():
        print("Already ran fantasy check today. Exiting.")
        sys.exit(0)

    print("Running fantasy manager catch-up...")
    
    # Initialize Gemini client
    client = genai.Client()

    # Pass instructions to execute the checks via your MCP tools or direct helper functions
    prompt = """
    Review my Sleeper fantasy teams:
    1. NBA: Check if any starter played their final scheduled game of the week (Game 3/3 or 4/4) and lock it in.
       If an unlocked starter has no game today, swap in a bench player who does play.
    2. NFL: Verify starting lineup matches highest projected points.
    3. If today is Tuesday, log any waiver free-agent targets.
    """

    # Trigger model with your registered tools
    response = client.models.generate_content(
        model="gemini-2.5-flash",
        contents=prompt,
    )
    print("Run response:", response.text)
    mark_completed()

if __name__ == "__main__":
    main()