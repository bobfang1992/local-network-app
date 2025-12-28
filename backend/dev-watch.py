#!/usr/bin/env python3
"""
Development watch script - auto-restarts backend on file changes
Usage: sudo python dev-watch.py
"""

import sys
import os
import signal
import subprocess
import time
from pathlib import Path

try:
    from watchdog.observers import Observer
    from watchdog.events import FileSystemEventHandler
except ImportError:
    print("Error: watchdog library not found")
    print("Installing watchdog...")
    subprocess.run([sys.executable, "-m", "pip", "install", "watchdog"])
    from watchdog.observers import Observer
    from watchdog.events import FileSystemEventHandler


class BackendRestartHandler(FileSystemEventHandler):
    def __init__(self, script_dir):
        self.script_dir = script_dir
        self.python_path = script_dir / ".venv" / "bin" / "python"
        self.main_path = script_dir / "main.py"
        self.process = None
        self.restarting = False

        # Start the backend initially
        self.start_backend()

    def start_backend(self):
        """Start the FastAPI backend"""
        print("\n" + "=" * 60)
        print("🚀 Starting backend...")
        print("=" * 60)

        try:
            self.process = subprocess.Popen(
                [str(self.python_path), str(self.main_path)],
                cwd=str(self.script_dir),
                stdout=sys.stdout,
                stderr=sys.stderr
            )
            print(f"✓ Backend started (PID: {self.process.pid})")
        except Exception as e:
            print(f"✗ Failed to start backend: {e}")
            sys.exit(1)

    def stop_backend(self):
        """Stop the FastAPI backend"""
        if self.process:
            print("\n🛑 Stopping backend...")
            try:
                self.process.terminate()
                self.process.wait(timeout=5)
                print("✓ Backend stopped")
            except subprocess.TimeoutExpired:
                print("⚠️  Backend didn't stop gracefully, force killing...")
                self.process.kill()
                self.process.wait()
            except Exception as e:
                print(f"✗ Error stopping backend: {e}")

    def restart_backend(self):
        """Restart the backend"""
        if self.restarting:
            return

        self.restarting = True
        print("\n🔄 File change detected, restarting...")

        self.stop_backend()
        time.sleep(0.5)  # Brief pause
        self.start_backend()

        self.restarting = False

    def on_modified(self, event):
        """Handle file modification events"""
        if event.is_directory:
            return

        # Only restart on Python file changes
        if event.src_path.endswith('.py'):
            # Ignore __pycache__ and .venv
            if '__pycache__' in event.src_path or '.venv' in event.src_path:
                return

            print(f"\n📝 Changed: {Path(event.src_path).name}")
            self.restart_backend()


def main():
    # Check if running with proper permissions
    if os.geteuid() != 0 and sys.platform == "darwin":
        print("⚠️  Warning: Not running as root. Network scanning may be limited.")
        print("For full functionality, run: sudo python dev-watch.py")
        print()

    script_dir = Path(__file__).parent.resolve()

    print("=" * 60)
    print("👀 Backend Development Watch Mode")
    print("=" * 60)
    print(f"Watching: {script_dir}")
    print("Monitoring: *.py files")
    print("Press Ctrl+C to stop")
    print("=" * 60)

    # Create event handler and observer
    event_handler = BackendRestartHandler(script_dir)
    observer = Observer()
    observer.schedule(event_handler, str(script_dir), recursive=False)
    observer.start()

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n\n🛑 Shutting down watch mode...")
        observer.stop()
        event_handler.stop_backend()
        print("✓ Stopped")

    observer.join()


if __name__ == "__main__":
    main()
