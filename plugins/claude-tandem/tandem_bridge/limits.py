"""Shared product limit, retained across OSes for interoperable messages."""
MAX_INPUT_UTF16_UNITS = 22000


def utf16_units(text):
    return len(text.encode('utf-16-le')) // 2
