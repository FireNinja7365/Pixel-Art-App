# canvas_cython_helpers.pyx
# cython: language_level=3
# cython: boundscheck=False
# cython: wraparound=False
# cython: cdivision=True
# cython: cpp=True

import numpy as np
cimport numpy as np
from collections import defaultdict

from libc.stdio cimport sprintf
from libc.stdlib cimport calloc, free
from libcpp.vector cimport vector

cdef inline unsigned char blend_channel(unsigned char fg, unsigned char bg, double alpha):
    return <unsigned char>(fg * alpha + bg * (1.0 - alpha))

cpdef tuple hex_to_rgb_cy(str hex_color):
    hex_color = hex_color.lstrip('#')
    cdef int r = int(hex_color[0:2], 16)
    cdef int g = int(hex_color[2:4], 16)
    cdef int b = int(hex_color[4:6], 16)
    return (r, g, b)

cpdef np.ndarray[np.uint8_t, ndim=3] render_image(
    int width, int height, list layers_data,
    bint use_bg_color, tuple bg_color_rgb, bint render_alpha,
    tuple dirty_bbox = None
):
    cdef int min_x = 0, min_y = 0, max_x = width, max_y = height
    cdef int render_width = width, render_height = height

    if dirty_bbox is not None:
        min_x, min_y, max_x, max_y = dirty_bbox
        render_width = max_x - min_x
        render_height = max_y - min_y

    cdef np.ndarray[np.uint8_t, ndim=3] buffer = np.zeros((render_height, render_width, 4), dtype=np.uint8)
    cdef unsigned char[:, :, ::1] v_buffer = buffer

    cdef int x, y, i, layer_idx, px, py, r, g, b, a
    cdef unsigned char e_alpha
    cdef double alpha_norm
    cdef tuple pixel_data, color_rgb

    cdef unsigned char c1_r=224, c1_g=224, c1_b=224
    cdef unsigned char c2_r=240, c2_g=240, c2_b=240

    for y in range(render_height):
        for x in range(render_width):
            px = x + min_x
            py = y + min_y
            if use_bg_color:
                v_buffer[y, x, 0] = bg_color_rgb[0]
                v_buffer[y, x, 1] = bg_color_rgb[1]
                v_buffer[y, x, 2] = bg_color_rgb[2]
                v_buffer[y, x, 3] = 255
            else:
                if (px + py) % 2 == 0:
                    v_buffer[y, x, 0] = c1_r; v_buffer[y, x, 1] = c1_g; v_buffer[y, x, 2] = c1_b;
                else:
                    v_buffer[y, x, 0] = c2_r; v_buffer[y, x, 1] = c2_g; v_buffer[y, x, 2] = c2_b;
                v_buffer[y, x, 3] = 255

    for layer_dict in layers_data:
        for (px, py), pixel_data in layer_dict.items():
            if min_x <= px < max_x and min_y <= py < max_y:
                x = px - min_x
                y = py - min_y

                a = pixel_data[1]
                if not render_alpha:
                    e_alpha = 255
                else:
                    e_alpha = a

                if e_alpha > 0:
                    color_rgb = hex_to_rgb_cy(pixel_data[0])
                    r, g, b = color_rgb

                    alpha_norm = e_alpha / 255.0

                    v_buffer[y, x, 0] = blend_channel(r, v_buffer[y, x, 0], alpha_norm)
                    v_buffer[y, x, 1] = blend_channel(g, v_buffer[y, x, 1], alpha_norm)
                    v_buffer[y, x, 2] = blend_channel(b, v_buffer[y, x, 2], alpha_norm)

    return buffer


cpdef tuple composite_pixel_stack_cy(
    int px, int py, list all_layers_data, int stop_at_layer_index,
    bint use_bg_color, tuple bg_color_rgb, bint render_alpha
):
    cdef tuple base_rgb
    if use_bg_color:
        base_rgb = bg_color_rgb
    else:
        base_rgb = (224, 224, 224) if (px + py) % 2 == 0 else (240, 240, 240)

    cdef double r, g, b
    r, g, b = <double>base_rgb[0], <double>base_rgb[1], <double>base_rgb[2]

    cdef int i, a
    cdef unsigned char e_alpha
    cdef double alpha_norm
    cdef tuple pixel_data, color_rgb
    cdef int layer_count = len(all_layers_data)

    if stop_at_layer_index == -1:
        stop_at_layer_index = layer_count

    for i in range(stop_at_layer_index):
        pixel_data = all_layers_data[i].get((px, py))
        if pixel_data:
            a = pixel_data[1]
            if not render_alpha: e_alpha = 255
            else: e_alpha = a

            if e_alpha > 0:
                color_rgb = hex_to_rgb_cy(pixel_data[0])
                alpha_norm = e_alpha / 255.0
                r = color_rgb[0] * alpha_norm + r * (1.0 - alpha_norm)
                g = color_rgb[1] * alpha_norm + g * (1.0 - alpha_norm)
                b = color_rgb[2] * alpha_norm + b * (1.0 - alpha_norm)

    return (<unsigned char>r, <unsigned char>g, <unsigned char>b)


cpdef list bresenham_line_cy(int x0, int y0, int x1, int y1):
    cdef list points = []
    cdef int dx = abs(x1 - x0)
    cdef int dy = -abs(y1 - y0)
    cdef int sx = 1 if x0 < x1 else -1
    cdef int sy = 1 if y0 < y1 else -1
    cdef int err = dx + dy
    cdef int e2

    while True:
        points.append((x0, y0))
        if x0 == x1 and y0 == y1:
            break
        e2 = 2 * err
        if e2 >= dy:
            err += dy
            x0 += sx
        if e2 <= dx:
            err += dx
            y0 += sy
    return points


cpdef tuple blend_colors_cy(str hex1, int alpha1, str hex2, int alpha2):
    cdef tuple rgb1 = hex_to_rgb_cy(hex1)
    cdef tuple rgb2 = hex_to_rgb_cy(hex2)
    cdef double a1 = alpha1 / 255.0
    cdef double a2 = alpha2 / 255.0

    cdef double a_out = a1 + a2 * (1.0 - a1)
    if a_out == 0:
        return ("#000000", 0)

    cdef int r_out = <int>round((rgb1[0] * a1 + rgb2[0] * a2 * (1.0 - a1)) / a_out)
    cdef int g_out = <int>round((rgb1[1] * a1 + rgb2[1] * a2 * (1.0 - a1)) / a_out)
    cdef int b_out = <int>round((rgb1[2] * a1 + rgb2[2] * a2 * (1.0 - a1)) / a_out)
    cdef int alpha_out = <int>round(a_out * 255)

    hex_out = "#{:02x}{:02x}{:02x}".format(r_out, g_out, b_out)
    
    return (hex_out.upper(), alpha_out)


cpdef set get_stroke_pixels_cy(
    int x0, int y0, int x1, int y1,
    int brush_size, int canvas_width, int canvas_height,
    set drawn_pixels_set
):
    cdef list line_pixels = bresenham_line_cy(x0, y0, x1, y1)
    cdef set pixels_to_add = set()

    cdef int offset = (brush_size - 1) // 2
    cdef int p_x, p_y, brush_px, brush_py, x_off, y_off

    for p_x, p_y in line_pixels:
        start_x = p_x - offset
        start_y = p_y - offset

        for y_off in range(brush_size):
            brush_py = start_y + y_off
            if 0 <= brush_py < canvas_height:
                for x_off in range(brush_size):
                    brush_px = start_x + x_off
                    if 0 <= brush_px < canvas_width:
                        if (brush_px, brush_py) not in drawn_pixels_set:
                            pixels_to_add.add((brush_px, brush_py))
                            drawn_pixels_set.add((brush_px, brush_py))

    return pixels_to_add


cpdef dict render_preview_chunks_cy(
    set new_preview_pixels,
    dict tool_options,
    list all_layers_data,
    bint use_bg_color, tuple bg_color_rgb, bint render_alpha,
    int chunk_size
):
    cdef bint is_eraser = tool_options.get("tool") == "eraser"
    cdef int active_layer_index = tool_options["active_layer_index"]
    cdef str source_hex = tool_options.get("color")
    cdef int source_alpha = tool_options.get("alpha", 0)
    cdef dict active_layer_data = tool_options["active_layer_data"]
    cdef bint color_blending = tool_options.get("color_blending", False)

    cdef dict dirty_chunks = {}
    cdef int px, py, cx, cy, i, a, alpha_to_use
    cdef tuple existing_pixel, base_rgb, applied_rgb, rgb_above, chunk_coord
    cdef str applied_hex
    cdef int applied_alpha
    cdef double alpha_norm, composite_r, composite_g, composite_b, final_r, final_g, final_b
    cdef list pixel_list_for_chunk
    
    cdef dict rendered_chunk_buffers = {}
    cdef np.ndarray[np.uint8_t, ndim=3] buffer
    cdef unsigned char[:, :, ::1] v_buffer

    for px, py in new_preview_pixels:
        chunk_coord = (px // chunk_size, py // chunk_size)
        if chunk_coord not in dirty_chunks:
            dirty_chunks[chunk_coord] = []
        dirty_chunks[chunk_coord].append((px, py))
    
    for (cx, cy), pixels_in_chunk in dirty_chunks.items():
        buffer = np.zeros((chunk_size, chunk_size, 4), dtype=np.uint8)
        v_buffer = buffer
        rendered_chunk_buffers[(cx, cy)] = buffer

        for px, py in pixels_in_chunk:
            base_rgb = composite_pixel_stack_cy(
                px, py, all_layers_data, active_layer_index,
                use_bg_color, bg_color_rgb, render_alpha
            )

            applied_hex = source_hex
            applied_alpha = source_alpha
            if is_eraser: applied_alpha = 0
            
            existing_pixel = active_layer_data.get((px, py))
            if color_blending and 0 < source_alpha < 255 and existing_pixel and existing_pixel[1] > 0:
                applied_hex, applied_alpha = blend_colors_cy(source_hex, source_alpha, existing_pixel[0], existing_pixel[1])

            composite_r, composite_g, composite_b = base_rgb
            if applied_alpha > 0:
                alpha_to_use = applied_alpha if render_alpha else 255
                alpha_norm = alpha_to_use / 255.0
                applied_rgb = hex_to_rgb_cy(applied_hex)
                composite_r = applied_rgb[0] * alpha_norm + base_rgb[0] * (1.0 - alpha_norm)
                composite_g = applied_rgb[1] * alpha_norm + base_rgb[1] * (1.0 - alpha_norm)
                composite_b = applied_rgb[2] * alpha_norm + base_rgb[2] * (1.0 - alpha_norm)

            final_r, final_g, final_b = composite_r, composite_g, composite_b
            for i in range(active_layer_index + 1, len(all_layers_data)):
                pixel_above = all_layers_data[i].get((px, py))
                if pixel_above and pixel_above[1] > 0:
                    a = pixel_above[1]
                    alpha_to_use = a if render_alpha else 255
                    if alpha_to_use > 0:
                        alpha_norm = alpha_to_use / 255.0
                        rgb_above = hex_to_rgb_cy(pixel_above[0])
                        final_r = rgb_above[0] * alpha_norm + final_r * (1.0 - alpha_norm)
                        final_g = rgb_above[1] * alpha_norm + final_g * (1.0 - alpha_norm)
                        final_b = rgb_above[2] * alpha_norm + final_b * (1.0 - alpha_norm)

            img_x, img_y = px % chunk_size, py % chunk_size
            v_buffer[img_y, img_x, 0] = <unsigned char>final_r
            v_buffer[img_y, img_x, 1] = <unsigned char>final_g
            v_buffer[img_y, img_x, 2] = <unsigned char>final_b
            v_buffer[img_y, img_x, 3] = 255

    return rendered_chunk_buffers

cdef cppclass PixelCoord:
    int x, y

cpdef tuple flood_fill_apply_cy(
    int start_x, int start_y,
    int canvas_width, int canvas_height,
    dict active_layer_data,
    tuple target_data,
    str new_hex, int new_alpha,
    bint color_blending
):
    cdef dict pixels_before = {}
    cdef dict pixels_after = {}
    cdef size_t map_size = canvas_width * canvas_height
    cdef char* processed = <char*>calloc(map_size, sizeof(char))
    cdef vector[PixelCoord] stack
    cdef vector[PixelCoord] pixels_to_fill
    cdef int x, y, nx, ny, px, py
    cdef long i
    cdef tuple current_pixel_data, original_pixel, final_pixel_data
    cdef PixelCoord current_coord, temp_coord
    cdef str applied_hex
    cdef int applied_alpha

    if not (0 <= start_x < canvas_width and 0 <= start_y < canvas_height):
        if processed: free(processed)
        return ({}, {})

    if processed is NULL:
        raise MemoryError("Failed to allocate processed map for flood fill")

    temp_coord.x = start_x
    temp_coord.y = start_y
    stack.push_back(temp_coord)
    processed[start_y * canvas_width + start_x] = 1

    while not stack.empty():
        current_coord = stack.back()
        stack.pop_back()
        x = current_coord.x
        y = current_coord.y
        
        current_pixel_data = active_layer_data.get((x, y), ("transparent", 0))

        if current_pixel_data == target_data:
            temp_coord.x = x
            temp_coord.y = y
            pixels_to_fill.push_back(temp_coord)
            pixels_before[(x,y)] = current_pixel_data

            for dx, dy in [(0, 1), (0, -1), (1, 0), (-1, 0)]:
                nx = x + dx
                ny = y + dy
                if 0 <= nx < canvas_width and 0 <= ny < canvas_height and not processed[ny * canvas_width + nx]:
                    processed[ny * canvas_width + nx] = 1
                    temp_coord.x = nx
                    temp_coord.y = ny
                    stack.push_back(temp_coord)
    
    free(processed)
    
    if not pixels_to_fill.empty():
        for i in range(pixels_to_fill.size()):
            px = pixels_to_fill[i].x
            py = pixels_to_fill[i].y
            
            applied_hex = new_hex
            applied_alpha = new_alpha

            if color_blending and 0 < new_alpha < 255:
                original_pixel = pixels_before.get((px, py))
                if original_pixel and original_pixel[1] > 0:
                    applied_hex, applied_alpha = blend_colors_cy(new_hex, new_alpha, original_pixel[0], original_pixel[1])

            if applied_alpha > 0:
                final_pixel_data = (applied_hex, applied_alpha)
                active_layer_data[(px, py)] = final_pixel_data
                pixels_after[(px, py)] = final_pixel_data
            elif (px, py) in active_layer_data:
                del active_layer_data[(px, py)]
                pixels_after[(px, py)] = None
    
    return (pixels_before, pixels_after)

cpdef set get_brush_pixels_cy(int center_x, int center_y, int brush_size, int canvas_width, int canvas_height):
    cdef set pixels = set()
    cdef int offset = (brush_size - 1) // 2
    cdef int start_x = center_x - offset
    cdef int start_y = center_y - offset
    cdef int x_off, y_off, px, py
    for y_off in range(brush_size):
        py = start_y + y_off
        if 0 <= py < canvas_height:
            for x_off in range(brush_size):
                px = start_x + x_off
                if 0 <= px < canvas_width:
                    pixels.add((px, py))
    return pixels

cpdef set get_rectangle_pixels_cy(int x0, int y0, int x1, int y1, bint fill, int canvas_width, int canvas_height):
    cdef set pixels = set()
    cdef int xs = min(x0, x1), ys = min(y0, y1)
    cdef int xe = max(x0, x1), ye = max(y0, y1)
    cdef int x, y
    if fill:
        for y in range(ys, ye + 1):
            if 0 <= y < canvas_height:
                for x in range(xs, xe + 1):
                    if 0 <= x < canvas_width:
                        pixels.add((x, y))
    else:
        for x in range(xs, xe + 1):
            if 0 <= x < canvas_width:
                if 0 <= ys < canvas_height: pixels.add((x, ys))
                if 0 <= ye < canvas_height: pixels.add((x, ye))
        for y in range(ys + 1, ye):
            if 0 <= y < canvas_height:
                if 0 <= xs < canvas_width: pixels.add((xs, y))
                if 0 <= xe < canvas_width: pixels.add((xe, y))
    return pixels

cpdef set get_ellipse_pixels_cy(int x0, int y0, int rx, int ry, bint fill, int canvas_width, int canvas_height):
    cdef set pixels = set()
    cdef int px, py, x_offset, y_offset
    cdef set full_ellipse, inner_ellipse
    cdef int rx_inner, ry_inner

    if rx == 0 and ry == 0:
        if 0 <= x0 < canvas_width and 0 <= y0 < canvas_height: pixels.add((x0,y0))
        return pixels

    if fill:
        for y_offset in range(-ry, ry + 1):
            for x_offset in range(-rx, rx + 1):
                if ((x_offset / <float>rx if rx > 0 else 0)**2 + (y_offset / <float>ry if ry > 0 else 0)**2) <= 1:
                    px = x0 + x_offset; py = y0 + y_offset
                    if 0 <= px < canvas_width and 0 <= py < canvas_height: pixels.add((px, py))
    else:
        full_ellipse = set()
        inner_ellipse = set()
        for y_offset in range(-ry, ry + 1):
            for x_offset in range(-rx, rx + 1):
                if ((x_offset / <float>rx if rx > 0 else 0)**2 + (y_offset / <float>ry if ry > 0 else 0)**2) <= 1:
                    px = x0 + x_offset; py = y0 + y_offset
                    if 0 <= px < canvas_width and 0 <= py < canvas_height: full_ellipse.add((px, py))
        
        rx_inner = max(0, rx - 1)
        ry_inner = max(0, ry - 1)
        if rx_inner > 0 or ry_inner > 0:
            for y_offset in range(-ry_inner, ry_inner + 1):
                for x_offset in range(-rx_inner, rx_inner + 1):
                    if ((x_offset / <float>rx_inner if rx_inner > 0 else 0)**2 + (y_offset / <float>ry_inner if ry_inner > 0 else 0)**2) <= 1:
                        px = x0 + x_offset; py = y0 + y_offset
                        if 0 <= px < canvas_width and 0 <= py < canvas_height: inner_ellipse.add((px, py))
        pixels.update(full_ellipse - inner_ellipse)
    return pixels

cpdef tuple apply_pixels_cy(set pixels_to_process, dict active_layer_data, str color, int alpha, bint color_blending):
    cdef dict pixels_before = {}
    cdef dict pixels_after = {}
    cdef tuple original_pixel, new_pixel_data
    cdef str applied_hex
    cdef int applied_alpha
    cdef int px, py
    
    for px, py in pixels_to_process:
        original_pixel = active_layer_data.get((px, py))
        pixels_before[(px, py)] = original_pixel
        
        applied_hex = color
        applied_alpha = alpha

        if color_blending and 0 < alpha < 255 and original_pixel and original_pixel[1] > 0:
            applied_hex, applied_alpha = blend_colors_cy(color, alpha, original_pixel[0], original_pixel[1])
        
        new_pixel_data = (applied_hex, applied_alpha) if applied_alpha > 0 else None
        
        if original_pixel != new_pixel_data:
            if new_pixel_data:
                active_layer_data[(px, py)] = new_pixel_data
            elif (px, py) in active_layer_data:
                del active_layer_data[(px, py)]
        pixels_after[(px, py)] = active_layer_data.get((px,py))

    return (pixels_before, pixels_after)

cpdef tuple pick_color_at_pixel_cy(int px, int py, list visible_layers_data):
    cdef tuple pixel_data
    cdef int i
    for i in range(len(visible_layers_data) - 1, -1, -1):
        pixel_data = visible_layers_data[i].get((px, py))
        if pixel_data and pixel_data[1] > 0:
            return pixel_data
    return None
