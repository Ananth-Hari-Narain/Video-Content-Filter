from pathlib import Path

def create_new_file_if_missing(dest_path: str, procedure, *args, **kwargs):
    if (Path(dest_path).exists()):
        return dest_path
    else:
        return procedure(*args, **kwargs)
