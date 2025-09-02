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
