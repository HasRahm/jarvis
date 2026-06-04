import os

def read_file(path: str) -> str:
    """Read the contents of a file at the given path"""
    try:
        with open(path, 'r', encoding='utf-8') as f:
            return f.read()
    except Exception as e:
        return f"Error reading file {path}: {str(e)}"

def write_file(path: str, content: str) -> str:
    """Write content to a file, creating it if it does not exist"""
    try:
        # Ensure directory exists
        os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
        with open(path, 'w', encoding='utf-8') as f:
            f.write(content)
        return f"Successfully wrote to {path}"
    except Exception as e:
        return f"Error writing to file {path}: {str(e)}"

def list_dir(path: str) -> str:
    """List files and directories at a path"""
    try:
        items = os.listdir(path)
        result = []
        for item in items:
            full_path = os.path.join(path, item)
            is_dir = os.path.isdir(full_path)
            result.append(f"{'[DIR]' if is_dir else '[FILE]'} {item}")
        return "\n".join(result)
    except Exception as e:
        return f"Error listing directory {path}: {str(e)}"
