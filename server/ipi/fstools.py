import os
import glob as py_glob
import re
import base64
import mimetypes
import subprocess
import shutil
import json
from fnmatch import fnmatch
import utils.auth as auth
import yaml
with open('../server_config.yaml', 'r') as f:
    config = yaml.safe_load(f)

# NOTE: The user-facing confirmation prompts (e.g., for write_file, replace) are handled by the execution environment
# and are not implemented within these tool functions themselves.

def _is_binary(file_path):
    """Heuristically determines if a file is binary."""
    try:
        with open(file_path, 'tr') as check_file:
            check_file.read(1024)
        return False
    except (UnicodeDecodeError, TypeError):
        return True

def _get_git_root():
    """Finds the root of the git repository."""
    try:
        # Check if we are in a git repo
        subprocess.run(['git', 'rev-parse', '--is-inside-work-tree'], check=True, capture_output=True, text=True)
        # Get the top level directory
        result = subprocess.run(['git', 'rev-parse', '--show-toplevel'], check=True, capture_output=True, text=True)
        return result.stdout.strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        return None

def _parse_gitignore(git_root):
    """Parses .gitignore files and returns a list of patterns."""
    patterns = []
    gitignore_path = os.path.join(git_root, '.gitignore')
    if os.path.exists(gitignore_path):
        with open(gitignore_path, 'r') as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#'):
                    patterns.append(line)
    return patterns

def _is_ignored(path, git_root, gitignore_patterns):
    """Checks if a path should be ignored based on .gitignore patterns."""
    if not git_root:
        return False
    relative_path = os.path.relpath(path, git_root).replace('\\', '/')
    for pattern in gitignore_patterns:
        if fnmatch(relative_path, pattern.strip('/')) or fnmatch(os.path.basename(path), pattern):
             return True
    return False

def _resolve_path(path: str) -> str:
    """Resolves a path to an absolute path, relative to the current working directory."""
    if os.path.isabs(path):
        return path
    if config["working_dir"]:
        return os.path.abspath(os.path.join(config["working_dir"], path))
    return os.path.abspath(os.path.join(os.getcwd(), path))
#=============================================================================================================================================================================================================
# Reading Files
#=============================================================================================================================================================================================================
def list_directory(path: str, ignore: list[str] = None, respect_git_ignore: bool = True) -> str:
    """
    Lists the names of files and subdirectories directly within a specified directory path.

    - Can optionally ignore entries matching provided glob patterns.
    - Indicates whether each entry is a directory.
    - Sorts entries with directories first, then alphabetically.

    Args:
        path (str): The path to the directory to list. Can be relative or absolute.
        ignore (list[str], optional): A list of glob patterns to exclude from the listing. Defaults to None.
        respect_git_ignore (bool, optional): Whether to respect .gitignore patterns. Defaults to True.

    Returns:
        str: A formatted string of the directory listing or an error message.
    """
    check = auth.authorize("list_directory")  # Ensure the user is authorized to list directories
    if check:
        return check
    
    resolved_path = _resolve_path(path)
    if not os.path.isdir(resolved_path):
        return f"Error: Directory not found at {resolved_path}"

    git_root = _get_git_root() if respect_git_ignore else None
    gitignore_patterns = _parse_gitignore(git_root) if git_root else []

    dirs = []
    files = []
    for item in os.listdir(resolved_path):
        item_path = os.path.join(resolved_path, item)
        
        # Handle ignore patterns
        if ignore and any(fnmatch(item, p) for p in ignore):
            continue
            
        # Handle .gitignore
        if respect_git_ignore and _is_ignored(item_path, git_root, gitignore_patterns):
            continue

        if os.path.isdir(item_path):
            dirs.append(f"[DIR] {item}")
        else:
            files.append(item)
            
    dirs.sort()
    files.sort()
    
    output = f"Directory listing for {resolved_path}:\n" + "\n".join(dirs + files)
    return output

def read_file(path: str, offset: int = None, limit: int = None) -> str | dict:
    """
    Reads and returns the content of a specified file.

    - Handles text, images (PNG, JPG, GIF, WEBP, SVG, BMP), and PDF files.
    - For text files, can read specific line ranges.
    - For image/PDF files, returns a base64-encoded data structure.

    Args:
        path (str): The path to the file to read. Can be relative or absolute.
        offset (int, optional): The 0-based line number to start reading from for text files. Defaults to None.
        limit (int, optional): The maximum number of lines to read for text files. Defaults to None.

    Returns:
        str | dict: The file content as a string, a dictionary for image/PDF data, or an error message.
    """
    check = auth.authorize("read_file")  # Ensure the user is authorized 
    if check:
        return check
    
    resolved_path = _resolve_path(path)
    if not os.path.exists(resolved_path):
        return f"Error: File not found at {resolved_path}"

    mime_type, _ = mimetypes.guess_type(resolved_path)
    is_image = mime_type and mime_type.startswith('image/')
    is_pdf = mime_type == 'application/pdf'

    if is_image or is_pdf:
        with open(resolved_path, 'rb') as f:
            data = base64.b64encode(f.read()).decode('utf-8')
        return {"inlineData": {"mimeType": mime_type, "data": data}}

    if _is_binary(resolved_path):
        return f"Cannot display content of binary file: {resolved_path}"

    with open(resolved_path, 'r', encoding='utf-8') as f:
        lines = f.readlines()

    total_lines = len(lines)
    if offset is not None and limit is not None:
        start = offset
        end = offset + limit
        lines = lines[start:end]
        header = f"[File content truncated: showing lines {start+1}-{min(end, total_lines)} of {total_lines} total lines...]\n"
    else:
        header = ""

    return header + "".join(lines)

def glob(pattern: str, path: str = None, respect_git_ignore: bool = True) -> str:
    """
    Finds files matching specific glob patterns, returning absolute paths.

    - Sorts results by modification time (newest first).
    - Can respect .gitignore patterns.

    Args:
        pattern (str): The glob pattern to match against (e.g., "*.py", "src/**/*.js").
        path (str, optional): The path to the directory to search within. Can be relative or absolute. Defaults to the current directory.
        respect_git_ignore (bool, optional): Whether to respect .gitignore patterns. Defaults to True.

    Returns:
        str: A formatted string of matching files or a message if none are found.
    """
    check = auth.authorize("glob")  # Ensure the user is authorized 
    if check:
        return check
    # Note: case_sensitive is hard to implement reliably across OSes without custom logic.
    # Python's glob is case-sensitive on Linux/macOS and insensitive on Windows.
    # This implementation does not add a cross-platform case-sensitivity layer.
    
    search_path = _resolve_path(path) if path else os.getcwd()
    full_pattern = os.path.join(search_path, pattern)
    
    files = py_glob.glob(full_pattern, recursive=True)
    
    if respect_git_ignore:
        git_root = _get_git_root()
        gitignore_patterns = _parse_gitignore(git_root) if git_root else []
        files = [f for f in files if not _is_ignored(f, git_root, gitignore_patterns)]

    # Sort by modification time (newest first)
    files.sort(key=os.path.getmtime, reverse=True)
    
    output = f'Found {len(files)} file(s) matching "{pattern}" within {path or "."}, sorted by modification time (newest first):\n'
    output += "\n".join(files)
    return output

def search_file_content(pattern: str, path: str = None, include: str = None) -> str:
    """
    Searches for a regular expression pattern within the content of files.

    - Can filter files by a glob pattern.
    - Returns the lines containing matches, with file paths and line numbers.
    - Uses `git grep` for performance if available.

    Args:
        pattern (str): The regular expression (regex) to search for.
        path (str, optional): The directory to search within. Can be relative or absolute. Defaults to the current directory.
        include (str, optional): A glob pattern to filter which files are searched. Defaults to all files.

    Returns:
        str: A formatted string of matches or a message if none are found.
    """
    check = auth.authorize("search_file_content")  # Ensure the user is authorized 
    if check:
        return check
    
    search_path = _resolve_path(path) if path else '.'
    
    # Use git grep if in a git repo for performance
    if shutil.which('git') and _get_git_root():
        try:
            cmd = ['git', 'grep', '-n', '-E', pattern]
            if include:
                cmd.append('--')
                cmd.append(include)
            result = subprocess.run(cmd, cwd=search_path, check=True, capture_output=True, text=True, encoding='utf-8')
            
            matches = result.stdout.strip().split('\n')
            # Reformat to match the desired output structure
            files = {}
            for match in matches:
                if not match: continue
                file_path, line_num, line_content = match.split(':', 2)
                if file_path not in files:
                    files[file_path] = []
                files[file_path].append(f"L{line_num}: {line_content}")
            
            output = f'Found {len(matches)} match(es) for pattern "{pattern}" in path "{search_path}" (filter: "{include or "all"}"):\n'
            for file_path, lines in files.items():
                output += f"---\nFile: {file_path}\n"
                output += "\n".join(lines) + "\n"
            return output
        except (subprocess.CalledProcessError, FileNotFoundError):
            # Fallback to Python search if git grep fails
            pass

    # Python-based fallback search
    found_matches = []
    files_to_search = py_glob.glob(os.path.join(search_path, include or '**/*'), recursive=True)
    
    for file_path in files_to_search:
        if os.path.isfile(file_path) and not _is_binary(file_path):
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    for i, line in enumerate(f):
                        if re.search(pattern, line):
                            found_matches.append({'file': file_path, 'line': i + 1, 'content': line.strip()})
            except Exception:
                continue # Ignore files that can't be read

    if not found_matches:
        return f'Found 0 match(es) for pattern "{pattern}" in path "{search_path}"'

    files = {}
    for match in found_matches:
        file = match['file']
        if file not in files:
            files[file] = []
        files[file].append(f"L{match['line']}: {match['content']}")

    output = f'Found {len(found_matches)} match(es) for pattern "{pattern}" in path "{search_path}" (filter: "{include or "all"}"):\n'
    for file_path, lines in files.items():
        output += f"---\nFile: {file_path}\n"
        output += "\n".join(lines) + "\n"
    return output

def read_many_files(paths: list[str], include: list[str] = None, exclude: list[str] = None, recursive: bool = True, useDefaultExcludes: bool = True, respect_git_ignore: bool = True) -> str:
    """
    Reads content from multiple files specified by paths or glob patterns.

    - For text files, concatenates their content into a single string.
    - For image and PDF files, returns them as base64-encoded data if explicitly requested.
    - Can include/exclude files based on glob patterns and respect .gitignore.

    Args:
        paths (list[str]): An array of glob patterns or paths. Can be relative or absolute.
        include (list[str], optional): Additional glob patterns to include. Defaults to None.
        exclude (list[str], optional): Glob patterns for files/directories to exclude. Defaults to None.
        recursive (bool, optional): Whether to search recursively. Defaults to True.
        useDefaultExcludes (bool, optional): Whether to apply default exclusion patterns. Defaults to True.
        respect_git_ignore (bool, optional): Whether to respect .gitignore patterns. Defaults to True.

    Returns:
        str: A string containing the concatenated content of the files, or an error message.
    """
    check = auth.authorize("read_many_files")  # Ensure the user is authorized 
    if check:
        return check
    
    all_paths = set()
    # Combine paths and include patterns
    search_patterns = paths + (include or [])

    # Default excludes, can be turned off
    default_excludes = ['.git', 'node_modules', '__pycache__'] if useDefaultExcludes else []
    exclude_patterns = default_excludes + (exclude or [])

    # Find all files matching the patterns
    for pattern in search_patterns:
        # Use py_glob for glob pattern matching
        resolved_pattern = _resolve_path(pattern)
        matched_files = py_glob.glob(resolved_pattern, recursive=recursive)
        for f in matched_files:
            all_paths.add(os.path.abspath(f))

    # Filter files based on exclude patterns and gitignore
    git_root = _get_git_root() if respect_git_ignore else None
    gitignore_patterns = _parse_gitignore(git_root) if git_root else []

    final_files = []
    for f_path in all_paths:
        is_excluded = any(fnmatch(f_path, p) for p in exclude_patterns)
        is_gitignored = respect_git_ignore and _is_ignored(f_path, git_root, gitignore_patterns)
        if not is_excluded and not is_gitignored:
            final_files.append(f_path)

    # Read and process the files
    output_parts = []
    for f_path in sorted(list(final_files)):
        if not os.path.isfile(f_path):
            continue

        output_parts.append(f"--- {f_path} ---")
        # Use the existing read_file logic to handle different file types
        file_content = read_file(f_path)
        if isinstance(file_content, dict):
            # For binary/image/pdf, just show the JSON representation
            output_parts.append(json.dumps(file_content, indent=2))
        else:
            output_parts.append(file_content)

    return "\n".join(output_parts)
#=============================================================================================================================================================================================================
# Writing Files
#=============================================================================================================================================================================================================
def edit_file(file_path: str, old_string: str, new_string: str, expected_replacements: int = 1) -> str:
    """
    Edits a file by either replacing specific text, overwriting the entire content, or deleting the file.

    - If old_string is provided and non-empty, performs targeted replacement of old_string with new_string
    - If old_string is None or empty, overwrites the entire file with new_string
    - If both old_string and new_string are empty strings, deletes the file
    - Creates parent directories and new files as needed

    Args:
        file_path (str): The path to the file to modify. Can be relative or absolute. Will create files and directories as needed.
        new_string (str): The new content to write or replacement text. If both old_string and new_string are empty, deletes the file or directory.
        old_string (str): The exact literal text to replace. If empty, overwrites entire file. Only leave this empty if you want to overwrite the entire file.
        expected_replacements (int, optional): The number of occurrences to replace when doing targeted replacement. Defaults to 1.

    Returns:
        str: A success or failure message.
    """
    check = auth.authorize("edit_file")  # Ensure the user is authorized 
    if check:
        return check
    
    resolved_path = _resolve_path(file_path)

    # If both old_string and new_string are empty, delete the file or empty directory
    if old_string == "" and new_string == "":
        if not os.path.exists(resolved_path):
            return f"Failed to delete, path does not exist: {resolved_path}"
        
        try:
            if os.path.isfile(resolved_path):
                os.remove(resolved_path)
                return f"Successfully deleted file: {resolved_path}"
            elif os.path.isdir(resolved_path):
                os.rmdir(resolved_path)
                return f"Successfully deleted empty directory: {resolved_path}"
            else:
                return f"Failed to delete, path is not a file or directory: {resolved_path}"
        except OSError as e:
            if "Directory not empty" in str(e):
                return f"Failed to delete directory, it is not empty: {resolved_path}"
            return f"Failed to delete path: {e}"
        except Exception as e:
            return f"Failed to delete path: {e}"

    # If old_string is empty, overwrite entire file
    if old_string == "":
        try:
            # Create parent directories if they don't exist
            parent_dir = os.path.dirname(resolved_path)
            if parent_dir:
                os.makedirs(parent_dir, exist_ok=True)
            
            is_new_file = not os.path.exists(resolved_path)
            
            with open(resolved_path, 'w', encoding='utf-8') as f:
                f.write(new_string)
                
            if is_new_file:
                return f"Successfully created and wrote to new file: {resolved_path}"
            else:
                return f"Successfully overwrote file: {resolved_path}"
        except Exception as e:
            return f"Failed to write to file: {e}"
    
    # Otherwise, perform targeted replacement
    if not os.path.exists(resolved_path):
        return f"Failed to edit, file does not exist: {resolved_path}"

    try:
        with open(resolved_path, 'r', encoding='utf-8') as f:
            content = f.read()
    except Exception as e:
        return f"Failed to read file: {e}"

    actual_occurrences = content.count(old_string)
    
    if actual_occurrences == 0:
        return f"Failed to edit, 0 occurrences of the 'old_string' were found."
        
    if expected_replacements is not None and actual_occurrences != expected_replacements:
        return f"Failed to edit, expected {expected_replacements} occurrences but found {actual_occurrences}."

    content = content.replace(old_string, new_string, expected_replacements or -1)

    try:
        with open(resolved_path, 'w', encoding='utf-8') as f:
            f.write(content)
        return f"Successfully modified file: {resolved_path} ({expected_replacements or actual_occurrences} replacements)."
    except Exception as e:
        return f"Failed to write changes to file: {e}"

def replace_in_file(file_path: str, old_string: str, new_string: str, expected_replacements: int = 1) -> str:
    """
    Replaces text within a file.

    - Replaces a specified number of occurrences of `old_string` with `new_string`.

    Args:
        file_path (str): The path to the file to modify. Can be relative or absolute.
        old_string (str): The exact literal text to replace.
        new_string (str): The exact literal text to replace `old_string` with.
        expected_replacements (int, optional): The number of occurrences to replace. Defaults to 1.

    Returns:
        str: A success or failure message.
    """
    resolved_path = _resolve_path(file_path)
    if not os.path.exists(resolved_path):
        return f"Failed to edit, file does not exist: {resolved_path}"

    return edit_file(resolved_path, old_string, new_string, expected_replacements)

def write_file(file_path: str, content: str) -> str:
    """
    Writes content to a specified file.

    - If the file exists, it will be overwritten.
    - If the file doesn't exist, it (and any necessary parent directories) will be created.

    Args:
        file_path (str): The path to the file to write to. Can be relative or absolute.
        content (str): The content to write into the file.

    Returns:
        str: A success or error message.
    """
    if content == "":
        return f"Failed to write, content cannot be empty."
    resolved_path = _resolve_path(file_path)
    return edit_file(resolved_path, "", content, 0)  # Use empty old_string to overwrite entire file
