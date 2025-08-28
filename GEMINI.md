# Gemini Project Context: summer-28

This document provides context for the Gemini agent regarding the `summer-28` project.

## `aircon_controller.py`

This is the main script for controlling a Nature Remo smart air conditioner.

### Key Functionality

*   **Purpose:** Automatically adjusts the air conditioner's temperature based on the current room temperature.
*   **Configuration:**
    *   Uses a local SQLite database (`/home/muo/workspace/summer-28/remo.db`) to store configuration.
    *   **Keys:**
        *   `token`: The Nature Remo API token.
        *   `appliance_id`: The ID of the target air conditioner.
        *   `last_set_temp`: The last temperature value set by the script (e.g., '28', '30', or 'off_detected').
        *   `last_set_timestamp`: The timestamp of the last temperature change or 'off' detection.
    *   An interactive setup flow (`setup_flow`) runs on the first execution to guide the user through obtaining the token and appliance ID.
*   **Control Logic:**
    *   The script checks the air conditioner's power status first.
    *   **If the power is OFF, the script will not change any settings.** It will not turn the power on automatically.
    *   **If the power is ON,** it executes the following logic:
        *   If the room temperature exceeds 29.0°C, it sets the air conditioner's temperature to 28°C.
        *   If the room temperature drops to 27.0°C or below, it sets the temperature to 30°C.
    *   After successfully changing the temperature, it records `last_set_temp` and `last_set_timestamp` to the database to track its last action.
*   **Stateful Caching (to avoid redundant API calls):**
    *   The script first attempts to read a recent (under 2 minutes old) temperature from an external log file (`/home/muo/templog.txt`).
    *   If a recent temperature is found and it's in the ideal range (27°C < T <= 29°C), the script exits.
    *   The script checks the database for two types of cooldown periods before making API calls:
        *   **Temperature Change Cooldown (5 minutes):** If the script recently changed the AC temperature, it will wait 5 minutes before making another change. For example, if the script set the AC to 30°C three minutes ago, it will exit even if the room temperature is still 26°C.
        *   **AC Off Detection Cooldown (10 minutes):** If the script detects that the room temperature is outside the ideal range but the AC power is OFF, it will log this event and wait for 10 minutes before attempting any action again. This prevents the script from repeatedly checking when the user has intentionally left the AC off.
    *   This stateful check prevents the script from making API calls every minute when the temperature has not yet stabilized or when the AC is intentionally off.
*   **API Usage:**
    *   Communicates with the Nature Remo Cloud API (`https.api.nature.global`).
    *   Uses the `requests` library for API calls.
*   **Dependencies:**
    *   `sqlite3`
    *   `requests`
    *   `os`
    *   `sys`
    *   `time`
