import tkinter as tk
from tkinter import ttk
from PIL import Image, ImageTk, ImageDraw
import math
from collections import defaultdict
import functools

from actions import PixelAction


import canvas_cython_helpers


class PixelCanvas(ttk.Frame):
    CHUNK_SIZE = 32

    def __init__(self, master, app_instance, pick_color_callback):
        super().__init__(master)
        self.app = app_instance
        self.pick_color_callback = pick_color_callback

        self.drawing = False
        self.panning = False
        self.mmb_eyedropper_active = False
        self.original_cursor_before_mmb = ""
        self.original_cursor_before_pan = ""
        self.art_sprite_image, self.art_sprite_canvas_item = None, None
        self._after_id_render, self._after_id_resize = None, None

        self._full_art_image_cache = None
        self._force_full_redraw = True
        self._dirty_bbox = None

        self.last_draw_pixel_x, self.last_draw_pixel_y = None, None
        self.stroke_pixels_drawn_this_stroke = set()
        self.start_shape_point, self.preview_shape_item = None, None

        self.preview_chunks = {}
        self.new_preview_pixels = set()
        self._after_id_preview_render = None
        self.PREVIEW_RENDER_INTERVAL_MS = 10

        self._setup_widgets()
        self._bind_events()

    def _setup_widgets(self):

        style = ttk.Style()

        style.layout(
            "NoArrows.Vertical.TScrollbar",
            [
                (
                    "Vertical.Scrollbar.trough",
                    {
                        "children": [
                            (
                                "Vertical.Scrollbar.thumb",
                                {"expand": "1", "sticky": "nswe"},
                            )
                        ],
                        "sticky": "ns",
                    },
                )
            ],
        )

        style.layout(
            "NoArrows.Horizontal.TScrollbar",
            [
                (
                    "Horizontal.Scrollbar.trough",
                    {
                        "children": [
                            (
                                "Horizontal.Scrollbar.thumb",
                                {"expand": "1", "sticky": "nswe"},
                            )
                        ],
                        "sticky": "ew",
                    },
                )
            ],
        )

        v_scroll = ttk.Scrollbar(
            self, orient=tk.VERTICAL, style="NoArrows.Vertical.TScrollbar"
        )
        h_scroll = ttk.Scrollbar(
            self, orient=tk.HORIZONTAL, style="NoArrows.Horizontal.TScrollbar"
        )

        self.canvas = tk.Canvas(
            self,
            bg="#C0C0C0",
            yscrollcommand=v_scroll.set,
            xscrollcommand=h_scroll.set,
            highlightthickness=0,
        )
        v_scroll.config(command=self.on_scroll_y)
        h_scroll.config(command=self.on_scroll_x)
        v_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        h_scroll.pack(side=tk.BOTTOM, fill=tk.X)
        self.canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        v_scroll.bind("<Button-1>", lambda e: self._handle_scroll_click(e, "vertical"))
        h_scroll.bind(
            "<Button-1>", lambda e: self._handle_scroll_click(e, "horizontal")
        )

    def _handle_scroll_click(self, event, orientation):
        scrollbar = event.widget

        if "thumb" in scrollbar.identify(event.x, event.y):
            return

        if orientation == "vertical":
            total_len = scrollbar.winfo_height()
            click_pos = event.y
            view_get = self.canvas.yview
            view_moveto = self.canvas.yview_moveto
        else:
            total_len = scrollbar.winfo_width()
            click_pos = event.x
            view_get = self.canvas.xview
            view_moveto = self.canvas.xview_moveto

        if total_len > 0:
            click_ratio = click_pos / total_len
            start, end = view_get()
            viewport_ratio = end - start

            new_start = click_ratio - (viewport_ratio / 2)
            view_moveto(new_start)
            self._update_visible_canvas_image()

        return "break"

    def _bind_events(self):
        self.canvas.bind("<Button-2>", self.start_mmb_eyedropper)
        self.canvas.bind("<B2-Motion>", self.mmb_eyedropper_motion)
        self.canvas.bind("<ButtonRelease-2>", self.stop_mmb_eyedropper)
        self.canvas.bind("<Button-3>", self.start_pan)
        self.canvas.bind("<B3-Motion>", self.pan_motion)
        self.canvas.bind("<ButtonRelease-3>", self.stop_pan)
        self.canvas.bind("<MouseWheel>", self.on_canvas_scroll)
        self.canvas.bind("<Button-4>", self.on_canvas_scroll)
        self.canvas.bind("<Button-5>", self.on_canvas_scroll)

    def schedule_rescale(self):
        if self._after_id_resize:
            self.app.root.after_cancel(self._after_id_resize)
        self._after_id_resize = self.app.root.after(50, self.rescale_canvas)

    def force_redraw(self):
        self._force_full_redraw = True
        self.rescale_canvas()

    def create_canvas(self):
        self.canvas.delete("all")
        self.art_sprite_image = self._full_art_image_cache = None
        self._force_full_redraw = True
        self._dirty_bbox = None
        self.art_sprite_canvas_item = self.canvas.create_image(
            0, 0, anchor="nw", tags="art_sprite"
        )
        for _ in range(self.app.canvas_height - 1):
            self.canvas.create_line(0, 0, 0, 0, fill=self.app.grid_color, tags="grid_h")
        for _ in range(self.app.canvas_width - 1):
            self.canvas.create_line(0, 0, 0, 0, fill=self.app.grid_color, tags="grid_v")
        self.rescale_canvas()
        self.canvas.tag_raise("grid_h", "art_sprite")
        self.canvas.tag_raise("grid_v", "art_sprite")
        self.center_canvas_view()

    def center_canvas_view(self):
        self.canvas.update_idletasks()
        total_width, total_height = (
            self.app.canvas_width * self.app.pixel_size,
            self.app.canvas_height * self.app.pixel_size,
        )
        viewport_width, viewport_height = (
            self.canvas.winfo_width(),
            self.canvas.winfo_height(),
        )
        if viewport_width <= 1 or viewport_height <= 1:
            self.app.root.after(50, self.center_canvas_view)
            return
        target_x, target_y = (total_width - viewport_width) / 2, (
            total_height - viewport_height
        ) / 2
        s_region_str = self.canvas.cget("scrollregion")
        if not s_region_str:
            self._update_visible_canvas_image()
            return
        try:
            s_x1, s_y1, s_x2, s_y2 = map(float, s_region_str.split())
            total_scroll_width, total_scroll_height = s_x2 - s_x1, s_y2 - s_y1
            if total_scroll_width > 0:
                self.canvas.xview_moveto((target_x - s_x1) / total_scroll_width)
            if total_scroll_height > 0:
                self.canvas.yview_moveto((target_y - s_y1) / total_scroll_height)
        except (ValueError, IndexError):
            pass
        self._update_visible_canvas_image()

    def _update_dirty_bbox(self, x, y):
        if self._dirty_bbox is None:
            self._dirty_bbox = (x, y, x + 1, y + 1)
        else:
            min_x, min_y, max_x, max_y = self._dirty_bbox
            self._dirty_bbox = (
                min(min_x, x),
                min(min_y, y),
                max(max_x, x + 1),
                max(max_y, y + 1),
            )

    def _update_canvas_scaling(self):
        total_width, total_height = (
            self.app.canvas_width * self.app.pixel_size,
            self.app.canvas_height * self.app.pixel_size,
        )
        grid_state = "normal" if self.app.show_grid_var.get() else "hidden"
        for i, line_id in enumerate(self.canvas.find_withtag("grid_h")):
            self.canvas.coords(
                line_id,
                0,
                (i + 1) * self.app.pixel_size,
                total_width,
                (i + 1) * self.app.pixel_size,
            )
            self.canvas.itemconfig(line_id, state=grid_state)
        for i, line_id in enumerate(self.canvas.find_withtag("grid_v")):
            self.canvas.coords(
                line_id,
                (i + 1) * self.app.pixel_size,
                0,
                (i + 1) * self.app.pixel_size,
                total_height,
            )
            self.canvas.itemconfig(line_id, state=grid_state)
        margin = 50
        viewport_width, viewport_height = max(1, self.canvas.winfo_width()), max(
            1, self.canvas.winfo_height()
        )
        padding_x, padding_y = max(0, viewport_width - margin), max(
            0, viewport_height - margin
        )
        self.canvas.configure(
            scrollregion=(
                -padding_x,
                -padding_y,
                total_width + padding_x,
                total_height + padding_y,
            )
        )

    def rescale_canvas(self):
        self._update_canvas_scaling()
        self._update_visible_canvas_image()

    def _update_visible_canvas_image(self):
        if self._after_id_render:
            self.app.root.after_cancel(self._after_id_render)
        self._after_id_render = None

        viewport_w, viewport_h = self.canvas.winfo_width(), self.canvas.winfo_height()
        if viewport_w <= 1 or viewport_h <= 1:
            self._after_id_render = self.app.root.after(
                50, self._update_visible_canvas_image
            )
            return

        visible_layers_info = [
            (layer.pixel_data, layer.opacity)
            for layer in self.app.layers
            if layer.visible
        ]
        use_bg = self.app.show_canvas_background_var.get()
        bg_rgb = canvas_cython_helpers.hex_to_rgb_cy(self.app.canvas_bg_color)
        render_alpha = self.app.render_pixel_alpha_var.get()

        if self._force_full_redraw or self._full_art_image_cache is None:

            image_buffer = canvas_cython_helpers.render_image(
                self.app.canvas_width,
                self.app.canvas_height,
                visible_layers_info,
                use_bg,
                bg_rgb,
                render_alpha,
            )
            self._full_art_image_cache = Image.frombytes(
                "RGBA",
                (self.app.canvas_width, self.app.canvas_height),
                bytes(image_buffer),
            )
            self._force_full_redraw = False
            self._dirty_bbox = None

        elif self._dirty_bbox is not None:
            dirty_w = self._dirty_bbox[2] - self._dirty_bbox[0]
            dirty_h = self._dirty_bbox[3] - self._dirty_bbox[1]
            dirty_buffer = canvas_cython_helpers.render_image(
                self.app.canvas_width,
                self.app.canvas_height,
                visible_layers_info,
                use_bg,
                bg_rgb,
                render_alpha,
                self._dirty_bbox,
            )
            dirty_image = Image.frombytes(
                "RGBA", (dirty_w, dirty_h), bytes(dirty_buffer)
            )
            self._full_art_image_cache.paste(
                dirty_image, (self._dirty_bbox[0], self._dirty_bbox[1])
            )
            self._dirty_bbox = None

        if self._full_art_image_cache is None:
            return

        canvas_x_start, canvas_y_start = self.canvas.canvasx(0), self.canvas.canvasy(0)
        px_start = max(0, math.floor(canvas_x_start / self.app.pixel_size))
        py_start = max(0, math.floor(canvas_y_start / self.app.pixel_size))
        px_end = min(
            self.app.canvas_width,
            math.ceil((canvas_x_start + viewport_w) / self.app.pixel_size),
        )
        py_end = min(
            self.app.canvas_height,
            math.ceil((canvas_y_start + viewport_h) / self.app.pixel_size),
        )

        if px_start >= px_end or py_start >= py_end:
            self.canvas.itemconfig(self.art_sprite_canvas_item, image=""),
            self.art_sprite_image = None
            return

        art_image_cropped = self._full_art_image_cache.crop(
            (px_start, py_start, px_end, py_end)
        )
        final_w, final_h = (px_end - px_start) * self.app.pixel_size, (
            py_end - py_start
        ) * self.app.pixel_size

        if final_w <= 0 or final_h <= 0:
            return

        self.art_sprite_image = ImageTk.PhotoImage(
            art_image_cropped.resize((final_w, final_h), Image.NEAREST)
        )
        self.canvas.itemconfig(self.art_sprite_canvas_item, image=self.art_sprite_image)
        self.canvas.coords(
            self.art_sprite_canvas_item,
            px_start * self.app.pixel_size,
            py_start * self.app.pixel_size,
        )
        self.canvas.tag_lower(self.art_sprite_canvas_item)

    def on_scroll_y(self, *args):
        self.canvas.yview(*args)
        self._update_visible_canvas_image()

    def on_scroll_x(self, *args):
        self.canvas.xview(*args)
        self._update_visible_canvas_image()

    def on_canvas_scroll(self, event):
        old_pixel_size = self.app.pixel_size
        current_canvas_x, current_canvas_y = self.canvas.canvasx(
            event.x
        ), self.canvas.canvasy(event.y)
        zoom_in = event.delta > 0 or event.num == 4
        new_pixel_size = (
            self.app.pixel_size + 1
            if zoom_in and self.app.pixel_size < 3
            else (
                self.app.pixel_size * self.app.zoom_factor
                if zoom_in
                else self.app.pixel_size / self.app.zoom_factor
            )
        )
        new_pixel_size = max(
            self.app.min_pixel_size, min(self.app.max_pixel_size, round(new_pixel_size))
        )
        if new_pixel_size == old_pixel_size:
            return
        self.app.pixel_size = new_pixel_size
        self._update_canvas_scaling()
        pixel_x_at_cursor, pixel_y_at_cursor = (
            current_canvas_x / old_pixel_size,
            current_canvas_y / old_pixel_size,
        )
        new_canvas_x_for_pixel, new_canvas_y_for_pixel = (
            pixel_x_at_cursor * self.app.pixel_size,
            pixel_y_at_cursor * self.app.pixel_size,
        )
        new_scroll_x_abs, new_scroll_y_abs = (
            new_canvas_x_for_pixel - event.x,
            new_canvas_y_for_pixel - event.y,
        )
        s_region_str = self.canvas.cget("scrollregion")
        if s_region_str:
            try:
                s_x1, s_y1, s_x2, s_y2 = map(int, s_region_str.split())
                total_scroll_width, total_scroll_height = s_x2 - s_x1, s_y2 - s_y1
                if total_scroll_width > 0:
                    self.canvas.xview_moveto(
                        (new_scroll_x_abs - s_x1) / total_scroll_width
                    )
                if total_scroll_height > 0:
                    self.canvas.yview_moveto(
                        (new_scroll_y_abs - s_y1) / total_scroll_height
                    )
            except (ValueError, IndexError):
                pass

        if self.drawing:
            self.app.on_canvas_motion_1(event)

            for (cx, cy), chunk in self.preview_chunks.items():
                canvas_x = cx * self.CHUNK_SIZE * self.app.pixel_size
                canvas_y = cy * self.CHUNK_SIZE * self.app.pixel_size
                self.canvas.coords(chunk["item"], canvas_x, canvas_y)

                final_w = self.CHUNK_SIZE * self.app.pixel_size
                resized_img = chunk["pil"].resize((final_w, final_w), Image.NEAREST)
                chunk["photo"] = ImageTk.PhotoImage(resized_img)
                self.canvas.itemconfig(chunk["item"], image=chunk["photo"])

        if self.panning:
            self.canvas.scan_mark(event.x, event.y)
        self._update_visible_canvas_image()

    def get_pixel_coords(self, event_x, event_y):
        canvas_x, canvas_y = self.canvas.canvasx(event_x), self.canvas.canvasy(event_y)

        px, py = math.floor(canvas_x / self.app.pixel_size), math.floor(
            canvas_y / self.app.pixel_size
        )

        return px, py

    def _schedule_preview_render(self):
        if self._after_id_preview_render is None:
            self._after_id_preview_render = self.app.root.after(
                self.PREVIEW_RENDER_INTERVAL_MS, self._render_preview_frame
            )

    def _render_preview_frame(self):
        self._after_id_preview_render = None
        if not self.drawing and not self.new_preview_pixels:
            return

        if not self.new_preview_pixels:
            return

        tool_opts = self.app._get_tool_options()

        tool_opts["color_blending"] = self.app.color_blending_var.get()

        visible_layers_info = [
            (layer.pixel_data, layer.opacity)
            for layer in self.app.layers
            if layer.visible
        ]
        use_bg = self.app.show_canvas_background_var.get()
        bg_rgb = canvas_cython_helpers.hex_to_rgb_cy(self.app.canvas_bg_color)
        render_alpha = self.app.render_pixel_alpha_var.get()

        rendered_buffers = canvas_cython_helpers.render_preview_chunks_cy(
            self.new_preview_pixels,
            tool_opts,
            visible_layers_info,
            use_bg,
            bg_rgb,
            render_alpha,
            self.CHUNK_SIZE,
            self.app.canvas_width,
            self.app.canvas_height,
        )
        self.new_preview_pixels.clear()

        for (cx, cy), buffer in rendered_buffers.items():
            if (cx, cy) not in self.preview_chunks:
                canvas_x = cx * self.CHUNK_SIZE * self.app.pixel_size
                canvas_y = cy * self.CHUNK_SIZE * self.app.pixel_size
                new_chunk = {
                    "pil": Image.new("RGBA", (self.CHUNK_SIZE, self.CHUNK_SIZE)),
                    "item": self.canvas.create_image(canvas_x, canvas_y, anchor="nw"),
                    "photo": None,
                }
                self.preview_chunks[(cx, cy)] = new_chunk

            chunk = self.preview_chunks[(cx, cy)]

            pil_image = Image.frombytes(
                "RGBA", (self.CHUNK_SIZE, self.CHUNK_SIZE), bytes(buffer)
            )

            chunk["pil"].paste(pil_image, mask=pil_image)

            final_w = self.CHUNK_SIZE * self.app.pixel_size
            if final_w > 0:
                resized_img = chunk["pil"].resize((final_w, final_w), Image.NEAREST)
                chunk["photo"] = ImageTk.PhotoImage(resized_img)
                self.canvas.itemconfig(chunk["item"], image=chunk["photo"])

        if self.drawing:
            self._schedule_preview_render()

    def _cleanup_preview(self):
        if self._after_id_preview_render:
            self.app.root.after_cancel(self._after_id_preview_render)
            self._after_id_preview_render = None

        for chunk in self.preview_chunks.values():
            self.canvas.delete(chunk["item"])

        self.preview_chunks.clear()
        self.new_preview_pixels.clear()

    def flood_fill(self, start_x, start_y, tool_options):
        active_layer_data = tool_options["active_layer_data"]
        new_color_hex, new_alpha = tool_options["color"], tool_options["alpha"]
        if start_x is None:
            return

        target_data = active_layer_data.get((start_x, start_y), ("transparent", 0))
        new_pixel_data = (new_color_hex, new_alpha)

        if target_data == new_pixel_data:
            return

        if target_data == ("transparent", 0) and new_alpha == 0:
            return

        pixels_before, pixels_after = canvas_cython_helpers.flood_fill_apply_cy(
            start_x,
            start_y,
            self.app.canvas_width,
            self.app.canvas_height,
            active_layer_data,
            target_data,
            new_color_hex,
            new_alpha,
        )

        if not pixels_before:
            return

        self._dirty_bbox = (0, 0, self.app.canvas_width, self.app.canvas_height)

        action = PixelAction(
            tool_options["active_layer_index"], pixels_before, pixels_after
        )
        self.app.add_action(action)
        self.rescale_canvas()

    def draw(self, event, tool_options):
        if not self.drawing or self.app.eyedropper_mode:
            return

        tool = tool_options["tool"]

        curr_px, curr_py = self.get_pixel_coords(event.x, event.y)

        if tool == "shape":

            if self.start_shape_point is None:
                return
            if self.preview_shape_item:
                self.canvas.delete(self.preview_shape_item)
            x0, y0 = self.start_shape_point
            shape_type, lock_aspect = (
                tool_options["shape_type"],
                tool_options["lock_aspect"],
            )
            if shape_type == "Line":
                x_s, y_s, x_c, y_c = (
                    (x0 + 0.5) * self.app.pixel_size,
                    (y0 + 0.5) * self.app.pixel_size,
                    (curr_px + 0.5) * self.app.pixel_size,
                    (curr_py + 0.5) * self.app.pixel_size,
                )
                self.preview_shape_item = self.canvas.create_line(
                    x_s, y_s, x_c, y_c, fill=tool_options["color"], width=2
                )
            elif shape_type == "Rectangle":
                ex, ey = curr_px, curr_py
                if lock_aspect:
                    side = max(abs(curr_px - x0), abs(curr_py - y0))
                    ex, ey = x0 + side * (-1 if curr_px < x0 else 1), y0 + side * (
                        -1 if curr_py < y0 else 1
                    )
                c_x0, c_y0 = (
                    min(x0, ex) * self.app.pixel_size,
                    min(y0, ey) * self.app.pixel_size,
                )
                c_x1, c_y1 = (max(x0, ex) + 1) * self.app.pixel_size, (
                    max(y0, ey) + 1
                ) * self.app.pixel_size
                self.preview_shape_item = self.canvas.create_rectangle(
                    c_x0, c_y0, c_x1, c_y1, outline=tool_options["color"], width=2
                )
            elif shape_type == "Ellipse":
                cx, cy = (x0 + 0.5) * self.app.pixel_size, (
                    y0 + 0.5
                ) * self.app.pixel_size
                rx_u, ry_u = abs((curr_px + 0.5) * self.app.pixel_size - cx), abs(
                    (curr_py + 0.5) * self.app.pixel_size - cy
                )
                rx_f, ry_f = (
                    (max(rx_u, ry_u), max(rx_u, ry_u)) if lock_aspect else (rx_u, ry_u)
                )
                self.preview_shape_item = self.canvas.create_oval(
                    cx - rx_f,
                    cy - ry_f,
                    cx + rx_f,
                    cy + ry_f,
                    outline=tool_options["color"],
                    width=2,
                )
            if self.preview_shape_item:
                self.canvas.tag_raise(self.preview_shape_item)

        elif tool != "fill":

            if (curr_px, curr_py) == (self.last_draw_pixel_x, self.last_draw_pixel_y):
                return

            pixels_to_add = set()

            if self.last_draw_pixel_x is not None:

                pixels_to_add = canvas_cython_helpers.get_stroke_pixels_cy(
                    self.last_draw_pixel_x,
                    self.last_draw_pixel_y,
                    curr_px,
                    curr_py,
                    tool_options["brush_size"],
                    self.app.canvas_width,
                    self.app.canvas_height,
                    self.stroke_pixels_drawn_this_stroke,
                )

                if pixels_to_add:
                    self.new_preview_pixels.update(pixels_to_add)

                    self._schedule_preview_render()

            self.last_draw_pixel_x, self.last_draw_pixel_y = curr_px, curr_py

    def stop_draw(self, event, tool_options):
        if not self.drawing or not tool_options["active_layer"]:
            return

        self.drawing = False
        self._render_preview_frame()
        self._cleanup_preview()

        tool = tool_options["tool"]
        active_layer_data = tool_options["active_layer_data"]
        pixels_to_process = set()

        if tool == "shape":
            if self.preview_shape_item:
                self.canvas.delete(self.preview_shape_item)
                self.preview_shape_item = None

            end_px, end_py = self.get_pixel_coords(event.x, event.y)

            if self.start_shape_point:
                x0, y0 = self.start_shape_point
                shape_type = tool_options["shape_type"]
                lock_aspect = tool_options["lock_aspect"]

                if shape_type == "Line":
                    pixels_to_process.update(
                        canvas_cython_helpers.bresenham_line_cy(x0, y0, end_px, end_py)
                    )
                elif shape_type == "Rectangle":
                    ex, ey = end_px, end_py
                    if lock_aspect:
                        side = max(abs(end_px - x0), abs(end_py - y0))
                        ex = x0 + side * (-1 if end_px < x0 else 1)
                        ey = y0 + side * (-1 if end_py < y0 else 1)
                    pixels_to_process.update(
                        canvas_cython_helpers.get_rectangle_pixels_cy(
                            x0,
                            y0,
                            ex,
                            ey,
                            tool_options["fill_shape"],
                            self.app.canvas_width,
                            self.app.canvas_height,
                        )
                    )
                elif shape_type == "Ellipse":
                    rx_u, ry_u = abs(end_px - x0), abs(end_py - y0)
                    rx, ry = (
                        (max(rx_u, ry_u), max(rx_u, ry_u))
                        if lock_aspect
                        else (rx_u, ry_u)
                    )
                    pixels_to_process.update(
                        canvas_cython_helpers.get_ellipse_pixels_cy(
                            x0,
                            y0,
                            rx,
                            ry,
                            tool_options["fill_shape"],
                            self.app.canvas_width,
                            self.app.canvas_height,
                        )
                    )

            self.start_shape_point = None

        elif tool in ["pencil", "eraser"]:
            pixels_to_process = self.stroke_pixels_drawn_this_stroke
            self.last_draw_pixel_x = self.last_draw_pixel_y = None

        if pixels_to_process:
            is_eraser = tool == "eraser"
            color, alpha = (
                ("transparent", 0)
                if is_eraser
                else (tool_options["color"], tool_options["alpha"])
            )

            pixels_before, pixels_after = canvas_cython_helpers.apply_pixels_cy(
                pixels_to_process,
                active_layer_data,
                color,
                alpha,
                self.app.color_blending_var.get(),
                self.app.canvas_width,
                self.app.canvas_height,
            )

            if pixels_before:
                for px, py in pixels_to_process:
                    self._update_dirty_bbox(px, py)
                action = PixelAction(
                    tool_options["active_layer_index"], pixels_before, pixels_after
                )
                self.app.add_action(action)
                self.rescale_canvas()

    def start_draw(self, event, tool_options):
        px, py = self.get_pixel_coords(event.x, event.y)
        if not tool_options["active_layer"]:
            return
        if self.app.eyedropper_mode:
            self.app.pick_color_from_canvas_tool(px, py)
            return
        if not tool_options["active_layer"].visible:
            self.app.show_hidden_layer_warning()
            return

        self._cleanup_preview()
        self.drawing = True
        self.stroke_pixels_drawn_this_stroke.clear()

        tool = tool_options["tool"]
        if tool == "shape":
            self.start_shape_point = (px, py)
        elif tool == "fill":
            self.flood_fill(px, py, tool_options)
        else:
            self.last_draw_pixel_x, self.last_draw_pixel_y = px, py

            initial_pixels = canvas_cython_helpers.get_brush_pixels_cy(
                px,
                py,
                tool_options["brush_size"],
                self.app.canvas_width,
                self.app.canvas_height,
            )
            self.stroke_pixels_drawn_this_stroke.update(initial_pixels)
            self.new_preview_pixels.update(initial_pixels)

            self._schedule_preview_render()

    def _core_pick_color_at_pixel(self, px, py):
        visible_layers_info = [
            (layer.pixel_data, layer.opacity)
            for layer in self.app.layers
            if layer.visible
        ]
        pixel_data = canvas_cython_helpers.pick_color_at_pixel_cy(
            px, py, visible_layers_info
        )
        if pixel_data:
            self.pick_color_callback(pixel_data[0], pixel_data[1])
            return True
        return False

    def start_mmb_eyedropper(self, event):
        px, py = self.get_pixel_coords(event.x, event.y)
        self.mmb_eyedropper_active = True
        self.original_cursor_before_mmb = self.canvas.cget("cursor")
        self.canvas.configure(cursor="dotbox")
        self._core_pick_color_at_pixel(px, py)

    def mmb_eyedropper_motion(self, event):
        if self.mmb_eyedropper_active:
            self._core_pick_color_at_pixel(*self.get_pixel_coords(event.x, event.y))

    def stop_mmb_eyedropper(self, event):
        if self.mmb_eyedropper_active:
            self.mmb_eyedropper_active = False
            self.canvas.configure(cursor=self.original_cursor_before_mmb)

    def start_pan(self, event):
        self.panning = True
        self.original_cursor_before_pan = self.canvas.cget("cursor")
        self.canvas.config(cursor="fleur")
        self.canvas.scan_mark(event.x, event.y)

    def pan_motion(self, event):
        self.canvas.scan_dragto(event.x, event.y, gain=1)
        self._update_visible_canvas_image()

    def stop_pan(self, event):
        self.panning = False
        self.canvas.config(cursor=self.original_cursor_before_pan)
