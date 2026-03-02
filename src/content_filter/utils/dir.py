from pathlib import Path
from .text import clean_word

def create_new_file_if_missing(dest_path: str, procedure, *args, **kwargs):
    if (Path(dest_path).exists()):
        return dest_path
    else:
        return procedure(*args, **kwargs)
    
def load_profanity(profanity_path, tmpdir):
    """
    Load the list of profanity words from a file, returning a set.
    """
    profanity_set = set()
    with open(profanity_path, "r", encoding="utf-8") as f:
        for line in f:
            word = clean_word(line)
            profanity_set.add(word)
    
    return profanity_set
