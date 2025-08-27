#!/usr/bin/env python3
"""
Simple launcher script for AI Chat Interface
This script automatically launches the Flask backend which then launches the GUI
"""

import subprocess
import sys
import os
import time

# Fix Windows console encoding for unicode support
if os.name == 'nt':  # Windows
    sys.stdout.reconfigure(encoding='utf-8')
    sys.stderr.reconfigure(encoding='utf-8')

def main():
    print("🤖 AI Chat Interface Launcher")
    print("=" * 40)
    
    # Define processes to launch: (script_path, working_directory)
    processes_to_launch = [
        ('main.py', 'server'),
        ('main_gui.py', 'client')
    ]

    # Check if required files exist
    missing_files = []
    for script, cwd in processes_to_launch:
        full_path = os.path.join(cwd, script)
        if not os.path.exists(full_path):
            missing_files.append(full_path)
    
    if missing_files:
        print("❌ Missing required files:")
        for file in missing_files:
            print(f"   - {file}")
        print("\nPlease make sure all files are in their respective directories.")
        return
    
    print("All required files found")
    print("Starting processes...")
    print("=" * 40)
    
    launched_processes = []
    try:
        for script, cwd in processes_to_launch:
            print(f"Starting {script} in {cwd}/...")
            process = subprocess.Popen([sys.executable, script], cwd=cwd)
            launched_processes.append((process, cwd))
        
        # Monitor processes and terminate all if one stops
        while True:
            all_running = True
            for p, cwd in launched_processes:
                if p.poll() is not None:  # Process has terminated
                    print(f"A process ({p.args[1]} in {cwd}) has stopped. Terminating all others.")
                    all_running = False
                    break
            
            if not all_running:
                break
            
            time.sleep(1) # Check every second

    except KeyboardInterrupt:
        print("\nLauncher stopped by user.")
    except Exception as e:
        print(f"An error occurred: {e}")
    finally:
        print("=" * 40)
        print("Cleaning up processes...")
        for p, cwd in launched_processes:
            if p.poll() is None:  # If process is still running
                print(f"Terminating {p.args[1]} in {cwd}...")
                p.terminate()
                try:
                    p.wait(timeout=5) # Give it some time to terminate
                except subprocess.TimeoutExpired:
                    print(f"Force killing {p.args[1]} in {cwd}...")
                    p.kill()
            else:
                print(f"Process {p.args[1]} in {cwd} already stopped.")
        print("Cleanup complete.")

if __name__ == '__main__':
    main()
