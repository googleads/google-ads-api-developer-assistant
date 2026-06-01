import pathlib
import tomllib
import sys


def load_commands(commands_dir):
    """Returns command names and descriptions from Gemini command TOML files."""
    if not commands_dir.exists():
        print(f"Directory not found: {commands_dir.absolute()}")
        sys.exit(1)

    files = sorted(commands_dir.glob("*.toml"))
    
    if not files:
        print("No .toml files found in .gemini/commands")
        return []

    commands = []
    for file_path in files:
        try:
            with file_path.open("rb") as f:
                data = tomllib.load(f)
                description = data.get("description", "No description found")
                commands.append((f"/{file_path.stem}", description))
        except Exception as e:
            print(f"Error reading {file_path.name}: {e}", file=sys.stderr)

    return commands


def print_commands(commands):
    if not commands:
        return

    max_len = max(len(cmd[0]) for cmd in commands)
    gap = 3
    for name, description in commands:
        print(f"{name:<{max_len + gap}}{description}")


def main():
    commands_dir = pathlib.Path(".gemini/commands")
    print_commands(load_commands(commands_dir))


if __name__ == "__main__":
    main()
