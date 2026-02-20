import os
import shutil
import sys
import datetime
import time

def cleanup():
    # Determine paths
    script_dir = os.path.dirname(os.path.abspath(__file__))
    # .gemini/hooks/ -> project root is 2 levels up
    project_root = os.path.abspath(os.path.join(script_dir, "../.."))
    config_dir = os.path.join(project_root, "config")
    log_file = os.path.join(project_root, ".gemini/hooks/execution.log")
    lock_file = os.path.join(os.path.expanduser("~"), ".gaada_cleanup.lock")

    pid = os.getpid()
    ppid = os.getppid()
    now = datetime.datetime.now().isoformat()

    # Diagnostic Logging
    try:
        with open(log_file, "a") as f:
            f.write(f"[{now}] PID: {pid}, PPID: {ppid} - Triggered cleanup\n")
    except Exception:
        pass

    # Atomic Deduplication Guard
    try:
        # os.O_EXCL fails if the file already exists (atomic operation)
        fd = os.open(lock_file, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        with os.fdopen(fd, 'w') as f:
            f.write(str(pid))
    except FileExistsError:
        # Check if the lock is stale (> 5 seconds)
        try:
            mtime = os.path.getmtime(lock_file)
            if time.time() - mtime < 5:
                with open(log_file, "a") as f:
                    f.write(f"[{now}] PID: {pid} - Exiting (Lock exists and is fresh)\n")
                return
            else:
                # Stale lock, try to take it by deleting and recreating
                os.unlink(lock_file)
                # Recurse once to try again after clearing stale lock
                return cleanup()
        except Exception:
            return
    except Exception as e:
        with open(log_file, "a") as f:
            f.write(f"[{now}] PID: {pid} - Lock error: {e}\n")
        # Proceed if lock check fails (fallback)
        pass

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
