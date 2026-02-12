import os
import shutil
import sys
import datetime

def cleanup():
    # Determine paths
    script_dir = os.path.dirname(os.path.abspath(__file__))
    # .gemini/hooks/ -> project root is 2 levels up
    project_root = os.path.abspath(os.path.join(script_dir, "../.."))
    config_dir = os.path.join(project_root, "config")

    if not os.path.exists(config_dir):
        print(f"Config directory {config_dir} does not exist. Nothing to clean.", file=sys.stderr)
        return

    try:
        # User requested to remove *all files* in the config directory.
        # We could also remove the directory itself. Let's remove content.
        for filename in os.listdir(config_dir):
            if filename == ".gitkeep":
                continue
            file_path = os.path.join(config_dir, filename)
            try:
                if os.path.isfile(file_path) or os.path.islink(file_path):
                    os.unlink(file_path)
                elif os.path.isdir(file_path):
                    shutil.rmtree(file_path)
            except Exception as e:
                print(f"Failed to delete {file_path}. Reason: {e}", file=sys.stderr)
        
        timestamp = datetime.datetime.now()

    except Exception as e:
        print(f"Error cleaning up config directory: {e}", file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    cleanup()
