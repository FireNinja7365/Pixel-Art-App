import re


def hex_to_rgb(hex_color_str):

    h = hex_color_str.lstrip("#")
    if len(h) != 6:
        return (0, 0, 0)
    try:
        return tuple(int(h[i : i + 2], 16) for i in (0, 2, 4))
    except ValueError:
        return (0, 0, 0)


def rgb_to_hex(r, g, b):

    return f"#{int (r ):02x}{int (g ):02x}{int (b ):02x}"


def handle_slider_click(event, slider):

    if slider.identify(event.x, event.y) in ("trough1", "trough2"):
        if (widget_size := slider.winfo_width()) > 0:
            from_, to = float(slider.cget("from")), float(slider.cget("to"))
            fraction = max(0.0, min(1.0, event.x / widget_size))
            slider.set(from_ + (fraction * (to - from_)))


def sanitize_hex_input(hex_str):

    clean = hex_str.lstrip("#")

    is_valid = len(clean) == 6 and all(c in "0123456789abcdefABCDEF" for c in clean)
    return clean, is_valid


def sanitize_int_input(value_str, min_val=0, max_val=255):

    if not value_str:
        return None

    try:
        num = int(value_str)
        if num > max_val:
            return str(max_val)
        if num < min_val:
            return str(min_val)
    except ValueError:
        pass
    return None


def validate_hex_entry(value):

    if len(value) > 6:
        return False

    for char in value:
        if char not in "0123456789abcdefABCDEF":
            return False

    return True


def validate_int_entry(value):

    return value == "" or value.isdigit()
