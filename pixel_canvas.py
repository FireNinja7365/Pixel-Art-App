import tkinter as tk
from tkinter import ttk
from PIL import Image, ImageTk, ImageDraw
import math
from collections import defaultdict

from actions import PixelAction
from utilities import blend_colors, bresenham_line, hex_to_rgb, rgb_to_hex


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
        v_scroll = ttk.Scrollbar(self, orient=tk.VERTICAL)
        h_scroll = ttk.Scrollbar(self, orient=tk.HORIZONTAL)
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
        if self._force_full_redraw or self._full_art_image_cache is None:
            if self.app.show_canvas_background_var.get():
                final_full = Image.new(
                    "RGBA",
                    (self.app.canvas_width, self.app.canvas_height),
                    hex_to_rgb(self.app.canvas_bg_color) + (255,),
                )
            else:
                bg_full = Image.new(
                    "RGBA", (self.app.canvas_width, self.app.canvas_height)
                )
                draw_bg, c1, c2 = (
                    ImageDraw.Draw(bg_full),
                    (224, 224, 224),
                    (240, 240, 240),
                )
                for y in range(self.app.canvas_height):
                    for x in range(self.app.canvas_width):
                        draw_bg.point((x, y), fill=c1 if (x + y) % 2 == 0 else c2)
                final_full = bg_full
            e_alpha = 255 if not self.app.render_pixel_alpha_var.get() else None
            for layer in self.app.layers:
                if not layer.visible:
                    continue
                layer_img = Image.new(
                    "RGBA",
                    (self.app.canvas_width, self.app.canvas_height),
                    (0, 0, 0, 0),
                )
                for (px, py), (hex_color, alpha) in layer.pixel_data.items():
                    layer_img.putpixel(
                        (px, py), hex_to_rgb(hex_color) + (e_alpha or alpha,)
                    )
                final_full.alpha_composite(layer_img)
            self._full_art_image_cache, self._force_full_redraw, self._dirty_bbox = (
                final_full,
                False,
                None,
            )
        elif self._dirty_bbox is not None:
            min_x, min_y, max_x, max_y = self._dirty_bbox
            width, height = max_x - min_x, max_y - min_y
            if self.app.show_canvas_background_var.get():
                dirty_final = Image.new(
                    "RGBA",
                    (width, height),
                    hex_to_rgb(self.app.canvas_bg_color) + (255,),
                )
            else:
                dirty_bg = Image.new("RGBA", (width, height))
                draw_bg, c1, c2 = (
                    ImageDraw.Draw(dirty_bg),
                    (224, 224, 224),
                    (240, 240, 240),
                )
                for y in range(height):
                    for x in range(width):
                        draw_bg.point(
                            (x, y),
                            fill=c1 if ((x + min_x) + (y + min_y)) % 2 == 0 else c2,
                        )
                dirty_final = dirty_bg
            e_alpha = 255 if not self.app.render_pixel_alpha_var.get() else None
            for layer in self.app.layers:
                if not layer.visible:
                    continue
                dirty_layer_img = Image.new("RGBA", (width, height), (0, 0, 0, 0))
                for (px, py), (hex_color, alpha) in layer.pixel_data.items():
                    if min_x <= px < max_x and min_y <= py < max_y:
                        dirty_layer_img.putpixel(
                            (px - min_x, py - min_y),
                            hex_to_rgb(hex_color) + (e_alpha or alpha,),
                        )
                dirty_final.alpha_composite(dirty_layer_img)
            self._full_art_image_cache.paste(dirty_final, (min_x, min_y))
            self._dirty_bbox = None
        if self._full_art_image_cache is None:
            return
        canvas_x_start, canvas_y_start = self.canvas.canvasx(0), self.canvas.canvasy(0)
        px_start, py_start = max(
            0, math.floor(canvas_x_start / self.app.pixel_size)
        ), max(0, math.floor(canvas_y_start / self.app.pixel_size))
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
        px, py = int(canvas_x / self.app.pixel_size), int(
            canvas_y / self.app.pixel_size
        )
        return (
            (px, py)
            if 0 <= px < self.app.canvas_width and 0 <= py < self.app.canvas_height
            else (None, None)
        )

    def draw_pixel(self, x, y, source_hex, source_alpha, active_layer_data):
        if x is None or y is None:
            return
        original_pixel = active_layer_data.get((x, y))
        applied_hex, applied_alpha = source_hex, source_alpha
        if (
            self.app.color_blending_var.get()
            and 0 < source_alpha < 255
            and original_pixel
            and original_pixel[1] > 0
        ):
            bg_hex, bg_a_int = original_pixel
            applied_hex, applied_alpha = blend_colors(
                source_hex, source_alpha, bg_hex, bg_a_int
            )

        new_pixel_data = (applied_hex, applied_alpha) if applied_alpha > 0 else None
        if original_pixel != new_pixel_data:
            if new_pixel_data:
                active_layer_data[(x, y)] = new_pixel_data
            elif (x, y) in active_layer_data:
                del active_layer_data[(x, y)]
            self._update_dirty_bbox(x, y)

    def _get_brush_pixels(self, center_x, center_y, brush_size):
        offset = (brush_size - 1) // 2
        start_x, start_y = center_x - offset, center_y - offset
        for y_off in range(brush_size):
            py = start_y + y_off
            if 0 <= py < self.app.canvas_height:
                for x_off in range(brush_size):
                    px = start_x + x_off
                    if 0 <= px < self.app.canvas_width:
                        yield (px, py)

    def _get_composite_pixel_color_under_layer(self, x, y, layer_index):
        if self.app.show_canvas_background_var.get():
            bg_rgb = hex_to_rgb(self.app.canvas_bg_color)
        else:
            bg_rgb = (224, 224, 224) if (x + y) % 2 == 0 else (240, 240, 240)

        composite_rgb = bg_rgb
        for i in range(layer_index):
            layer = self.app.layers[i]
            if not layer.visible:
                continue
            pixel_data = layer.pixel_data.get((x, y))
            if pixel_data and pixel_data[1] > 0:
                hex_color, alpha = pixel_data
                alpha_to_use = alpha if self.app.render_pixel_alpha_var.get() else 255
                if alpha_to_use > 0:
                    fg_rgb = hex_to_rgb(hex_color)
                    alpha_norm = alpha_to_use / 255.0
                    composite_rgb = tuple(
                        fg_rgb[c] * alpha_norm + composite_rgb[c] * (1 - alpha_norm)
                        for c in range(3)
                    )
        return composite_rgb

    def _calculate_preview_pixel_rgba(self, x, y, is_eraser, tool_options):
        active_layer_index = tool_options["active_layer_index"]
        base_rgb = self._get_composite_pixel_color_under_layer(x, y, active_layer_index)
        applied_hex, applied_alpha = None, 0

        if not is_eraser:
            source_hex, source_alpha = tool_options["color"], tool_options["alpha"]
            applied_hex, applied_alpha = source_hex, source_alpha
            existing_pixel = tool_options["active_layer_data"].get((x, y))
            if (
                self.app.color_blending_var.get()
                and 0 < source_alpha < 255
                and existing_pixel
                and existing_pixel[1] > 0
            ):
                bg_hex, bg_a_int = existing_pixel
                applied_hex, applied_alpha = blend_colors(
                    source_hex, source_alpha, bg_hex, bg_a_int
                )

        composite_rgb = base_rgb
        if applied_alpha > 0:
            alpha_to_use = (
                applied_alpha if self.app.render_pixel_alpha_var.get() else 255
            )
            alpha_norm = alpha_to_use / 255.0
            applied_rgb = hex_to_rgb(applied_hex)
            composite_rgb = tuple(
                applied_rgb[c] * alpha_norm + base_rgb[c] * (1.0 - alpha_norm)
                for c in range(3)
            )

        final_rgb = composite_rgb
        for i in range(active_layer_index + 1, len(self.app.layers)):
            layer = self.app.layers[i]
            if not layer.visible:
                continue
            pixel_above_data = layer.pixel_data.get((x, y))
            if pixel_above_data and pixel_above_data[1] > 0:
                hex_above, alpha_above = pixel_above_data
                alpha_to_use = (
                    alpha_above if self.app.render_pixel_alpha_var.get() else 255
                )
                if alpha_to_use > 0:
                    alpha_norm = alpha_to_use / 255.0
                    rgb_above = hex_to_rgb(hex_above)
                    final_rgb = tuple(
                        rgb_above[c] * alpha_norm + final_rgb[c] * (1.0 - alpha_norm)
                        for c in range(3)
                    )

        final_rgb_int = tuple(min(255, max(0, int(round(c)))) for c in final_rgb)
        return final_rgb_int + (255,)

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
            if self.drawing:
                self._schedule_preview_render()
            return

        tool_options = self.app._get_tool_options()
        is_eraser = tool_options["tool"] == "eraser"

        dirty_chunks = defaultdict(list)
        for px, py in self.new_preview_pixels:
            cx, cy = px // self.CHUNK_SIZE, py // self.CHUNK_SIZE
            dirty_chunks[(cx, cy)].append((px, py))
        self.new_preview_pixels.clear()

        for (cx, cy), pixels_in_chunk in dirty_chunks.items():
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
            pil_image = chunk["pil"]

            for px, py in pixels_in_chunk:
                rgba = self._calculate_preview_pixel_rgba(
                    px, py, is_eraser, tool_options
                )

                img_x, img_y = px % self.CHUNK_SIZE, py % self.CHUNK_SIZE
                pil_image.putpixel((img_x, img_y), rgba)

            final_w = self.CHUNK_SIZE * self.app.pixel_size
            if final_w > 0:
                resized_img = pil_image.resize((final_w, final_w), Image.NEAREST)
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
        if target_data == (new_color_hex, new_alpha) and not (
            self.app.color_blending_var.get() and 0 < new_alpha < 255
        ):
            return
        if target_data == ("transparent", 0) and new_alpha == 0:
            return
        stack, processed, pixels_before = [(start_x, start_y)], set(), {}
        while stack:
            x, y = stack.pop()
            if (
                not (0 <= x < self.app.canvas_width and 0 <= y < self.app.canvas_height)
                or (x, y) in processed
            ):
                continue
            current_pixel_data = active_layer_data.get((x, y), ("transparent", 0))
            if current_pixel_data == target_data:
                pixels_before[(x, y)] = current_pixel_data
                processed.add((x, y))
                self.draw_pixel(x, y, new_color_hex, new_alpha, active_layer_data)
                for dx, dy in [(0, 1), (0, -1), (1, 0), (-1, 0)]:
                    stack.append((x + dx, y + dy))
        if processed:
            pixels_after = {(x, y): active_layer_data.get((x, y)) for x, y in processed}
            action = PixelAction(
                tool_options["active_layer_index"], pixels_before, pixels_after
            )
            self.app.add_action(action)
            self.rescale_canvas()

    def start_draw(self, event, tool_options):
        px, py = self.get_pixel_coords(event.x, event.y)
        if px is None or not tool_options["active_layer"]:
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

            initial_pixels = set(
                self._get_brush_pixels(px, py, tool_options["brush_size"])
            )
            self.stroke_pixels_drawn_this_stroke.update(initial_pixels)
            self.new_preview_pixels.update(initial_pixels)

            self._schedule_preview_render()

    def draw(self, event, tool_options):
        if not self.drawing or self.app.eyedropper_mode:
            return
        curr_px, curr_py = self.get_pixel_coords(event.x, event.y)
        tool = tool_options["tool"]
        if tool == "shape":

            if curr_px is None or self.start_shape_point is None:
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
                    x_s, y_s, x_c, y_c, fill=tool_options["color"], width=1, dash=(4, 2)
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
                    c_x0, c_y0, c_x1, c_y1, outline=tool_options["color"], dash=(4, 2)
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
                    dash=(4, 2),
                )
            if self.preview_shape_item:
                self.canvas.tag_raise(self.preview_shape_item)
        elif tool != "fill":

            if curr_px is None:
                self.last_draw_pixel_x = self.last_draw_pixel_y = None
                return
            if (curr_px, curr_py) == (self.last_draw_pixel_x, self.last_draw_pixel_y):
                return

            pixels_to_add = set()
            if self.last_draw_pixel_x is not None:
                for p_x, p_y in bresenham_line(
                    self.last_draw_pixel_x, self.last_draw_pixel_y, curr_px, curr_py
                ):
                    for brush_px, brush_py in self._get_brush_pixels(
                        p_x, p_y, tool_options["brush_size"]
                    ):
                        if (
                            brush_px,
                            brush_py,
                        ) not in self.stroke_pixels_drawn_this_stroke:
                            self.stroke_pixels_drawn_this_stroke.add(
                                (brush_px, brush_py)
                            )
                            pixels_to_add.add((brush_px, brush_py))

            self.new_preview_pixels.update(pixels_to_add)
            self.last_draw_pixel_x, self.last_draw_pixel_y = curr_px, curr_py

    def stop_draw(self, event, tool_options):
        if not self.drawing or not tool_options["active_layer"]:
            return

        self.drawing = False
        self._render_preview_frame()
        self._cleanup_preview()

        tool, active_layer_data = (
            tool_options["tool"],
            tool_options["active_layer_data"],
        )
        pixels_to_process, pixels_before = set(), {}
        if tool == "shape":

            if self.preview_shape_item:
                self.canvas.delete(self.preview_shape_item)
                self.preview_shape_item = None
            end_px, end_py = self.get_pixel_coords(event.x, event.y)
            if self.start_shape_point is None or end_px is None:
                self.start_shape_point = None
                return
            x0, y0 = self.start_shape_point
            shape_type, lock_aspect = (
                tool_options["shape_type"],
                tool_options["lock_aspect"],
            )
            if shape_type == "Line":
                pixels_to_process.update(bresenham_line(x0, y0, end_px, end_py))
            elif shape_type == "Rectangle":
                ex, ey = end_px, end_py
                if lock_aspect:
                    side = max(abs(end_px - x0), abs(end_py - y0))
                    ex, ey = x0 + side * (-1 if end_px < x0 else 1), y0 + side * (
                        -1 if end_py < y0 else 1
                    )
                xs, ys, xe, ye = min(x0, ex), min(y0, ey), max(x0, ex), max(y0, ey)
                if tool_options["fill_shape"]:
                    for y in range(ys, ye + 1):
                        for x in range(xs, xe + 1):
                            if (
                                0 <= x < self.app.canvas_width
                                and 0 <= y < self.app.canvas_height
                            ):
                                pixels_to_process.add((x, y))
                else:
                    for x in range(xs, xe + 1):
                        if 0 <= x < self.app.canvas_width:
                            if 0 <= ys < self.app.canvas_height:
                                pixels_to_process.add((x, ys))
                            if 0 <= ye < self.app.canvas_height:
                                pixels_to_process.add((x, ye))
                    for y in range(ys + 1, ye):
                        if 0 <= y < self.app.canvas_height:
                            if 0 <= xs < self.app.canvas_width:
                                pixels_to_process.add((xs, y))
                            if 0 <= xe < self.app.canvas_width:
                                pixels_to_process.add((xe, y))
            elif shape_type == "Ellipse":
                rx_u, ry_u = abs(end_px - x0), abs(end_py - y0)
                rx, ry = (
                    (max(rx_u, ry_u), max(rx_u, ry_u)) if lock_aspect else (rx_u, ry_u)
                )
                if tool_options["fill_shape"]:
                    if rx == 0 and ry == 0:
                        pixels_to_process.add((x0, y0))
                    else:
                        for y_offset in range(-ry, ry + 1):
                            for x_offset in range(-rx, rx + 1):
                                if ((x_offset / rx) ** 2 if rx > 0 else 0) + (
                                    (y_offset / ry) ** 2 if ry > 0 else 0
                                ) <= 1:
                                    px, py = x0 + x_offset, y0 + y_offset
                                    if (
                                        0 <= px < self.app.canvas_width
                                        and 0 <= py < self.app.canvas_height
                                    ):
                                        pixels_to_process.add((px, py))
                else:
                    full_ellipse, inner_ellipse = set(), set()
                    if rx > 0 and ry > 0:
                        for y_offset in range(-ry, ry + 1):
                            for x_offset in range(-rx, rx + 1):
                                if (x_offset / rx) ** 2 + (y_offset / ry) ** 2 <= 1:
                                    px, py = x0 + x_offset, y0 + y_offset
                                    if (
                                        0 <= px < self.app.canvas_width
                                        and 0 <= py < self.app.canvas_height
                                    ):
                                        full_ellipse.add((px, py))
                        rx_inner, ry_inner = max(0, rx - 1), max(0, ry - 1)
                        if rx_inner > 0 and ry_inner > 0:
                            for y_offset in range(-ry_inner, ry_inner + 1):
                                for x_offset in range(-rx_inner, rx_inner + 1):
                                    if (x_offset / rx_inner) ** 2 + (
                                        y_offset / ry_inner
                                    ) ** 2 <= 1:
                                        px, py = x0 + x_offset, y0 + y_offset
                                        if (
                                            0 <= px < self.app.canvas_width
                                            and 0 <= py < self.app.canvas_height
                                        ):
                                            inner_ellipse.add((px, py))
                        pixels_to_process.update(full_ellipse - inner_ellipse)
                    else:
                        for px, py in bresenham_line(
                            x0 - rx, y0 - ry, x0 + rx, y0 + ry
                        ):
                            if (
                                0 <= px < self.app.canvas_width
                                and 0 <= py < self.app.canvas_height
                            ):
                                pixels_to_process.add((px, py))
            if pixels_to_process:
                for px, py in pixels_to_process:
                    pixels_before[(px, py)] = active_layer_data.get((px, py))
            for px, py in pixels_to_process:
                self.draw_pixel(
                    px,
                    py,
                    tool_options["color"],
                    tool_options["alpha"],
                    active_layer_data,
                )
            self.start_shape_point = None
        elif tool in ["pencil", "eraser"]:
            pixels_to_process = self.stroke_pixels_drawn_this_stroke.copy()
            if pixels_to_process:
                for px, py in pixels_to_process:
                    pixels_before[(px, py)] = active_layer_data.get((px, py))
                is_eraser = tool == "eraser"
                color, alpha = (
                    ("transparent", 0)
                    if is_eraser
                    else (tool_options["color"], tool_options["alpha"])
                )
                for px, py in pixels_to_process:
                    self.draw_pixel(px, py, color, alpha, active_layer_data)
            self.last_draw_pixel_x = self.last_draw_pixel_y = None
        if pixels_to_process:
            pixels_after = {
                (px, py): active_layer_data.get((px, py))
                for px, py in pixels_to_process
            }
            action = PixelAction(
                tool_options["active_layer_index"], pixels_before, pixels_after
            )
            self.app.add_action(action)
            self.rescale_canvas()

    def _core_pick_color_at_pixel(self, px, py):

        if px is None:
            return False
        for layer in reversed(self.app.layers):
            if not layer.visible:
                continue
            pixel_data = layer.pixel_data.get((px, py))
            if pixel_data and pixel_data[1] > 0:
                self.pick_color_callback(pixel_data[0], pixel_data[1])
                return True
        return False

    def start_mmb_eyedropper(self, event):

        px, py = self.get_pixel_coords(event.x, event.y)
        if px is None:
            return
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
