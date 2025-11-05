# agent.py — hybrid vision + text agent

# libs
import os
import time
import json
import base64
import mss
import mss.tools
from openai import OpenAI
from pynput.keyboard import Key, Controller as KeyboardController
from pynput.mouse import Button, Controller as MouseController

# --- setup ---
# controllers
keyboard = KeyboardController()
mouse = MouseController()

# AI client (set your key!)
client = OpenAI(
    base_url="https://api.studio.nebius.com/v1/", 
    api_key="Your_API_Key_Here"  # <-- Replace with your actual API key
)

# --- models ---
vision_model_id = "mistralai/Mistral-Small-3.1-24B-Instruct-2503"
text_model_id = "deepseek-ai/DeepSeek-V3"

# --- state & timers ---
current_strategic_goal = "INITIALIZING"
last_strategic_update_time = 0
strategic_update_interval = 4.0  # Commander thinks every 4s

# --- helper & execution ---
# capture, read state, execute actions

def capture_screen_as_base64():
    """Grab whole screen and return base64 PNG."""
    with mss.mss() as sct:
        monitor = sct.monitors[1]
        sct_img = sct.grab(monitor)
        img_bytes = mss.tools.to_png(sct_img.rgb, sct_img.size)
        return base64.b64encode(img_bytes).decode('utf-8')

def read_game_state():
    """Read game_state.json, return dict or None."""
    try:
        with open("game_state.json", "r") as f:
            return json.load(f)
    except:
        return None

def execute_command(command, game_state):
    """Translate AI command into keyboard/mouse actions."""
    aim_error = game_state.get('angle_to_enemy_error', 0)

    if command in ['AIM', 'ATTACK'] and game_state.get('is_enemy_visible', False):
        mouse_movement = -int(aim_error * 2.5)
        mouse.move(mouse_movement, 0)

    if command == "ATTACK" and abs(aim_error) < 5:
        mouse.press(Button.left)
    else:
        mouse.release(Button.left)

    if command == "DEFENSIVE_MANEUVER":
        keyboard.press('s'); keyboard.press('a')
        time.sleep(0.5)
        keyboard.release('s'); keyboard.release('a')

    if command == "SEARCH":
        mouse.move(80, 0)

    if command == "ADVANCE":
        keyboard.press('w'); time.sleep(0.3); keyboard.release('w')

# --- AI brain: Commander & Lieutenant ---

def get_strategic_goal_from_vlm(game_state, screenshot_base64):
    """Commander: vision + data -> strategy."""
    print("\n--- Commander thinking... ---")
    state_report = json.dumps(game_state, indent=2)
    try:
        # Send a request to the OpenAI API with the system prompt, user text, and the screenshot.
        response = client.chat.completions.create(
            model=vision_model_id,  # Use the specified vision model.
            messages=[
                {
                    "role": "system",
                    "content": """
                    You are a strategic AI Commander. You see the big picture using both an image and precise data. Your job is to set the overall strategy, not the immediate action.
                    Analyze the visual environment and the data report.

                    Choose ONE of these STRATEGIC GOALS:
                    - `ENGAGE_AGGRESSIVELY`: The situation is favorable. I have good health, and the enemy is in a killable position.
                    - `REPOSITION_DEFENSIVELY`: The situation is dangerous. I have low health, am in a bad position (too open, too close), or just took damage. Survival is key.
                    - `HUNT_THE_ENEMY`: I cannot see the enemy. My goal is to find them.
                    
                    Provide ONLY the command word for the chosen strategy.
                    """
                },
                {
                    "role": "user",
                    "content": [
                        # The user prompt includes both the text data and the image.
                        {"type": "text", "text": f"Analyze the scene and this data to set the strategy.\nDATA:\n{state_report}"},
                        {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{screenshot_base64}"}}
                    ]
                }
            ],
            max_tokens=10  # Limit the response length to get just the command.
        )
        strategy = response.choices[0].message.content.strip().replace("'", "").replace('"', "")
        print(f"--- Strategy: {strategy} ---")
        return strategy
    except Exception as e:
        print(f"Commander error: {e}")
        return "HUNT_THE_ENEMY"

def get_tactical_action_from_llm(strategy, game_state):
    """Lieutenant: strategy + state -> immediate action."""
    state_report = json.dumps(game_state, indent=2)
    try:
        # Send a request to the OpenAI API with the current strategy and game state.
        response = client.chat.completions.create(
            model=text_model_id,  # Use the specified fast text model.
            messages=[
                {
                    "role": "system",
                    "content": f"""
                    You are a tactical AI Lieutenant. Your Commander has issued the strategic order: '{strategy}'.
                    Your job is to choose the best IMMEDIATE action based on this order and real-time data.

                    IF STRATEGY IS 'ENGAGE_AGGRESSIVELY':
                     - If enemy is visible and aim is good (error < 5), command `ATTACK`.
                     - If enemy is visible but aim is bad, command `AIM`.
                     - If enemy is far (>15m), command `ADVANCE`.
                    
                    IF STRATEGY IS 'REPOSITION_DEFENSIVELY':
                     - Command `DEFENSIVE_MANEUVER` to get to safety immediately.
                    
                    IF STRATEGY IS 'HUNT_THE_ENEMY':
                     - If enemy is not visible, command `SEARCH`. If they suddenly become visible, command `AIM`.

                    Choose ONE command: `ATTACK`, `AIM`, `ADVANCE`, `DEFENSIVE_MANEUVER`, `SEARCH`.
                    """
                },
                {"role": "user", "content": f"Strategy: '{strategy}'.\nReal-time data:\n{state_report}\n\nYour command:"}
            ],
            max_tokens=10,  # Limit the response length.
            temperature=0.0  # Set temperature to 0 for deterministic, non-creative responses.
        )
        action = response.choices[0].message.content.strip().replace("'", "").replace('"', "")
        print(f"Lieutenant action: {action}")
        return action
    except Exception as e:
        print(f"Lieutenant error: {e}")
        return "SEARCH"

# --- main loop ---
if __name__ == "__main__":
    print("Agent starting in 5s...")
    time.sleep(5)
    keyboard.press('g'); time.sleep(0.1); keyboard.release('g')
    print("Agent active.")

    try:
        # Start the main control loop that runs continuously.
        while True:
            # Read the latest game state from the JSON file.
            game_state = read_game_state()
            # If the game state is missing or indicates the game has ended, stop the agent.
            if not game_state or game_state.get('game_status') in ['won', 'lost']:
                print(f"Game over or state unreadable.")
                break

            # commander: update strategy if needed
            # Check if enough time has passed since the last strategic update.
            if time.time() - last_strategic_update_time > strategic_update_interval:
                # If so, capture a new screenshot.
                screenshot = capture_screen_as_base64()
                # Ask the Commander (VLM) for a new strategic goal.
                current_strategic_goal = get_strategic_goal_from_vlm(game_state, screenshot)
                # Update the timestamp for the last strategic update.
                last_strategic_update_time = time.time()

            # lieutenant: get and run a tactical action
            # Ensure the Commander has provided an initial strategy.
            if current_strategic_goal != "INITIALIZING":
                # Ask the Lieutenant (LLM) for a specific tactical action based on the current strategy.
                tactical_action = get_tactical_action_from_llm(current_strategic_goal, game_state)
                # Execute the chosen action.
                execute_command(tactical_action, game_state)
            else:
                # If still initializing, just print a waiting message.
                print("Waiting for initial strategy from Commander...")

            # small sleep to throttle the loop
            time.sleep(0.3)

    finally:
        print("Exiting, releasing keys.")
        mouse.release(Button.left)