import json
import os
import sys

def get_extension_version() -> None:
    """Reads gemini-extension.json and prints the version."""
    try:
        # Assumes the script is in .gemini/skills/ext_version/scripts/
        # gemini-extension.json is at the root, so 4 levels up
        base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))
        json_path = os.path.join(base_dir, "gemini-extension.json")
        
        if not os.path.exists(json_path):
             # Fallback: try current directory or one level up if running from root
             if os.path.exists("gemini-extension.json"):
                 json_path = "gemini-extension.json"
        
        with open(json_path, "r", encoding="utf-8") as f:
            data = json.load(f)
            print(data.get("version", "Version not found"))

    except FileNotFoundError:
        print("Error: gemini-extension.json not found at expected path.", file=sys.stderr)
        sys.exit(1)
    except json.JSONDecodeError:
        print("Error: gemini-extension.json is not valid JSON.", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"An unexpected error occurred: {e}", file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    get_extension_version()
