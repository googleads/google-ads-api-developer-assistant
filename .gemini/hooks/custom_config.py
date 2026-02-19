import os
import shutil
import subprocess
import json
import sys

def get_version(ext_version_script):
    """Retrieves the extension version."""
    try:
        result = subprocess.run(
            [sys.executable, ext_version_script],
            capture_output=True,
            text=True,
            check=True
        )
        return result.stdout.strip()
    except Exception as e:
        print(f"Error getting extension version: {e}", file=sys.stderr)
        return None

def configure_language(lang_name, home_config, target_config, version, is_python=False):
    """Copies and versions a specific language configuration."""
    if not os.path.exists(home_config):
        if is_python:
            print(f"Error: {home_config} does not exist. Please create it in your home directory.", file=sys.stderr)
            sys.exit(1)
        else:
            print(f"Warning: {home_config} does not exist for {lang_name}. Skipping.", file=sys.stderr)
            return False

    try:
        shutil.copy2(home_config, target_config)
        with open(target_config, "a", encoding="utf-8") as f:
            # Python/YAML uses :, INI/Ruby often can use = in these formats
            sep = ":" if is_python else "="
            f.write(f"\ngaada {sep} \"{version}\"\n")
        
        return True
    except Exception as e:
        print(f"Error configuring {lang_name}: {e}", file=sys.stderr)
        return False

def main():
    script_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.abspath(os.path.join(script_dir, "../.."))
    settings_path = os.path.join(project_root, ".gemini/settings.json")
    config_dir = os.path.join(project_root, "config")
    ext_version_script = os.path.join(project_root, ".gemini/skills/ext_version/scripts/get_extension_version.py")
    
    os.makedirs(config_dir, exist_ok=True)
    version = get_version(ext_version_script)
    if not version:
        sys.exit(1)

    # 1. Configure Python (Always)
    python_home = os.path.join(os.path.expanduser("~"), "google-ads.yaml")
    python_target = os.path.join(config_dir, "google-ads.yaml")
    configure_language("Python", python_home, python_target, version, is_python=True)

    # 2. Configure other languages (Conditional)
    if os.path.exists(settings_path):
        try:
            with open(settings_path, "r") as f:
                settings = json.load(f)
            include_dirs = settings.get("context", {}).get("includeDirectories", [])
        except Exception as e:
            print(f"Error reading settings.json: {e}", file=sys.stderr)
            include_dirs = []

        languages = [
            {
                "id": "google-ads-php",
                "name": "PHP",
                "filename": "google_ads_php.ini",
                "home": os.path.join(os.path.expanduser("~"), "google_ads_php.ini")
            },
            {
                "id": "google-ads-ruby",
                "name": "Ruby",
                "filename": "google_ads_config.rb",
                "home": os.path.join(os.path.expanduser("~"), "google_ads_config.rb")
            }
        ]

        for lang in languages:
            enabled = any(lang["id"] in d for d in include_dirs)
            if enabled:
                target = os.path.join(config_dir, lang["filename"])
                configure_language(lang["name"], lang["home"], target, version)

if __name__ == "__main__":
    main()
