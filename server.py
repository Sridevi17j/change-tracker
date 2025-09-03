#!/usr/bin/env python3
"""
Claude Code Change Tracker MCP Server
Tracks changes made by Claude Code with state management and rollback capabilities.
"""

import os
import json
import hashlib
import zipfile
import shutil
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Optional, Tuple
import fnmatch

from fastmcp import FastMCP

# Initialize the MCP server
mcp = FastMCP("Claude Code Change Tracker")

def get_claude_code_working_directory():
    """
    Attempt to detect the working directory where Claude Code is running.
    This would be enhanced based on actual Claude Code integration.
    """
    # Method 1: Check for common Claude Code indicators
    current_dir = Path.cwd()
    
    # Look for common project files that indicate we're in a project root
    project_indicators = [
        'package.json', 'requirements.txt', 'Cargo.toml', 'go.mod', 
        'pom.xml', 'composer.json', '.git', 'pyproject.toml'
    ]
    
    # Start from current directory and move up to find project root
    search_dir = current_dir
    for _ in range(5):  # Don't go too far up
        for indicator in project_indicators:
            if (search_dir / indicator).exists():
                return str(search_dir)
        parent = search_dir.parent
        if parent == search_dir:  # Reached filesystem root
            break
        search_dir = parent
    
    # Fallback to current directory
    return str(current_dir)

# Configuration
HISTORY_DIR = ".claude-history"
INITIAL_BACKUP = "initial_backup.zip"
FILE_HASHES = "file_hashes.json"
METADATA_FILE = "metadata.json"
CURRENT_STATE_FILE = "current_state.txt"
STATES_DIR = "states"

# Default ignore patterns (similar to .gitignore)
DEFAULT_IGNORE_PATTERNS = [
    ".git/*",
    "node_modules/*",
    "__pycache__/*",
    "*.pyc",
    ".env",
    ".DS_Store",
    "*.log",
    ".claude-history/*"
]


class ChangeTracker:
    def __init__(self, project_dir: str = "."):
        # Use the path exactly as Claude passes it, without resolving to server's filesystem
        self.project_dir = Path(project_dir)
        
        # Always create history directory within the project directory
        self.history_dir = self.project_dir / HISTORY_DIR
        self.states_dir = self.history_dir / STATES_DIR
        
        # Print where the history will be stored for debugging
        print(f"[ChangeTracker] History directory will be: {self.history_dir}")
        
    def _should_ignore_file(self, file_path: str) -> bool:
        """Check if file should be ignored based on patterns"""
        for pattern in DEFAULT_IGNORE_PATTERNS:
            if fnmatch.fnmatch(file_path, pattern):
                return True
        return False
    
    def _get_file_hash(self, file_path: Path) -> str:
        """Calculate MD5 hash of file content"""
        try:
            with open(file_path, 'rb') as f:
                return hashlib.md5(f.read()).hexdigest()
        except Exception:
            return ""
    
    def _get_all_project_files(self) -> List[Path]:
        """Get all files in project (excluding ignored ones)"""
        files = []
        for root, dirs, filenames in os.walk(self.project_dir):
            # Skip history directory
            if HISTORY_DIR in root:
                continue
                
            for filename in filenames:
                file_path = Path(root) / filename
                relative_path = file_path.relative_to(self.project_dir)
                
                if not self._should_ignore_file(str(relative_path)):
                    files.append(file_path)
        return files
    
    def _load_metadata(self) -> Dict:
        """Load metadata about saved states"""
        metadata_path = self.history_dir / METADATA_FILE
        if metadata_path.exists():
            with open(metadata_path, 'r') as f:
                return json.load(f)
        return {"states": [], "current_state": 0}
    
    def _save_metadata(self, metadata: Dict):
        """Save metadata about saved states"""
        metadata_path = self.history_dir / METADATA_FILE
        with open(metadata_path, 'w') as f:
            json.dump(metadata, f, indent=2)
    
    def _load_file_hashes(self) -> Dict[str, str]:
        """Load initial file hashes"""
        hash_path = self.history_dir / FILE_HASHES
        if hash_path.exists():
            with open(hash_path, 'r') as f:
                return json.load(f)
        return {}
    
    def _save_file_hashes(self, hashes: Dict[str, str]):
        """Save file hashes"""
        hash_path = self.history_dir / FILE_HASHES
        with open(hash_path, 'w') as f:
            json.dump(hashes, f, indent=2)
    
    def initialize_tracking(self) -> Dict[str, any]:
        """Initialize tracking by creating initial backup and file hashes"""
        # Create history directory
        print(f"[ChangeTracker] Creating history directory at: {self.history_dir}")
        self.history_dir.mkdir(exist_ok=True)
        self.states_dir.mkdir(exist_ok=True)
        print(f"[ChangeTracker] History directory created successfully")
        
        # Get all project files
        project_files = self._get_all_project_files()
        
        # Create initial backup zip
        initial_backup_path = self.history_dir / INITIAL_BACKUP
        file_hashes = {}
        
        with zipfile.ZipFile(initial_backup_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
            for file_path in project_files:
                relative_path = file_path.relative_to(self.project_dir)
                zipf.write(file_path, relative_path)
                
                # Store file hash
                file_hashes[str(relative_path)] = self._get_file_hash(file_path)
        
        # Save file hashes
        self._save_file_hashes(file_hashes)
        
        # Initialize metadata
        metadata = {
            "states": [],
            "current_state": 0,
            "initialized_at": datetime.now().isoformat(),
            "total_files_tracked": len(project_files)
        }
        self._save_metadata(metadata)
        
        return {
            "status": "success",
            "message": f"Initialized tracking for {len(project_files)} files",
            "backup_location": str(initial_backup_path),
            "files_tracked": len(project_files)
        }
    
    def save_current_changes(self, prompt_text: str = "", description: str = "") -> Dict[str, any]:
        """Save current changes compared to initial state"""
        if not (self.history_dir / INITIAL_BACKUP).exists():
            return {"status": "error", "message": "Not initialized. Run initialize_tracking() first."}
        
        # Load initial file hashes
        initial_hashes = self._load_file_hashes()
        
        # Find changed files
        changed_files = []
        current_files = self._get_all_project_files()
        
        for file_path in current_files:
            relative_path = str(file_path.relative_to(self.project_dir))
            current_hash = self._get_file_hash(file_path)
            
            # Check if file is new or modified
            if relative_path not in initial_hashes or initial_hashes[relative_path] != current_hash:
                changed_files.append(file_path)
        
        if not changed_files:
            return {"status": "info", "message": "No changes detected"}
        
        # Load metadata and create new state
        metadata = self._load_metadata()
        state_number = len(metadata["states"]) + 1
        state_filename = f"state_{state_number:03d}.zip"
        state_path = self.states_dir / state_filename
        
        # Create zip with changed files
        with zipfile.ZipFile(state_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
            for file_path in changed_files:
                relative_path = file_path.relative_to(self.project_dir)
                zipf.write(file_path, relative_path)
        
        # Update metadata
        state_info = {
            "state_number": state_number,
            "filename": state_filename,
            "timestamp": datetime.now().isoformat(),
            "prompt": prompt_text,
            "description": description,
            "files_changed": [str(f.relative_to(self.project_dir)) for f in changed_files],
            "file_count": len(changed_files)
        }
        
        metadata["states"].append(state_info)
        metadata["current_state"] = state_number
        self._save_metadata(metadata)
        
        return {
            "status": "success",
            "message": f"Saved state {state_number} with {len(changed_files)} changed files",
            "state_number": state_number,
            "files_changed": len(changed_files),
            "changed_files": [str(f.relative_to(self.project_dir)) for f in changed_files]
        }
    
    def list_states(self) -> Dict[str, any]:
        """List all saved states"""
        metadata = self._load_metadata()
        
        if not metadata["states"]:
            return {"status": "info", "message": "No states saved yet", "states": []}
        
        states_info = []
        for state in metadata["states"]:
            states_info.append({
                "state_number": state["state_number"],
                "timestamp": state["timestamp"],
                "prompt": state.get("prompt", "")[:100] + "..." if len(state.get("prompt", "")) > 100 else state.get("prompt", ""),
                "description": state.get("description", ""),
                "files_changed": state["file_count"],
                "is_current": state["state_number"] == metadata["current_state"]
            })
        
        return {
            "status": "success",
            "current_state": metadata["current_state"],
            "total_states": len(metadata["states"]),
            "states": states_info
        }
    
    def restore_to_state(self, state_number: int) -> Dict[str, any]:
        """Restore project to a specific state"""
        metadata = self._load_metadata()
        
        # Validate state number
        if state_number == 0:
            # Restore to initial state
            return self._restore_to_initial()
        
        # Find the state
        target_state = None
        for state in metadata["states"]:
            if state["state_number"] == state_number:
                target_state = state
                break
        
        if not target_state:
            return {"status": "error", "message": f"State {state_number} not found"}
        
        # First restore to initial state
        initial_result = self._restore_to_initial()
        if initial_result["status"] != "success":
            return initial_result
        
        # Then apply the target state changes
        state_path = self.states_dir / target_state["filename"]
        if not state_path.exists():
            return {"status": "error", "message": f"State file {target_state['filename']} not found"}
        
        try:
            with zipfile.ZipFile(state_path, 'r') as zipf:
                zipf.extractall(self.project_dir)
            
            # Update current state
            metadata["current_state"] = state_number
            self._save_metadata(metadata)
            
            return {
                "status": "success",
                "message": f"Restored to state {state_number}",
                "state_info": {
                    "state_number": target_state["state_number"],
                    "timestamp": target_state["timestamp"],
                    "prompt": target_state.get("prompt", ""),
                    "description": target_state.get("description", ""),
                    "files_restored": target_state["file_count"]
                }
            }
        except Exception as e:
            return {"status": "error", "message": f"Failed to restore state: {str(e)}"}
    
    def _restore_to_initial(self) -> Dict[str, any]:
        """Restore to initial backup state"""
        initial_backup_path = self.history_dir / INITIAL_BACKUP
        if not initial_backup_path.exists():
            return {"status": "error", "message": "Initial backup not found"}
        
        try:
            # Remove all current project files (except .claude-history)
            for file_path in self._get_all_project_files():
                file_path.unlink()
            
            # Extract initial backup
            with zipfile.ZipFile(initial_backup_path, 'r') as zipf:
                zipf.extractall(self.project_dir)
            
            # Update metadata
            metadata = self._load_metadata()
            metadata["current_state"] = 0
            self._save_metadata(metadata)
            
            return {
                "status": "success",
                "message": "Restored to initial state"
            }
        except Exception as e:
            return {"status": "error", "message": f"Failed to restore to initial state: {str(e)}"}
    
    def show_state_details(self, state_number: int) -> Dict[str, any]:
        """Show detailed information about a specific state"""
        metadata = self._load_metadata()
        
        if state_number == 0:
            return {
                "status": "success",
                "state_info": {
                    "state_number": 0,
                    "description": "Initial project state",
                    "timestamp": metadata.get("initialized_at", "Unknown"),
                    "is_current": metadata["current_state"] == 0
                }
            }
        
        # Find the state
        target_state = None
        for state in metadata["states"]:
            if state["state_number"] == state_number:
                target_state = state
                break
        
        if not target_state:
            return {"status": "error", "message": f"State {state_number} not found"}
        
        return {
            "status": "success",
            "state_info": {
                "state_number": target_state["state_number"],
                "timestamp": target_state["timestamp"],
                "prompt": target_state.get("prompt", ""),
                "description": target_state.get("description", ""),
                "files_changed": target_state["files_changed"],
                "file_count": target_state["file_count"],
                "is_current": target_state["state_number"] == metadata["current_state"]
            }
        }
    
    def cleanup_states(self, keep_last_n: int = 10) -> Dict[str, any]:
        """Keep only the last N states, remove older ones"""
        metadata = self._load_metadata()
        
        if len(metadata["states"]) <= keep_last_n:
            return {"status": "info", "message": f"Only {len(metadata['states'])} states exist, nothing to cleanup"}
        
        # Sort states by state number and keep last N
        sorted_states = sorted(metadata["states"], key=lambda x: x["state_number"])
        states_to_remove = sorted_states[:-keep_last_n]
        states_to_keep = sorted_states[-keep_last_n:]
        
        # Remove old state files
        removed_count = 0
        for state in states_to_remove:
            state_path = self.states_dir / state["filename"]
            if state_path.exists():
                state_path.unlink()
                removed_count += 1
        
        # Update metadata
        metadata["states"] = states_to_keep
        self._save_metadata(metadata)
        
        return {
            "status": "success",
            "message": f"Removed {removed_count} old states, kept last {len(states_to_keep)} states"
        }


# Global tracker instance
tracker = None

# MCP Tool Definitions

@mcp.tool()
def initialize_tracking(working_directory: str) -> str:
    """
    Initialize change tracking for the specified working directory.
    
    Args:
        working_directory: The directory where Claude Code is currently running (REQUIRED)
    """
    global tracker
    
    if not working_directory:
        return json.dumps({
            "status": "error", 
            "message": "working_directory is required. Please provide the project directory path."
        })
    
    # Use the working directory path exactly as Claude passes it
    if not working_directory:
        return json.dumps({
            "status": "error",
            "message": "Working directory path is required"
        })
    
    tracker = ChangeTracker(working_directory)
    result = tracker.initialize_tracking()
    result["working_directory"] = working_directory
    return json.dumps(result, indent=2)

@mcp.tool()
def save_current_changes(working_directory: str, prompt_text: str = "", description: str = "") -> str:
    """
    Save current project changes as a new state.
    
    Args:
        working_directory: The directory where Claude Code is running (REQUIRED)
        prompt_text: The prompt that was used with Claude Code
        description: Additional description for this state
    """
    global tracker
    
    if not working_directory:
        return json.dumps({
            "status": "error",
            "message": "working_directory is required. Please provide the project directory path."
        })
    
    # Use the working directory path exactly as Claude passes it
    if not tracker or str(tracker.project_dir) != working_directory:
        tracker = ChangeTracker(working_directory)
    
    result = tracker.save_current_changes(prompt_text, description)
    result["working_directory"] = working_directory
    return json.dumps(result, indent=2)

@mcp.tool()
def restore_to_state(working_directory: str, state_number: int) -> str:
    """
    Restore project to a specific state.
    
    Args:
        working_directory: The directory where the project is located (REQUIRED)
        state_number: State number to restore to (0 for initial state)
    """
    global tracker
    
    if not working_directory:
        return json.dumps({
            "status": "error",
            "message": "working_directory is required."
        })
    
    if not tracker or str(tracker.project_dir) != working_directory:
        tracker = ChangeTracker(working_directory)
    
    result = tracker.restore_to_state(state_number)
    result["working_directory"] = working_directory
    return json.dumps(result, indent=2)

@mcp.tool()
def list_states(working_directory: str) -> str:
    """
    List all saved states with their information.
    
    Args:
        working_directory: The directory where the project is located (REQUIRED)
    """
    global tracker
    
    if not working_directory:
        return json.dumps({
            "status": "error",
            "message": "working_directory is required."
        })
    
    if not tracker or str(tracker.project_dir) != working_directory:
        tracker = ChangeTracker(working_directory)
    
    result = tracker.list_states()
    result["working_directory"] = working_directory
    return json.dumps(result, indent=2)

@mcp.tool()
def show_state_details(working_directory: str, state_number: int) -> str:
    """
    Show detailed information about a specific state.
    
    Args:
        working_directory: The directory where the project is located (REQUIRED)
        state_number: State number to show details for
    """
    global tracker
    
    if not working_directory:
        return json.dumps({
            "status": "error",
            "message": "working_directory is required."
        })
    
    if not tracker or str(tracker.project_dir) != working_directory:
        tracker = ChangeTracker(working_directory)
    
    result = tracker.show_state_details(state_number)
    result["working_directory"] = working_directory
    return json.dumps(result, indent=2)

@mcp.tool()
def cleanup_old_states(working_directory: str, keep_last_n: int = 10) -> str:
    """
    Remove old states, keeping only the last N states.
    
    Args:
        working_directory: The directory where the project is located (REQUIRED)
        keep_last_n: Number of recent states to keep (default: 10)
    """
    global tracker
    
    if not working_directory:
        return json.dumps({
            "status": "error",
            "message": "working_directory is required."
        })
    
    if not tracker or str(tracker.project_dir) != working_directory:
        tracker = ChangeTracker(working_directory)
    
    result = tracker.cleanup_states(keep_last_n)
    result["working_directory"] = working_directory
    return json.dumps(result, indent=2)

@mcp.tool()
def get_current_status(working_directory: str) -> str:
    """
    Get current tracking status and information.
    
    Args:
        working_directory: The directory where the project is located (REQUIRED)
    """
    if not working_directory:
        return json.dumps({
            "status": "error",
            "message": "working_directory is required."
        })
    
    # Use working directory exactly as Claude passes it
    temp_tracker = ChangeTracker(working_directory)
    metadata = temp_tracker._load_metadata()
    
    status_info = {
        "is_initialized": (temp_tracker.history_dir / INITIAL_BACKUP).exists(),
        "current_state": metadata.get("current_state", 0),
        "total_states": len(metadata.get("states", [])),
        "initialized_at": metadata.get("initialized_at", "Not initialized"),
        "working_directory": working_directory,
        "history_directory": str(temp_tracker.history_dir)
    }
    
    return json.dumps(status_info, indent=2)

if __name__ == "__main__":
    print("Starting MCP Change Tracker Server - Testing print statement!")
    port = os.getenv("MCP_PORT", "8000")
    mcp.run(transport="http", host="0.0.0.0", port=8000)