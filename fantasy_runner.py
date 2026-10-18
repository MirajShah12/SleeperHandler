import os
import sys
import asyncio
import httpx
from google import genai
from google.genai import types
from playwright.async_api import async_playwright

# --- CONFIGURATION ---
# Set your Sleeper username here
SLEEPER_USERNAME = os.getenv("SLEEPER_USERNAME")
SLEEPER_BASE = "https://api.sleeper.app/v1"
STATE_FILE = "storage_state.json"

# --- SLEEPER READ TOOLS ---

async def get_user_leagues(sport: str = "nba", season: str = "2026") -> str:
    """Fetches user ID and all active league IDs and names for the user."""
    async with httpx.AsyncClient() as client:
        u_res = await client.get(f"{SLEEPER_BASE}/user/{SLEEPER_USERNAME}")
        if u_res.status_code != 200:
            return f"User {SLEEPER_USERNAME} not found."
        user_id = u_res.json().get("user_id")

        l_res = await client.get(f"{SLEEPER_BASE}/user/{user_id}/leagues/{sport}/{season}")
        leagues = l_res.json()
        if not leagues:
            return f"No {sport} leagues found for season {season}."
        return "\n".join([f"League: {l['name']} | ID: {l['league_id']}" for l in leagues])

async def get_league_matchups(league_id: str, week: int) -> str:
    """Fetches current matchup data, starters, and points for a given week."""
    async with httpx.AsyncClient() as client:
        res = await client.get(f"{SLEEPER_BASE}/league/{league_id}/matchups/{week}")
        if res.status_code != 200:
            return f"Failed to fetch matchups for league {league_id}."
        return str(res.json()[:4])

async def get_trending_waivers(sport: str = "nba") -> str:
    """Fetches trending added free agents across Sleeper."""
    async with httpx.AsyncClient() as client:
        res = await client.get(f"{SLEEPER_BASE}/players/{sport}/trending/add")
        if res.status_code != 200:
            return "Failed to fetch trending players."
        return str(res.json()[:10])

# --- SLEEPER ACTION TOOLS (PLAYWRIGHT) ---

async def lock_in_player(league_id: str, player_name: str) -> str:
    """Clicks 'Lock In' on the Sleeper web UI for a starter whose score should be locked."""
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(storage_state=STATE_FILE if os.path.exists(STATE_FILE) else None)
        page = await context.new_page()

        await page.goto(f"https://sleeper.com/leagues/{league_id}/matchup")
        await page.wait_for_timeout(3500)

        player_row = page.locator(f"xpath=//div[contains(., '{player_name}')]")
        lock_btn = player_row.locator("button:has-text('Lock')").first

        if await lock_btn.is_visible():
            await lock_btn.click()
            await page.wait_for_timeout(1500)
            await browser.close()
            return f"Successfully locked in {player_name}."

        await browser.close()
        return f"Could not find an active Lock button for {player_name}."

async def swap_lineup(league_id: str, starter_out: str, bench_in: str) -> str:
    """Swaps a bench player into the starting lineup."""
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(storage_state=STATE_FILE if os.path.exists(STATE_FILE) else None)
        page = await context.new_page()

        await page.goto(f"https://sleeper.com/leagues/{league_id}/team")
        await page.wait_for_timeout(3500)

        swap_btn = page.locator(f"xpath=//div[contains(., '{starter_out}')]//button[contains(., 'Swap')]").first
        if await swap_btn.is_visible():
            await swap_btn.click()
            await page.wait_for_timeout(1000)
            await page.locator(f"text='{bench_in}'").first.click()
            await page.wait_for_timeout(1500)
            await browser.close()
            return f"Swapped {starter_out} with {bench_in}."

        await browser.close()
        return f"Could not find swap button for {starter_out}."

# Mapping tool names to executable functions
TOOL_MAP = {
    "get_user_leagues": get_user_leagues,
    "get_league_matchups": get_league_matchups,
    "get_trending_waivers": get_trending_waivers,
    "lock_in_player": lock_in_player,
    "swap_lineup": swap_lineup,
}

# --- AGENT RUNNER LOOP ---

async def run_agent():
    print("Initializing Gemini Client...")
    client = genai.Client()

    prompt = f"""
    You are managing my Sleeper fantasy teams for user '{SLEEPER_USERNAME}'.
    
    1. NBA Daily Routine:
       - Use get_user_leagues to list my active NBA leagues.
       - Check matchups and rosters using get_league_matchups.
       - If a starter has finished their final game of the week (Game 3/3 or 4/4) or exceeded projection, call lock_in_player.
       - If a starter is idle today and a bench player has an active game, call swap_lineup.
    2. NFL Routine:
       - Optimize starting lineup for highest projected points.
    3. Waiver Watch:
       - If free agent evaluation is needed, use get_trending_waivers and summarize recommendations.
    """

    tools = [
        get_user_leagues,
        get_league_matchups,
        get_trending_waivers,
        lock_in_player,
        swap_lineup
    ]

    # Initialize multi-turn chat to handle function calling turns
    chat = client.chats.create(
        model="gemini-2.5-flash",
        config=types.GenerateContentConfig(
            tools=tools,
            temperature=0.2
        )
    )

    response = chat.send_message(prompt)

    # Resolve any tool calls emitted by Gemini
    while response.function_calls:
        for call in response.function_calls:
            fn_name = call.name
            fn_args = call.args
            print(f"Calling tool: {fn_name} with {fn_args}")

            fn = TOOL_MAP.get(fn_name)
            if fn:
                if asyncio.iscoroutinefunction(fn):
                    result = await fn(**fn_args)
                else:
                    result = fn(**fn_args)
            else:
                result = f"Error: Tool {fn_name} not found."

            response = chat.send_message(
                types.Part.from_function_response(
                    name=fn_name,
                    response={"result": result}
                )
            )

    print("\n--- AGENT SUMMARY ---")
    print(response.text)

if __name__ == "__main__":
    asyncio.run(run_agent())
