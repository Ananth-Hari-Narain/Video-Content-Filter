import re

def remove_punctuation(text: str) -> str:
    return re.sub(r"[^\w\s]", "", text)

def clean_word(text: str) -> str:
    return remove_punctuation(text.strip()).lower()