import os
import shutil
import subprocess
import sys
import datetime

def configure():
    """Configures the Google Ads environment."""
    # Determine paths
    script_dir = os.path.dirname(os.path.abspath(__file__))
    # hooks/SessionStart -> root is 2 levels up
    root_dir = os.path.abspath(os.path.join(script_dir, "../.."))
    source_yaml = os.path.join(os.path.expanduser("~"), "google-ads.yaml")
    config_dir = os.path.join(root_dir, "config")
    target_yaml = os.path.join(config_dir, "google-ads.yaml")
    ext_version_script = os.path.join(root_dir, "skills/ext_version/scripts/get_extension_version.py")

    # Check if source exists
    if not os.path.exists(source_yaml):
        # Fail silently or print error? Hooks might be noisy. 
        # But user requested "If it does not exist display an error and stop" originally.
        # We will keep the error message but maybe not exit(1) if we don't want to break the session?
        # User requirement said "If it does not exist display an error and stop", so we stick to it.
        print(f"Error: {source_yaml} does not exist. Please create it in the project root.", file=sys.stderr)
        sys.exit(1)

    # Create config directory
    os.makedirs(config_dir, exist_ok=True)

    # Copy file
    shutil.copy2(source_yaml, target_yaml)

    # Get extension version
    try:
        # Run the extension version script via python3
        result = subprocess.run(
            [sys.executable, ext_version_script],
            capture_output=True,
            text=True,
            check=True
        )
        version = result.stdout.strip()
    except subprocess.CalledProcessError as e:
        print(f"Error getting extension version: {e.stderr}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"Error executing version script: {e}", file=sys.stderr)
        sys.exit(1)

    # Append version to target yaml
    try:
        with open(target_yaml, "a", encoding="utf-8") as f:
            f.write(f"\ngaada: \"{version}\"\n")
    except Exception as e:
        print(f"Error appending to {target_yaml}: {e}", file=sys.stderr)
        sys.exit(1)

    # Output env var command
    print(f"export GOOGLE_ADS_CONFIGURATION_FILE_PATH=\"{target_yaml}\"", file=sys.stdout)

if __name__ == "__main__":
    timestamp = datetime.datetime.now()
    message = f"SUCCESS: SessionEnd hook 'cleanup_config.py' ran at {timestamp}"
    print(message, file=sys.stderr)
    configure()
