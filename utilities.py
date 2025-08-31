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


def blend_colors(fg_hex, fg_alpha, bg_hex, bg_alpha):

    fg_r, fg_g, fg_b = hex_to_rgb(fg_hex)
    bg_r, bg_g, bg_b = hex_to_rgb(bg_hex)

    fa, ba = fg_alpha / 255.0, bg_alpha / 255.0
    out_a_norm = fa + ba * (1.0 - fa)

    if out_a_norm > 0:
        final_alpha = min(255, int(round(out_a_norm * 255.0)))
        r = min(
            255, max(0, int(round((fg_r * fa + bg_r * ba * (1 - fa)) / out_a_norm)))
        )
        g = min(
            255, max(0, int(round((fg_g * fa + bg_g * ba * (1 - fa)) / out_a_norm)))
        )
        b = min(
            255, max(0, int(round((fg_b * fa + bg_b * ba * (1 - fa)) / out_a_norm)))
        )
        final_hex = rgb_to_hex(r, g, b)
    else:
        final_hex, final_alpha = "#000000", 0

    return final_hex, final_alpha


def bresenham_line(x0, y0, x1, y1):

    dx = abs(x1 - x0)
    dy = abs(y1 - y0)
    sx = 1 if x0 < x1 else -1
    sy = 1 if y0 < y1 else -1
    err = dx - dy

    while True:
        yield (x0, y0)
        if x0 == x1 and y0 == y1:
            break
        e2 = 2 * err
        if e2 > -dy:
            err -= dy
            x0 += sx
        if e2 < dx:
            err += dx
            y0 += sy


def handle_slider_click(event, slider):

    if slider.identify(event.x, event.y) in ("trough1", "trough2"):
        if (widget_size := slider.winfo_width()) > 0:
            from_, to = float(slider.cget("from")), float(slider.cget("to"))
            fraction = max(0.0, min(1.0, event.x / widget_size))
            slider.set(from_ + (fraction * (to - from_)))
