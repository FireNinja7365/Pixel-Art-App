import tkinter as tk
from tkinter import ttk
from PIL import Image, ImageTk, ImageDraw
import math
import colorsys

from utilities import (
    hex_to_rgb,
    rgb_to_hex,
    handle_slider_click,
    sanitize_hex_input,
    sanitize_int_input,
    validate_hex_entry,
    validate_int_entry,
)


class ColorWheelPicker(ttk.Frame):
    def __init__(
        self, parent, color_change_callback, show_alpha=True, show_preview=True
    ):
        super().__init__(parent)
        self.pack(pady=5)
        self.color_change_callback = color_change_callback
        self.show_alpha = show_alpha
        self.show_preview = show_preview

        self.hue, self.saturation, self.value = 0.0, 1.0, 1.0
        self.alpha = 255
        self.indicator_radius, self.sv_indicator_radius = 6, 9
        self.drag_mode = None
        self._is_updating = False
        self.preview_image_tk = None

        canvas_size = 150
        self.sv_box_size = 72
        self.sv_box_offset = (canvas_size - self.sv_box_size) / 2

        if self.show_preview:
            self._create_preview_canvas()

        self.color_canvas = tk.Canvas(
            self, width=canvas_size, height=canvas_size, highlightthickness=0
        )
        self.color_canvas.pack()

        self._create_input_fields()
        self.create_hue_wheel()

        self.hue_indicator = self.color_canvas.create_oval(
            0, 0, 0, 0, fill="white", outline="black", width=1, tags=("hue_indicator",)
        )
        self.sv_indicator = self.color_canvas.create_oval(
            0, 0, 0, 0, fill="white", outline="black", width=1, tags=("sv_indicator",)
        )

        self.set_color("#000000", 255, run_callback=False)

        for tag in ["hue_area", "hue_indicator"]:
            self.color_canvas.tag_bind(tag, "<Button-1>", self.start_hue_drag)
        for tag in ["sv_area", "sv_indicator"]:
            self.color_canvas.tag_bind(tag, "<Button-1>", self.start_sv_drag)
        self.color_canvas.bind("<B1-Motion>", self.on_canvas_drag)
        self.color_canvas.bind("<ButtonRelease-1>", self.stop_drag)

    def _create_preview_canvas(self):
        preview_container = ttk.Frame(self)
        preview_container.pack(pady=(0, 5))
        self.preview_canvas = tk.Canvas(
            preview_container,
            width=120,
            height=30,
            relief=tk.SUNKEN,
            bd=2,
            highlightthickness=0,
        )
        self.preview_canvas.pack()

    def _create_input_fields(self):
        inputs_container = ttk.Frame(self)
        inputs_container.pack(pady=(10, 0))

        color_inputs_frame = ttk.Frame(inputs_container)
        color_inputs_frame.pack()
        self.hex_var, self.r_var, self.g_var, self.b_var = (
            tk.StringVar(),
            tk.StringVar(),
            tk.StringVar(),
            tk.StringVar(),
        )

        ttk.Label(color_inputs_frame, text="HEX:", width=5).grid(
            row=0, column=0, padx=(0, 5), sticky="w"
        )

        vcmd_hex = (self.register(validate_hex_entry), "%P")

        hex_entry = ttk.Entry(
            color_inputs_frame,
            textvariable=self.hex_var,
            width=10,
            validate="key",
            validatecommand=vcmd_hex,
        )
        hex_entry.grid(row=0, column=1, columnspan=3, sticky="we")
        hex_entry.bind("<KeyRelease>", self._on_hex_input)
        hex_entry.bind("<FocusOut>", self._on_hex_input)

        ttk.Label(color_inputs_frame, text="RGB:", width=5).grid(
            row=1, column=0, padx=(0, 5), pady=(5, 0), sticky="w"
        )

        vcmd_int = (self.register(validate_int_entry), "%P")

        for i, var in enumerate([self.r_var, self.g_var, self.b_var]):
            entry = ttk.Entry(
                color_inputs_frame,
                textvariable=var,
                width=4,
                validate="key",
                validatecommand=vcmd_int,
            )
            entry.grid(row=1, column=i + 1, pady=(5, 0), sticky="w")
            entry.bind("<KeyRelease>", self._on_rgb_input)
            entry.bind("<FocusOut>", self._on_rgb_input_focus_out)

        if self.show_alpha:
            alpha_frame = ttk.Frame(inputs_container)
            alpha_frame.pack(fill=tk.X, pady=(10, 0))
            self.alpha_var = tk.StringVar()
            ttk.Label(alpha_frame, text="A:", width=2).pack(side=tk.LEFT, padx=(0, 5))
            alpha_entry = ttk.Entry(
                alpha_frame,
                textvariable=self.alpha_var,
                width=6,
                validate="key",
                validatecommand=vcmd_int,
            )
            alpha_entry.pack(side=tk.LEFT, padx=(0, 10))
            alpha_entry.bind("<KeyRelease>", self._on_alpha_entry_change)
            alpha_entry.bind("<FocusOut>", self._on_alpha_entry_focus_out)
            self.alpha_slider = tk.Scale(
                alpha_frame,
                from_=0,
                to=255,
                orient=tk.HORIZONTAL,
                showvalue=0,
                command=self._on_alpha_slider_change,
                bg="#A0A0A0",
                troughcolor="#E0E0E0",
                activebackground="#606060",
                sliderrelief=tk.RAISED,
                width=15,
                sliderlength=20,
                highlightthickness=0,
                bd=0,
            )
            self.alpha_slider.pack(side=tk.LEFT, fill=tk.X, expand=True)
            self.alpha_slider.bind(
                "<Button-1>", lambda e: handle_slider_click(e, self.alpha_slider)
            )

    def set_color(self, hex_color, alpha=None, run_callback=True):
        if self._is_updating:
            return
        if not hex_color or not hex_color.startswith("#"):
            return

        r, g, b = hex_to_rgb(hex_color)
        self.hue, self.saturation, self.value = colorsys.rgb_to_hsv(
            r / 255.0, g / 255.0, b / 255.0
        )
        if alpha is not None and self.show_alpha:
            self.alpha = max(0, min(255, int(alpha)))

        self._update_ui()
        if run_callback:
            self._fire_callback()

    def _fire_callback(self):
        rgb_float = colorsys.hsv_to_rgb(self.hue, self.saturation, self.value)
        r, g, b = tuple(int(c * 255) for c in rgb_float)
        hex_color = rgb_to_hex(r, g, b)
        self.color_change_callback(hex_color, self.alpha)

    def _update_ui(self):
        if self._is_updating:
            return
        self._is_updating = True
        self.update_sv_box()
        self._update_indicators()
        self._update_text_inputs()
        if self.show_alpha:
            self._update_alpha_widgets()
        if self.show_preview:
            self._update_preview()
        self._is_updating = False

    def _update_preview(self):
        rgb_float = colorsys.hsv_to_rgb(self.hue, self.saturation, self.value)
        r, g, b = tuple(int(c * 255) for c in rgb_float)

        if self.show_alpha:
            width, height = (
                self.preview_canvas.winfo_width(),
                self.preview_canvas.winfo_height(),
            )
            if width <= 1 or height <= 1:
                self.after(50, self._update_preview)
                return
            checker_size = 6
            bg_img = Image.new("RGBA", (width, height))
            draw_bg = ImageDraw.Draw(bg_img)
            for y in range(0, height, checker_size):
                for x in range(0, width, checker_size):
                    fill = (
                        (224, 224, 224, 255)
                        if (x // checker_size + y // checker_size) % 2
                        else (245, 245, 245, 255)
                    )
                    draw_bg.rectangle(
                        [x, y, x + checker_size, y + checker_size], fill=fill
                    )

            overlay_img = Image.new("RGBA", (width, height), (r, g, b, self.alpha))
            final_img = Image.alpha_composite(bg_img, overlay_img)
            self.preview_image_tk = ImageTk.PhotoImage(final_img)
            self.preview_canvas.delete("all")
            self.preview_canvas.create_image(
                0, 0, image=self.preview_image_tk, anchor="nw"
            )
        else:
            hex_color = rgb_to_hex(r, g, b)
            self.preview_canvas.config(bg=hex_color)

    def _update_indicators(self):
        angle, radius, center = self.hue * 2 * math.pi, 63.75, 75
        indicator_x = center + radius * math.cos(angle)
        indicator_y = center - radius * math.sin(angle)
        self.color_canvas.coords(
            self.hue_indicator,
            indicator_x - self.indicator_radius,
            indicator_y - self.indicator_radius,
            indicator_x + self.indicator_radius,
            indicator_y + self.indicator_radius,
        )

        sv_x = self.sv_box_offset + self.saturation * (self.sv_box_size - 1)
        sv_y = self.sv_box_offset + (1.0 - self.value) * (self.sv_box_size - 1)
        self.color_canvas.coords(
            self.sv_indicator,
            sv_x - self.sv_indicator_radius,
            sv_y - self.sv_indicator_radius,
            sv_x + self.sv_indicator_radius,
            sv_y + self.sv_indicator_radius,
        )

    def _update_text_inputs(self):
        rgb_float = colorsys.hsv_to_rgb(self.hue, self.saturation, self.value)
        r, g, b = tuple(int(c * 255) for c in rgb_float)
        self.hex_var.set(rgb_to_hex(r, g, b).lstrip("#"))
        self.r_var.set(str(r))
        self.g_var.set(str(g))
        self.b_var.set(str(b))

    def _update_alpha_widgets(self):
        alpha_str = str(self.alpha)
        if self.alpha_var.get() != alpha_str:
            self.alpha_var.set(alpha_str)
        if self.alpha_slider.get() != self.alpha:
            self.alpha_slider.set(self.alpha)

    def create_hue_wheel(self):
        size = 150
        radius = center_x = center_y = size // 2
        image = Image.new("RGBA", (size, size), (0, 0, 0, 0))
        pixels = image.load()
        for y in range(size):
            for x in range(size):
                dx, dy = x - center_x, y - center_y
                dist_sq = dx**2 + dy**2
                if (radius * 0.7) ** 2 < dist_sq < radius**2:
                    hue = (math.atan2(-dy, dx) / (2 * math.pi)) % 1.0
                    rgb_float = colorsys.hsv_to_rgb(hue, 1.0, 1.0)
                    pixels[x, y] = tuple(int(c * 255) for c in rgb_float) + (255,)
        self.hue_wheel_image = ImageTk.PhotoImage(image)
        self.color_canvas.create_image(
            center_x, center_y, image=self.hue_wheel_image, tags="hue_area"
        )

    def update_sv_box(self):
        self.color_canvas.delete("gradient")
        size = self.sv_box_size
        gradient_img = Image.new("RGB", (size, size))
        pixels = gradient_img.load()
        for y in range(size):
            val = 1.0 - (y / (size - 1))
            for x in range(size):
                sat = x / (size - 1)
                rgb_float = colorsys.hsv_to_rgb(self.hue, sat, val)
                pixels[x, y] = tuple(int(c * 255) for c in rgb_float)
        self.sv_image = ImageTk.PhotoImage(gradient_img)
        self.color_canvas.create_image(
            self.sv_box_offset,
            self.sv_box_offset,
            anchor=tk.NW,
            image=self.sv_image,
            tags=("sv_area", "gradient"),
        )
        self.color_canvas.tag_raise("hue_indicator")
        self.color_canvas.tag_raise("sv_indicator")

    def start_hue_drag(self, event):
        self.drag_mode = "hue"
        self._update_from_drag(event.x, event.y)

    def start_sv_drag(self, event):
        self.drag_mode = "sv"
        self._update_from_drag(event.x, event.y)

    def stop_drag(self, event):
        self.drag_mode = None

    def on_canvas_drag(self, event):
        self._update_from_drag(event.x, event.y)

    def _update_from_drag(self, x, y):
        if not self.drag_mode:
            return
        if self.drag_mode == "hue":
            center_x, center_y = 75, 75
            dx, dy = x - center_x, y - center_y
            if not (dx == 0 and dy == 0):
                self.hue = (math.atan2(-dy, dx) / (2 * math.pi)) % 1.0
        elif self.drag_mode == "sv":
            x = max(
                self.sv_box_offset, min(x, self.sv_box_offset + self.sv_box_size - 1)
            )
            y = max(
                self.sv_box_offset, min(y, self.sv_box_offset + self.sv_box_size - 1)
            )
            self.saturation = max(
                0.0, min(1.0, (x - self.sv_box_offset) / (self.sv_box_size - 1))
            )
            self.value = max(
                0.0, min(1.0, 1.0 - (y - self.sv_box_offset) / (self.sv_box_size - 1))
            )
        self._update_ui()
        self._fire_callback()

    def _on_hex_input(self, event):
        if self._is_updating:
            return

        current_val = self.hex_var.get()

        sanitized_val, is_valid = sanitize_hex_input(current_val)

        if is_valid:
            self.set_color(f"#{sanitized_val .lower ()}")

    def _on_rgb_input(self, event=None):
        if self._is_updating:
            return
        try:
            for var in [self.r_var, self.g_var, self.b_var]:
                sanitized = sanitize_int_input(var.get())
                if sanitized is not None:
                    var.set(sanitized)

            r, g, b = (
                int(self.r_var.get() or 0),
                int(self.g_var.get() or 0),
                int(self.b_var.get() or 0),
            )
            self.set_color(rgb_to_hex(r, g, b))
        except (ValueError, tk.TclError):
            pass

    def _on_rgb_input_focus_out(self, event):
        if self._is_updating:
            return
        try:
            for var in [self.r_var, self.g_var, self.b_var]:
                if not var.get():
                    var.set("0")
        except tk.TclError:
            pass
        self._on_rgb_input()

    def _on_alpha_entry_change(self, event):
        if self._is_updating:
            return
        try:
            sanitized = sanitize_int_input(self.alpha_var.get())
            if sanitized is not None:
                self.alpha_var.set(sanitized)
                if sanitized != event.widget.get():
                    event.widget.icursor(tk.END)

            if self.alpha_var.get():
                self.alpha = int(self.alpha_var.get())
                self._update_ui()
                self._fire_callback()
        except (ValueError, tk.TclError):
            pass

    def _on_alpha_entry_focus_out(self, event):
        if self._is_updating:
            return
        try:
            val_str = self.alpha_var.get()
            self.alpha_var.set(
                "255" if not val_str else str(max(0, min(255, int(val_str))))
            )
            self.alpha = int(self.alpha_var.get())
            self._update_ui()
            self._fire_callback()
        except (ValueError, tk.TclError):
            self.alpha = 255
            self.alpha_var.set("255")
            self._update_ui()

    def _on_alpha_slider_change(self, value):
        if self._is_updating:
            return
        self.alpha = int(float(value))
        self._update_alpha_widgets()
        if self.show_preview:
            self._update_preview()
        self._fire_callback()
