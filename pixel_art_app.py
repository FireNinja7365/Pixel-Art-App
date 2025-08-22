import tkinter as tk
from tkinter import ttk, filedialog, messagebox, colorchooser, simpledialog
from PIL import Image, ImageTk, ImageDraw
from pathlib import Path
import os
import math
import colorsys
import re

from tkinterdnd2 import DND_FILES, TkinterDnD


class Action:

    def __init__(self):

        self.pixels_before = {}

        self.pixels_after = {}


class ColorWheelPicker(ttk.Frame):
    def __init__(self, parent, color_change_callback):
        super().__init__(parent)
        self.pack(pady=5)
        self.color_change_callback = color_change_callback

        self.hue, self.saturation, self.value = 0.0, 0.0, 0.0
        self.indicator_radius, self.sv_indicator_radius = 6, 9
        self.drag_mode = None

        canvas_size = 150
        self.sv_box_size = 72
        self.sv_box_offset = (canvas_size - self.sv_box_size) / 2

        self.color_canvas = tk.Canvas(
            self, width=canvas_size, height=canvas_size, highlightthickness=0
        )
        self.color_canvas.pack()

        self.create_hue_wheel()

        hue_angle, wheel_radius, canvas_center = 0.0, 63.75, 75
        hue_indicator_x = canvas_center + wheel_radius * math.cos(hue_angle)
        hue_indicator_y = canvas_center + wheel_radius * math.sin(hue_angle)
        self.hue_indicator = self.color_canvas.create_oval(
            hue_indicator_x - self.indicator_radius,
            hue_indicator_y - self.indicator_radius,
            hue_indicator_x + self.indicator_radius,
            hue_indicator_y + self.indicator_radius,
            fill="white",
            outline="black",
            width=1,
            tags=("hue_indicator",),
        )

        sv_x = self.sv_box_offset + self.saturation * (self.sv_box_size - 1)
        sv_y = self.sv_box_offset + (1.0 - self.value) * (self.sv_box_size - 1)
        r = self.sv_indicator_radius
        self.sv_indicator = self.color_canvas.create_oval(
            sv_x - r,
            sv_y - r,
            sv_x + r,
            sv_y + r,
            fill="white",
            outline="black",
            width=1,
            tags=("sv_indicator",),
        )

        self.update_sv_box()
        self.update_color_display()

        for tag in ["hue_area", "hue_indicator"]:
            self.color_canvas.tag_bind(tag, "<Button-1>", self.start_hue_drag)
        for tag in ["sv_area", "sv_indicator"]:
            self.color_canvas.tag_bind(tag, "<Button-1>", self.start_sv_drag)
        self.color_canvas.bind("<B1-Motion>", self.on_canvas_drag)
        self.color_canvas.bind("<ButtonRelease-1>", self.stop_drag)

    def _hex_to_rgb(self, hex_color_str):
        h = hex_color_str.lstrip("#")
        if len(h) != 6:
            return (0, 0, 0)
        try:
            return tuple(int(h[i : i + 2], 16) for i in (0, 2, 4))
        except ValueError:
            return (0, 0, 0)

    def set_color(self, hex_color):
        if not hex_color or not hex_color.startswith("#"):
            return
        r, g, b = self._hex_to_rgb(hex_color)
        self.hue, self.saturation, self.value = colorsys.rgb_to_hsv(
            r / 255.0, g / 255.0, b / 255.0
        )
        self.update_sv_box()

        angle, radius, center_x, center_y = self.hue * 2 * math.pi, 63.75, 75, 75
        indicator_x = center_x + radius * math.cos(angle)

        indicator_y = center_y - radius * math.sin(angle)
        r_hue = self.indicator_radius
        self.color_canvas.coords(
            self.hue_indicator,
            indicator_x - r_hue,
            indicator_y - r_hue,
            indicator_x + r_hue,
            indicator_y + r_hue,
        )

        sv_x = self.sv_box_offset + self.saturation * (self.sv_box_size - 1)
        sv_y = self.sv_box_offset + (1.0 - self.value) * (self.sv_box_size - 1)
        r_sv = self.sv_indicator_radius
        self.color_canvas.coords(
            self.sv_indicator, sv_x - r_sv, sv_y - r_sv, sv_x + r_sv, sv_y + r_sv
        )
        self.update_color_display(run_callback=False)

    def create_hue_wheel(self):
        size = 150
        radius = center_x = center_y = size // 2
        image = Image.new("RGBA", (size, size), (0, 0, 0, 0))
        pixels = image.load()
        for y in range(size):
            for x in range(size):
                dx, dy = x - center_x, y - center_y
                if radius * 0.7 < math.sqrt(dx**2 + dy**2) < radius:
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
        self.update_hue(event.x, event.y)

    def start_sv_drag(self, event):
        self.drag_mode = "sv"
        self.update_sv(event.x, event.y)

    def stop_drag(self, event):
        self.drag_mode = None

    def on_canvas_drag(self, event):
        if self.drag_mode == "hue":
            self.update_hue(event.x, event.y)
        elif self.drag_mode == "sv":
            self.update_sv(event.x, event.y)

    def update_hue(self, x, y):
        center_x, center_y = 75, 75
        dx, dy = x - center_x, y - center_y
        if dx == 0 and dy == 0:
            return
        angle = math.atan2(-dy, dx)
        self.hue = (angle / (2 * math.pi)) % 1.0
        self.update_sv_box()
        self.update_color_display()
        indicator_x = center_x + 63.75 * math.cos(angle)
        indicator_y = center_y - 63.75 * math.sin(angle)
        r = self.indicator_radius
        self.color_canvas.coords(
            self.hue_indicator,
            indicator_x - r,
            indicator_y - r,
            indicator_x + r,
            indicator_y + r,
        )

    def update_sv(self, x, y):
        x = max(self.sv_box_offset, min(x, self.sv_box_offset + self.sv_box_size - 1))
        y = max(self.sv_box_offset, min(y, self.sv_box_offset + self.sv_box_size - 1))
        self.saturation = max(
            0.0, min(1.0, (x - self.sv_box_offset) / (self.sv_box_size - 1))
        )
        self.value = max(
            0.0, min(1.0, 1.0 - (y - self.sv_box_offset) / (self.sv_box_size - 1))
        )
        self.update_color_display()
        r = self.sv_indicator_radius
        self.color_canvas.coords(self.sv_indicator, x - r, y - r, x + r, y + r)

    def update_color_display(self, run_callback=True):
        rgb_float = colorsys.hsv_to_rgb(self.hue, self.saturation, self.value)
        rgb_int = tuple(int(c * 255) for c in rgb_float)
        hex_color = f"#{rgb_int [0 ]:02x}{rgb_int [1 ]:02x}{rgb_int [2 ]:02x}"
        if run_callback:
            self.color_change_callback(hex_color)


class PixelArtApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Pixel Art Drawing App")
        self.root.geometry("1260x710")

        self.icon_path = Path(__file__).parent / "assets" / "app.ico"
        try:
            if self.icon_path.exists():
                self.root.iconbitmap(str(self.icon_path))
        except Exception as e:
            print(f"Warning: Could not set application icon: {e }")

        self.canvas_width, self.canvas_height = 100, 100
        self.canvas_bg_color = "#FFFFFF"
        self.pixel_size, self.min_pixel_size, self.max_pixel_size = 5, 1, 60
        self.brush_size = 1
        self.zoom_factor = 1.2
        self.grid_color = "#cccccc"
        self.current_color, self.current_alpha = "#000000", 255
        self.drawing, self.current_tool, self.eyedropper_mode = False, "pencil", False
        self.last_used_tool = "pencil"
        self._updating_color_inputs, self.mmb_eyedropper_active = False, False
        self.panning = False
        self.original_cursor_before_mmb, self.original_cursor_before_pan = "", ""
        self.current_filename = None
        self.pixel_data = {}
        self.art_sprite_image, self.art_sprite_canvas_item = None, None
        self._after_id_render, self._after_id_resize = None, None

        self._full_art_image_cache = None

        self._force_full_redraw = True
        self._dirty_bbox = None

        self.last_draw_pixel_x, self.last_draw_pixel_y = None, None
        self.stroke_pixels_drawn_this_stroke = set()
        self.start_shape_point, self.preview_shape_item = None, None
        self.color_preview_image_tk = None

        self.show_canvas_background_var = tk.BooleanVar(value=False)
        self.save_background_var = tk.BooleanVar(value=False)
        self.render_pixel_alpha_var = tk.BooleanVar(value=True)
        self.color_blending_var = tk.BooleanVar(value=True)
        self.show_grid_var = tk.BooleanVar(value=False)
        self.brush_size_var = tk.IntVar(value=self.brush_size)

        self.undo_stack = []
        self.redo_stack = []

        self.canvas_menu = None

        self.setup_menu()
        self.setup_ui()

        self.setup_drag_and_drop()

        self.create_canvas()
        self._update_shape_controls_state()
        self._update_brush_controls_state()
        self.update_inputs_from_current_color()
        self._update_history_controls()
        self._update_save_background_menu_state()

    def _hex_to_rgb(self, hex_color_str):
        h = hex_color_str.lstrip("#")
        if len(h) != 6:
            return (0, 0, 0)
        try:
            return tuple(int(h[i : i + 2], 16) for i in (0, 2, 4))
        except ValueError:
            return (0, 0, 0)

    def _rgb_to_hex(self, r, g, b):
        return f"#{int (r ):02x}{int (g ):02x}{int (b ):02x}"

    def _update_dirty_bbox(self, x, y):

        if self._dirty_bbox is None:
            self._dirty_bbox = (x, y, x + 1, y + 1)
        else:
            min_x, min_y, max_x, max_y = self._dirty_bbox
            min_x = min(min_x, x)
            min_y = min(min_y, y)
            max_x = max(max_x, x + 1)
            max_y = max(max_y, y + 1)
            self._dirty_bbox = (min_x, min_y, max_x, max_y)

    def setup_menu(self):
        menubar = tk.Menu(self.root)
        self.root.config(menu=menubar)

        file_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="File", menu=file_menu)
        file_menu.add_command(
            label="New", command=self.new_canvas, accelerator="Ctrl+N"
        )
        file_menu.add_separator()
        file_menu.add_command(
            label="Open PNG...", command=self.open_file, accelerator="Ctrl+O"
        )
        file_menu.add_separator()
        file_menu.add_command(
            label="Save PNG", command=self.save_file, accelerator="Ctrl+S"
        )
        file_menu.add_command(
            label="Export PNG As...",
            command=self.export_png,
            accelerator="Ctrl+Shift+S",
        )
        file_menu.add_separator()
        file_menu.add_command(
            label="Exit", command=self.root.quit, accelerator="Ctrl+Q"
        )

        self.canvas_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="Canvas", menu=self.canvas_menu)
        self.canvas_menu.add_command(
            label="Resize Canvas...", command=self.show_resize_dialog
        )
        self.canvas_menu.add_command(
            label="Set Background Color...", command=self.choose_canvas_background_color
        )
        self.canvas_menu.add_separator()
        self.canvas_menu.add_checkbutton(
            label="Show Background",
            variable=self.show_canvas_background_var,
            command=self.toggle_canvas_background_display,
        )
        self.canvas_menu.add_checkbutton(
            label="    Save Background", variable=self.save_background_var
        )
        self.canvas_menu.add_checkbutton(
            label="Show Grid",
            variable=self.show_grid_var,
            command=self.toggle_grid_visibility,
        )
        self.canvas_menu.add_checkbutton(
            label="Color Blending", variable=self.color_blending_var
        )
        self.canvas_menu.add_checkbutton(
            label="Render Pixel Alpha",
            variable=self.render_pixel_alpha_var,
            command=self.toggle_pixel_alpha_rendering,
        )

        for key, func in [
            ("<Control-n>", self.new_canvas),
            ("<Control-o>", self.open_file),
            ("<Control-s>", self.save_file),
            ("<Control-Shift-S>", self.export_png),
            ("<Control-q>", lambda e: self.root.quit()),
            ("<Control-z>", self.undo),
            ("<Control-y>", self.redo),
        ]:
            self.root.bind(key, lambda e, f=func: f())

    def _update_history_controls(self):
        undo_state = tk.NORMAL if self.undo_stack else tk.DISABLED
        redo_state = tk.NORMAL if self.redo_stack else tk.DISABLED
        if hasattr(self, "undo_button"):
            self.undo_button.config(state=undo_state)
            self.redo_button.config(state=redo_state)

    def _update_save_background_menu_state(self):
        if self.show_canvas_background_var.get():
            self.canvas_menu.entryconfig("    Save Background", state=tk.NORMAL)
        else:
            self.save_background_var.set(False)
            self.canvas_menu.entryconfig("    Save Background", state=tk.DISABLED)

    def _clear_history(self):
        self.undo_stack.clear()
        self.redo_stack.clear()
        self._update_history_controls()

    def add_action(self, action):
        if not action.pixels_before and not action.pixels_after:
            return
        self.undo_stack.append(action)
        self.redo_stack.clear()
        self._update_history_controls()

    def undo(self, event=None):
        if not self.undo_stack:
            return
        action = self.undo_stack.pop()

        for (x, y), data_before in action.pixels_before.items():
            if data_before:
                self.pixel_data[(x, y)] = data_before
            elif (x, y) in self.pixel_data:
                del self.pixel_data[(x, y)]
            self._update_dirty_bbox(x, y)

        self.redo_stack.append(action)
        self._rescale_canvas()
        self._update_history_controls()

    def redo(self, event=None):
        if not self.redo_stack:
            return
        action = self.redo_stack.pop()

        for (x, y), data_after in action.pixels_after.items():
            if data_after:
                self.pixel_data[(x, y)] = data_after
            elif (x, y) in self.pixel_data:
                del self.pixel_data[(x, y)]
            self._update_dirty_bbox(x, y)

        self.undo_stack.append(action)
        self._rescale_canvas()
        self._update_history_controls()

    def show_resize_dialog(self):
        dialog = tk.Toplevel(self.root)
        dialog.title("Resize Canvas")
        dialog.geometry("250x150")
        dialog.resizable(False, False)
        dialog.transient(self.root)
        dialog.grab_set()
        dialog.geometry(
            f"+{self .root .winfo_rootx ()+50 }+{self .root .winfo_rooty ()+50 }"
        )
        main_frame = ttk.Frame(dialog, padding=20)
        main_frame.pack(fill=tk.BOTH, expand=True)
        ttk.Label(main_frame, text="Width:").grid(
            row=0, column=0, sticky=tk.W, padx=(0, 10)
        )
        width_var = tk.StringVar(value=str(self.canvas_width))
        width_entry = ttk.Entry(main_frame, textvariable=width_var, width=10)
        width_entry.grid(row=0, column=1, pady=(0, 10))
        ttk.Label(main_frame, text="Height:").grid(
            row=1, column=0, sticky=tk.W, padx=(0, 10)
        )
        height_var = tk.StringVar(value=str(self.canvas_height))
        height_entry = ttk.Entry(main_frame, textvariable=height_var, width=10)
        height_entry.grid(row=1, column=1, pady=(0, 20))
        button_frame = ttk.Frame(main_frame)
        button_frame.grid(row=2, column=0, columnspan=2)

        def apply_resize():
            try:

                new_width, new_height = int(width_var.get()), int(height_var.get())
                if 1 <= new_width <= 2048 and 1 <= new_height <= 2048:
                    if (self.canvas_width, self.canvas_height) != (
                        new_width,
                        new_height,
                    ):
                        self.canvas_width, self.canvas_height = new_width, new_height

                        self._clear_history()
                        self.create_canvas()
                    dialog.destroy()
                else:
                    messagebox.showerror(
                        "Error",
                        "Canvas size must be between 1 and 2048 pixels",
                        parent=dialog,
                    )
            except ValueError:
                messagebox.showerror(
                    "Error", "Please enter valid numbers for canvas size", parent=dialog
                )

        ttk.Button(button_frame, text="Apply", command=apply_resize).pack(
            side=tk.LEFT, padx=(0, 10)
        )
        ttk.Button(button_frame, text="Cancel", command=dialog.destroy).pack(
            side=tk.LEFT
        )
        width_entry.focus()
        width_entry.select_range(0, tk.END)
        dialog.bind("<Return>", lambda e: apply_resize())
        dialog.bind("<Escape>", lambda e: dialog.destroy())

    def create_transparent_color_preview(self, parent_frame, width=60, height=40):
        return tk.Canvas(
            parent_frame,
            width=width,
            height=height,
            relief=tk.SUNKEN,
            bd=2,
            highlightthickness=0,
        )

    def update_color_preview(self):
        if not hasattr(self, "color_preview_canvas"):
            return
        width, height = (
            self.color_preview_canvas.winfo_width(),
            self.color_preview_canvas.winfo_height(),
        )
        if width <= 1 or height <= 1:
            self.root.after(50, self.update_color_preview)
            return
        checker_size = 6
        bg_img = Image.new("RGBA", (width, height))
        draw_bg = ImageDraw.Draw(bg_img)
        for y_bg in range(0, height, checker_size):
            for x_bg in range(0, width, checker_size):
                fill_c = (
                    (224, 224, 224, 255)
                    if (x_bg // checker_size + y_bg // checker_size) % 2
                    else (245, 245, 245, 255)
                )
                draw_bg.rectangle(
                    [x_bg, y_bg, x_bg + checker_size, y_bg + checker_size], fill=fill_c
                )
        try:
            r, g, b = self._hex_to_rgb(self.current_color)
            a = self.current_alpha
        except ValueError:
            r, g, b, a = 0, 0, 0, 255
        overlay_img = Image.new("RGBA", (width, height), (r, g, b, a))
        final_img = Image.alpha_composite(bg_img, overlay_img)
        self.color_preview_image_tk = ImageTk.PhotoImage(final_img)
        self.color_preview_canvas.delete("all")
        self.color_preview_canvas.create_image(
            0, 0, image=self.color_preview_image_tk, anchor="nw"
        )

    def on_window_resize(self, event):
        if event.widget == self.root:
            if self._after_id_resize:
                self.root.after_cancel(self._after_id_resize)
            self._after_id_resize = self.root.after(50, self._rescale_canvas)

    def _update_canvas_workarea_color(self):

        if not self.show_canvas_background_var.get():
            self.canvas.config(bg="#C0C0C0")
            return

        r, g, b = self._hex_to_rgb(self.canvas_bg_color)

        grayscale_value = int(r * 0.299 + g * 0.587 + b * 0.114)

        adjustment = 32

        if grayscale_value >= 128:
            new_gray_value = grayscale_value - adjustment

        else:
            new_gray_value = grayscale_value + adjustment

        new_gray_value = max(0, min(255, new_gray_value))

        new_hex_color = self._rgb_to_hex(new_gray_value, new_gray_value, new_gray_value)

        self.canvas.config(bg=new_hex_color)

    def setup_ui(self):
        main_frame = ttk.Frame(self.root)
        main_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        left_panel = ttk.Frame(main_frame, width=250)
        left_panel.pack(side=tk.LEFT, fill=tk.Y, padx=(0, 10))
        left_panel.pack_propagate(False)

        tools_frame = ttk.LabelFrame(left_panel, text="Tools", padding=10)
        tools_frame.pack(fill=tk.X, pady=(0, 10))
        self.tool_var = tk.StringVar(value="pencil")
        for tool in ["pencil", "eraser", "fill"]:
            ttk.Radiobutton(
                tools_frame,
                text=tool.capitalize(),
                variable=self.tool_var,
                value=tool,
                command=self.change_tool,
            ).pack(anchor=tk.W)

        shape_line_frame = ttk.Frame(tools_frame)
        shape_line_frame.pack(fill=tk.X, anchor=tk.W, pady=(2, 0))
        ttk.Radiobutton(
            shape_line_frame,
            text="Shape",
            variable=self.tool_var,
            value="shape",
            command=self.change_tool,
        ).pack(side=tk.LEFT, anchor=tk.W)
        self.shape_type_var = tk.StringVar(value="Line")
        self.shape_combobox = ttk.Combobox(
            shape_line_frame,
            textvariable=self.shape_type_var,
            values=["Line", "Rectangle", "Ellipse"],
            state="readonly",
            width=12,
        )
        self.shape_combobox.pack(side=tk.LEFT, padx=(5, 0), anchor=tk.W)
        self.shape_combobox.bind("<<ComboboxSelected>>", self.on_shape_type_change)

        self.lock_aspect_var = tk.BooleanVar(value=False)
        lock_aspect_frame = ttk.Frame(tools_frame)
        lock_aspect_frame.pack(fill=tk.X, anchor=tk.W)
        self.lock_aspect_checkbox = ttk.Checkbutton(
            lock_aspect_frame, text="Lock Aspect", variable=self.lock_aspect_var
        )
        self.lock_aspect_checkbox.pack(pady=(2, 0), padx=(20, 0), anchor=tk.W)

        self.brush_size_frame = ttk.LabelFrame(
            tools_frame, text="Brush Size", padding=5
        )
        self.brush_size_frame.pack(fill=tk.X, pady=(10, 0), anchor=tk.W)

        brush_size_inner_frame = ttk.Frame(self.brush_size_frame)
        brush_size_inner_frame.pack(fill=tk.X)

        self.brush_size_slider = tk.Scale(
            brush_size_inner_frame,
            from_=1,
            to=20,
            orient=tk.HORIZONTAL,
            showvalue=0,
            variable=self.brush_size_var,
            command=self.on_brush_size_change,
            bg="#A0A0A0",
            troughcolor="#E0E0E0",
            activebackground="#606060",
            sliderrelief=tk.RAISED,
            width=15,
            sliderlength=20,
            highlightthickness=0,
            bd=0,
        )
        self.brush_size_slider.pack(side=tk.LEFT, fill=tk.X, expand=True)
        self.brush_size_slider.bind(
            "<Button-1>", lambda e: self._on_slider_click(e, self.brush_size_slider)
        )

        self.brush_size_label = ttk.Label(
            brush_size_inner_frame,
            text=f"{self .brush_size }",
            width=5,
            anchor="e",
        )
        self.brush_size_label.pack(side=tk.RIGHT, padx=(5, 0))

        color_frame = ttk.LabelFrame(left_panel, text="Color Picker", padding=10)
        color_frame.pack(fill=tk.X, pady=(0, 10))
        preview_container = ttk.Frame(color_frame)
        preview_container.pack(pady=(0, 10))
        self.color_preview_canvas = self.create_transparent_color_preview(
            preview_container, width=120, height=40
        )
        self.color_preview_canvas.pack()
        self.color_wheel = ColorWheelPicker(color_frame, self._on_color_wheel_change)

        color_inputs_frame = ttk.Frame(color_frame)
        color_inputs_frame.pack(pady=(10, 0))
        self.hex_var, self.r_var, self.g_var, self.b_var = (
            tk.StringVar(),
            tk.StringVar(),
            tk.StringVar(),
            tk.StringVar(),
        )
        ttk.Label(color_inputs_frame, text="HEX:", width=5).grid(
            row=0, column=0, padx=(0, 5), sticky="w"
        )
        hex_entry = ttk.Entry(color_inputs_frame, textvariable=self.hex_var, width=10)
        hex_entry.grid(row=0, column=1, columnspan=3, sticky="we")
        hex_entry.bind("<KeyRelease>", self.on_hex_input)
        hex_entry.bind("<FocusOut>", self.on_hex_input)

        ttk.Label(color_inputs_frame, text="RGB:", width=5).grid(
            row=1, column=0, padx=(0, 5), pady=(5, 0), sticky="w"
        )
        digit_only_vcmd = (self.root.register(lambda v: v == "" or v.isdigit()), "%P")
        r_entry = ttk.Entry(
            color_inputs_frame,
            textvariable=self.r_var,
            width=4,
            validate="key",
            validatecommand=digit_only_vcmd,
        )
        r_entry.grid(row=1, column=1, pady=(5, 0), sticky="w")
        g_entry = ttk.Entry(
            color_inputs_frame,
            textvariable=self.g_var,
            width=4,
            validate="key",
            validatecommand=digit_only_vcmd,
        )
        g_entry.grid(row=1, column=2, pady=(5, 0), sticky="w")
        b_entry = ttk.Entry(
            color_inputs_frame,
            textvariable=self.b_var,
            width=4,
            validate="key",
            validatecommand=digit_only_vcmd,
        )
        b_entry.grid(row=1, column=3, pady=(5, 0), sticky="w")
        for entry in [r_entry, g_entry, b_entry]:
            entry.bind("<KeyRelease>", self.on_rgb_input)
            entry.bind("<FocusOut>", self.on_rgb_input_focus_out)

        alpha_frame = ttk.Frame(color_frame)
        alpha_frame.pack(fill=tk.X, pady=(10, 0))
        self.alpha_var = tk.StringVar(value="255")
        ttk.Label(alpha_frame, text="A:", width=2).pack(side=tk.LEFT, padx=(0, 5))
        alpha_entry = ttk.Entry(
            alpha_frame,
            textvariable=self.alpha_var,
            width=6,
            validate="key",
            validatecommand=digit_only_vcmd,
        )
        alpha_entry.pack(side=tk.LEFT, padx=(0, 10))
        alpha_entry.bind("<KeyRelease>", self.on_alpha_entry_change)
        alpha_entry.bind("<FocusOut>", self.on_alpha_entry_focus_out)
        self.alpha_slider = tk.Scale(
            alpha_frame,
            from_=0,
            to=255,
            orient=tk.HORIZONTAL,
            showvalue=0,
            command=self.on_alpha_slider_change,
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
            "<Button-1>", lambda e: self._on_slider_click(e, self.alpha_slider)
        )
        self.alpha_slider.set(self.current_alpha)
        ttk.Button(
            color_frame, text="Pick Color (Eyedropper)", command=self.toggle_eyedropper
        ).pack(pady=10)

        history_frame = ttk.LabelFrame(left_panel, text="History", padding=10)
        history_frame.pack(fill=tk.X, pady=(0, 10))

        button_container = ttk.Frame(history_frame)
        button_container.pack()

        self.undo_button = ttk.Button(button_container, text="Undo", command=self.undo)
        self.undo_button.pack(side=tk.LEFT, padx=(0, 5))

        self.redo_button = ttk.Button(button_container, text="Redo", command=self.redo)
        self.redo_button.pack(side=tk.LEFT)

        canvas_frame = ttk.Frame(main_frame)
        canvas_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        v_scroll = ttk.Scrollbar(canvas_frame, orient=tk.VERTICAL)
        h_scroll = ttk.Scrollbar(canvas_frame, orient=tk.HORIZONTAL)
        self.canvas = tk.Canvas(
            canvas_frame,
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

        self.canvas.bind("<Button-1>", self.start_draw)
        self.canvas.bind("<B1-Motion>", self.draw)
        self.canvas.bind("<ButtonRelease-1>", self.stop_draw)
        self.canvas.bind("<Button-2>", self.start_mmb_eyedropper)
        self.canvas.bind("<B2-Motion>", self.mmb_eyedropper_motion)
        self.canvas.bind("<ButtonRelease-2>", self.stop_mmb_eyedropper)
        self.canvas.bind("<Button-3>", self.start_pan)
        self.canvas.bind("<B3-Motion>", self.pan_motion)
        self.canvas.bind("<ButtonRelease-3>", self.stop_pan)
        self.canvas.bind("<MouseWheel>", self.on_canvas_scroll)
        self.canvas.bind("<Button-4>", self.on_canvas_scroll)
        self.canvas.bind("<Button-5>", self.on_canvas_scroll)
        self.root.bind("<Configure>", self.on_window_resize)

        self._update_canvas_workarea_color()

    def setup_drag_and_drop(self):

        self.root.drop_target_register(DND_FILES)
        self.root.dnd_bind("<<Drop>>", self.handle_drop)

    def handle_drop(self, event):

        filepath = event.data.strip("{}")

        supported_extensions = (".png", ".jpg", ".jpeg", ".gif", ".bmp")
        if not filepath.lower().endswith(supported_extensions):
            return

        prompt_message = (
            "Open this image? Any unsaved changes on the current canvas will be lost."
        )
        if messagebox.askyesno("Open Dropped File", prompt_message, parent=self.root):
            self._load_image_from_path(filepath)

    def _on_color_wheel_change(self, new_hex_color):
        if self.current_tool == "eraser":
            self.tool_var.set(self.last_used_tool)
            self.change_tool()

        self.current_color = new_hex_color

        self.update_inputs_from_current_color(source="wheel")
        self.update_color_preview()

    def on_hex_input(self, event):
        if self._updating_color_inputs:
            return
        hex_val = self.hex_var.get().lstrip("#")
        if len(hex_val) > 6:
            hex_val = hex_val[:6]
            self.hex_var.set(hex_val)
        if re.fullmatch(r"[0-9a-fA-F]{6}", hex_val):
            new_color = f"#{hex_val .lower ()}"
            if self.current_color != new_color:
                self.current_color = new_color
                self.update_inputs_from_current_color(source="hex")

    def on_rgb_input(self, event=None):
        if self._updating_color_inputs:
            return

        for var in [self.r_var, self.g_var, self.b_var]:
            try:
                val_str = var.get()
                if val_str and int(val_str) > 255:
                    var.set("255")
            except (ValueError, tk.TclError):
                pass

        try:
            r = int(self.r_var.get() or 0)
            g = int(self.g_var.get() or 0)
            b = int(self.b_var.get() or 0)

            new_color = self._rgb_to_hex(r, g, b)
            if self.current_color != new_color:
                self.current_color = new_color
                self.update_inputs_from_current_color(source="rgb")
        except (ValueError, tk.TclError):
            pass

    def on_rgb_input_focus_out(self, event):
        if self._updating_color_inputs:
            return
        try:
            for var in [self.r_var, self.g_var, self.b_var]:
                if not var.get():
                    var.set("0")
        except tk.TclError:
            pass
        self.on_rgb_input()

    def on_alpha_entry_change(self, event):
        try:
            value_str = self.alpha_var.get()
            if not value_str:
                return
            num = int(value_str)
            if num > 255:
                self.alpha_var.set("255")
                event.widget.icursor(tk.END)
            elif num < 0:
                self.alpha_var.set("0")
                event.widget.icursor(tk.END)
            self.current_alpha = int(self.alpha_var.get())
            if self.alpha_slider.get() != self.current_alpha:
                self.alpha_slider.set(self.current_alpha)
            self.update_color_preview()
        except ValueError:
            pass

    def on_alpha_entry_focus_out(self, event):
        try:
            val_str = self.alpha_var.get()
            self.alpha_var.set(
                "255" if not val_str else str(max(0, min(255, int(val_str))))
            )
            self.current_alpha = int(self.alpha_var.get())
            self.alpha_slider.set(self.current_alpha)
        except (ValueError, tk.TclError):
            self.alpha_var.set("255")
            self.alpha_slider.set(255)
            self.current_alpha = 255
        self.update_color_preview()

    def on_alpha_slider_change(self, value):
        val_int_str = str(int(float(value)))
        self.current_alpha = int(val_int_str)
        if self.alpha_var.get() != val_int_str:
            self.alpha_var.set(val_int_str)
        self.update_color_preview()

    def _on_slider_click(self, event, slider):

        element = slider.identify(event.x, event.y)
        if element not in ("trough1", "trough2"):
            return

        click_pos = event.x
        widget_size = slider.winfo_width()

        if widget_size == 0:
            return

        from_ = float(slider.cget("from"))
        to = float(slider.cget("to"))
        value_range = to - from_

        fraction = max(0.0, min(1.0, click_pos / widget_size))
        new_value = from_ + (fraction * value_range)

        slider.set(new_value)

    def on_brush_size_change(self, value):
        self.brush_size = self.brush_size_var.get()
        self.brush_size_label.config(text=f"{self .brush_size }")

    def on_scroll_y(self, *args):
        self.canvas.yview(*args)
        self._update_visible_canvas_image()

    def on_scroll_x(self, *args):
        self.canvas.xview(*args)
        self._update_visible_canvas_image()

    def on_canvas_scroll(self, event):
        old_pixel_size = self.pixel_size
        current_canvas_x, current_canvas_y = self.canvas.canvasx(
            event.x
        ), self.canvas.canvasy(event.y)
        zoom_in = event.delta > 0 or event.num == 4
        if zoom_in and self.pixel_size < 3:
            new_pixel_size = self.pixel_size + 1
        else:
            new_pixel_size = (
                self.pixel_size * self.zoom_factor
                if zoom_in
                else self.pixel_size / self.zoom_factor
            )
        new_pixel_size = max(
            self.min_pixel_size, min(self.max_pixel_size, round(new_pixel_size))
        )
        if new_pixel_size == old_pixel_size:
            return
        self.pixel_size = new_pixel_size
        self._update_canvas_scaling()

        if self.drawing:
            tool = self.tool_var.get()
            if tool in ["pencil", "eraser"]:
                self.canvas.delete("preview_stroke")
                for px, py in self.stroke_pixels_drawn_this_stroke:
                    self._draw_preview_rect(px, py, tool == "eraser")
            elif tool == "shape":
                self.draw(event)

        pixel_x_at_cursor = current_canvas_x / old_pixel_size
        pixel_y_at_cursor = current_canvas_y / old_pixel_size
        new_canvas_x_for_pixel = pixel_x_at_cursor * self.pixel_size
        new_canvas_y_for_pixel = pixel_y_at_cursor * self.pixel_size
        new_scroll_x_abs = new_canvas_x_for_pixel - event.x
        new_scroll_y_abs = new_canvas_y_for_pixel - event.y
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

        if self.panning:
            self.canvas.scan_mark(event.x, event.y)

        self._update_visible_canvas_image()

    def _update_canvas_scaling(self):
        total_width, total_height = (
            self.canvas_width * self.pixel_size,
            self.canvas_height * self.pixel_size,
        )
        grid_state = "normal" if self.show_grid_var.get() else "hidden"
        for i, line_id in enumerate(self.canvas.find_withtag("grid_h")):
            y = (i + 1) * self.pixel_size
            self.canvas.coords(line_id, 0, y, total_width, y)
            self.canvas.itemconfig(line_id, state=grid_state)
        for i, line_id in enumerate(self.canvas.find_withtag("grid_v")):
            x = (i + 1) * self.pixel_size
            self.canvas.coords(line_id, x, 0, x, total_height)
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

    def _rescale_canvas(self):
        self._update_canvas_scaling()
        self._update_visible_canvas_image()

    def on_shape_type_change(self, event=None):
        shape = self.shape_type_var.get()
        is_shape_tool_active = self.tool_var.get() == "shape"
        checkbox_text = "Lock Aspect"
        new_state = tk.DISABLED
        if is_shape_tool_active:
            if shape == "Rectangle":
                checkbox_text, new_state = "Lock Square", tk.NORMAL
            elif shape == "Ellipse":
                checkbox_text, new_state = "Lock Circle", tk.NORMAL
        self.lock_aspect_checkbox.config(text=checkbox_text, state=new_state)

    def _update_shape_controls_state(self):
        is_shape_tool = self.tool_var.get() == "shape"
        self.shape_combobox.config(state="readonly" if is_shape_tool else tk.DISABLED)
        self.on_shape_type_change()

    def _update_brush_controls_state(self):
        tool = self.tool_var.get()
        new_state = tk.NORMAL if tool in ["pencil", "eraser"] else tk.DISABLED
        self.brush_size_slider.config(state=new_state)
        self.brush_size_label.config(state=new_state)

    def update_inputs_from_current_color(self, source=None):
        if not self.current_color or not hasattr(self, "color_wheel"):
            return
        self._updating_color_inputs = True
        if source != "wheel":
            self.color_wheel.set_color(self.current_color)
        if source != "rgb":
            r, g, b = self._hex_to_rgb(self.current_color)
            self.r_var.set(str(r))
            self.g_var.set(str(g))
            self.b_var.set(str(b))
        if source != "hex":
            self.hex_var.set(self.current_color.lstrip("#"))
        alpha_str = str(self.current_alpha)
        if self.alpha_var.get() != alpha_str:
            self.alpha_var.set(alpha_str)
        if self.alpha_slider.get() != self.current_alpha:
            self.alpha_slider.set(self.current_alpha)
        self.update_color_preview()
        self._updating_color_inputs = False

    def create_canvas(self):
        self.canvas.delete("all")
        self.art_sprite_image = self._full_art_image_cache = None
        self._force_full_redraw = True
        self._dirty_bbox = None
        self.art_sprite_canvas_item = self.canvas.create_image(
            0, 0, anchor="nw", tags="art_sprite"
        )
        for _ in range(self.canvas_height - 1):
            self.canvas.create_line(0, 0, 0, 0, fill=self.grid_color, tags="grid_h")
        for _ in range(self.canvas_width - 1):
            self.canvas.create_line(0, 0, 0, 0, fill=self.grid_color, tags="grid_v")
        self._rescale_canvas()
        self.canvas.tag_raise("grid_h", "art_sprite")
        self.canvas.tag_raise("grid_v", "art_sprite")
        self.center_canvas_view()

    def center_canvas_view(self):
        self.canvas.update_idletasks()
        total_width, total_height = (
            self.canvas_width * self.pixel_size,
            self.canvas_height * self.pixel_size,
        )
        viewport_width, viewport_height = (
            self.canvas.winfo_width(),
            self.canvas.winfo_height(),
        )
        if viewport_width <= 1 or viewport_height <= 1:
            self.root.after(50, self.center_canvas_view)
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

    def _update_visible_canvas_image(self):
        if self._after_id_render:
            self.root.after_cancel(self._after_id_render)
            self._after_id_render = None

        viewport_w, viewport_h = self.canvas.winfo_width(), self.canvas.winfo_height()
        if viewport_w <= 1 or viewport_h <= 1:
            self._after_id_render = self.root.after(
                50, self._update_visible_canvas_image
            )
            return

        if self._force_full_redraw or self._full_art_image_cache is None:
            art_image_full = Image.new(
                "RGBA", (self.canvas_width, self.canvas_height), (0, 0, 0, 0)
            )
            e_alpha = 255 if not self.render_pixel_alpha_var.get() else None

            for (px, py), (hex_color, alpha) in self.pixel_data.items():
                rgb = self._hex_to_rgb(hex_color)
                art_image_full.putpixel((px, py), rgb + (e_alpha or alpha,))

            if self.show_canvas_background_var.get():
                final_full = Image.new(
                    "RGBA",
                    (self.canvas_width, self.canvas_height),
                    self._hex_to_rgb(self.canvas_bg_color) + (255,),
                )
                final_full.alpha_composite(art_image_full)
            else:
                bg_full = Image.new("RGBA", (self.canvas_width, self.canvas_height))
                draw_bg, c1, c2 = (
                    ImageDraw.Draw(bg_full),
                    (224, 224, 224),
                    (240, 240, 240),
                )
                for y in range(self.canvas_height):
                    for x in range(self.canvas_width):
                        draw_bg.point((x, y), fill=c1 if (x + y) % 2 == 0 else c2)
                final_full = Image.alpha_composite(bg_full, art_image_full)

            self._full_art_image_cache = final_full
            self._force_full_redraw = False
            self._dirty_bbox = None

        elif self._dirty_bbox is not None:
            min_x, min_y, max_x, max_y = self._dirty_bbox

            dirty_art_layer = Image.new(
                "RGBA", (max_x - min_x, max_y - min_y), (0, 0, 0, 0)
            )
            e_alpha = 255 if not self.render_pixel_alpha_var.get() else None

            for (px, py), (hex_color, alpha) in self.pixel_data.items():
                if min_x <= px < max_x and min_y <= py < max_y:
                    rgb = self._hex_to_rgb(hex_color)
                    dirty_art_layer.putpixel(
                        (px - min_x, py - min_y), rgb + (e_alpha or alpha,)
                    )

            if self.show_canvas_background_var.get():
                dirty_bg = Image.new(
                    "RGBA",
                    (max_x - min_x, max_y - min_y),
                    self._hex_to_rgb(self.canvas_bg_color) + (255,),
                )
            else:
                dirty_bg = Image.new("RGBA", (max_x - min_x, max_y - min_y))
                draw_bg, c1, c2 = (
                    ImageDraw.Draw(dirty_bg),
                    (224, 224, 224),
                    (240, 240, 240),
                )
                for y in range(max_y - min_y):
                    for x in range(max_x - min_x):
                        fill_c = c1 if ((x + min_x) + (y + min_y)) % 2 == 0 else c2
                        draw_bg.point((x, y), fill=fill_c)

            dirty_final = Image.alpha_composite(dirty_bg, dirty_art_layer)
            self._full_art_image_cache.paste(dirty_final, (min_x, min_y))

            self._dirty_bbox = None

        if self._full_art_image_cache is None:
            return

        canvas_x_start, canvas_y_start = self.canvas.canvasx(0), self.canvas.canvasy(0)
        px_start = max(0, math.floor(canvas_x_start / self.pixel_size))
        py_start = max(0, math.floor(canvas_y_start / self.pixel_size))
        px_end = min(
            self.canvas_width,
            math.ceil((canvas_x_start + viewport_w) / self.pixel_size),
        )
        py_end = min(
            self.canvas_height,
            math.ceil((canvas_y_start + viewport_h) / self.pixel_size),
        )

        if px_start >= px_end or py_start >= py_end:
            self.canvas.itemconfig(self.art_sprite_canvas_item, image="")
            self.art_sprite_image = None
            return

        art_image_cropped = self._full_art_image_cache.crop(
            (px_start, py_start, px_end, py_end)
        )
        final_w, final_h = (px_end - px_start) * self.pixel_size, (
            py_end - py_start
        ) * self.pixel_size

        if final_w <= 0 or final_h <= 0:
            return

        self.art_sprite_image = ImageTk.PhotoImage(
            art_image_cropped.resize((final_w, final_h), Image.NEAREST)
        )
        self.canvas.itemconfig(self.art_sprite_canvas_item, image=self.art_sprite_image)
        self.canvas.coords(
            self.art_sprite_canvas_item,
            px_start * self.pixel_size,
            py_start * self.pixel_size,
        )
        self.canvas.tag_lower(self.art_sprite_canvas_item)

    def get_pixel_coords(self, event_x, event_y):
        canvas_x, canvas_y = self.canvas.canvasx(event_x), self.canvas.canvasy(event_y)
        px, py = int(canvas_x / self.pixel_size), int(canvas_y / self.pixel_size)
        return (
            (px, py)
            if 0 <= px < self.canvas_width and 0 <= py < self.canvas_height
            else (None, None)
        )

    def draw_pixel(self, x, y, source_hex, source_alpha):
        if x is None or y is None:
            return
        original_pixel = self.pixel_data.get((x, y))
        applied_hex, applied_alpha = source_hex, source_alpha

        if (
            self.color_blending_var.get()
            and 0 < source_alpha < 255
            and original_pixel
            and original_pixel[1] > 0
        ):
            bg_hex, bg_a_int = original_pixel
            fg_r, fg_g, fg_b = self._hex_to_rgb(source_hex)
            bg_r, bg_g, bg_b = self._hex_to_rgb(bg_hex)
            fa, ba = source_alpha / 255.0, bg_a_int / 255.0
            out_a_norm = fa + ba * (1.0 - fa)
            if out_a_norm > 0:
                applied_alpha = min(255, int(round(out_a_norm * 255.0)))
                r = min(
                    255,
                    max(0, int(round((fg_r * fa + bg_r * ba * (1 - fa)) / out_a_norm))),
                )
                g = min(
                    255,
                    max(0, int(round((fg_g * fa + bg_g * ba * (1 - fa)) / out_a_norm))),
                )
                b = min(
                    255,
                    max(0, int(round((fg_b * fa + bg_b * ba * (1 - fa)) / out_a_norm))),
                )
                applied_hex = self._rgb_to_hex(r, g, b)
            else:
                applied_alpha, applied_hex = 0, "transparent"

        new_pixel_data = (applied_hex, applied_alpha) if applied_alpha > 0 else None
        if original_pixel != new_pixel_data:
            if new_pixel_data:
                self.pixel_data[(x, y)] = new_pixel_data
            elif (x, y) in self.pixel_data:
                del self.pixel_data[(x, y)]
            self._update_dirty_bbox(x, y)

    def _draw_line_between_pixels(self, x0, y0, x1, y1, color_hex, alpha, is_eraser):
        for px, py in self._bresenham_line_pixels(x0, y0, x1, y1):
            if (px, py) not in self.stroke_pixels_drawn_this_stroke:
                self.draw_pixel(
                    px,
                    py,
                    "transparent" if is_eraser else color_hex,
                    0 if is_eraser else alpha,
                )
                self.stroke_pixels_drawn_this_stroke.add((px, py))

    def _draw_ellipse_pixels(self, xc, yc, rx, ry, color_hex, alpha):
        pixels = set()
        rx, ry = abs(rx), abs(ry)
        if rx == 0 and ry == 0:
            pixels.add((xc, yc))
        elif rx == 0:
            for y_off in range(-ry, ry + 1):
                pixels.add((xc, yc + y_off))
        elif ry == 0:
            for x_off in range(-rx, rx + 1):
                pixels.add((xc + x_off, yc))
        else:
            for x in range(-rx, rx + 1):
                if 1 - (x / rx) ** 2 >= 0:
                    y_abs = ry * math.sqrt(1 - (x / rx) ** 2)
                    pixels.add((xc + x, yc + round(y_abs)))
                    pixels.add((xc + x, yc - round(y_abs)))
            for y in range(-ry, ry + 1):
                if 1 - (y / ry) ** 2 >= 0:
                    x_abs = rx * math.sqrt(1 - (y / ry) ** 2)
                    pixels.add((xc + round(x_abs), yc + y))
                    pixels.add((xc - round(x_abs), yc + y))
        for px, py in pixels:
            self.draw_pixel(px, py, color_hex, alpha)

    def flood_fill(self, start_x, start_y, new_color_hex, new_alpha):
        if start_x is None:
            return
        target_data = self.pixel_data.get((start_x, start_y), ("transparent", 0))
        if target_data == (new_color_hex, new_alpha) and not (
            self.color_blending_var.get() and 0 < new_alpha < 255
        ):
            return
        if target_data == ("transparent", 0) and new_alpha == 0:
            return

        action = Action()
        stack, processed = [(start_x, start_y)], set()
        while stack:
            x, y = stack.pop()
            if (
                not (0 <= x < self.canvas_width and 0 <= y < self.canvas_height)
                or (x, y) in processed
            ):
                continue

            current_pixel_data = self.pixel_data.get((x, y), ("transparent", 0))
            if current_pixel_data == target_data:
                action.pixels_before[(x, y)] = current_pixel_data
                processed.add((x, y))
                self.draw_pixel(x, y, new_color_hex, new_alpha)
                for dx, dy in [(0, 1), (0, -1), (1, 0), (-1, 0)]:
                    stack.append((x + dx, y + dy))

        if processed:
            for x, y in processed:
                action.pixels_after[(x, y)] = self.pixel_data.get((x, y))
            self.add_action(action)
            self._rescale_canvas()

    def _get_brush_pixels(self, center_x, center_y):

        if self.brush_size == 1:
            yield (center_x, center_y)
            return

        offset = (self.brush_size - 1) // 2
        start_x, start_y = center_x - offset, center_y - offset
        for y_off in range(self.brush_size):
            for x_off in range(self.brush_size):
                yield (start_x + x_off, start_y + y_off)

    def _draw_preview_rect(self, x, y, is_eraser):
        if x is None or y is None:
            return
        x0, y0 = x * self.pixel_size, y * self.pixel_size
        x1, y1 = x0 + self.pixel_size, y0 + self.pixel_size
        if self.show_canvas_background_var.get():
            ultimate_bg_rgb = self._hex_to_rgb(self.canvas_bg_color)
        else:
            ultimate_bg_rgb = (224, 224, 224) if (x + y) % 2 == 0 else (240, 240, 240)
        if is_eraser:
            self.canvas.create_rectangle(
                x0,
                y0,
                x1,
                y1,
                fill=self._rgb_to_hex(*ultimate_bg_rgb),
                outline="#000000",
                width=1,
                tags="preview_stroke",
            )
            return
        fg_rgb, fg_a_norm = (
            self._hex_to_rgb(self.current_color),
            self.current_alpha / 255.0,
        )
        if fg_a_norm == 1.0:
            self.canvas.create_rectangle(
                x0,
                y0,
                x1,
                y1,
                fill=self.current_color,
                outline="",
                tags="preview_stroke",
            )
            return
        existing, blending = self.pixel_data.get((x, y)), self.color_blending_var.get()
        if not blending or not existing:
            base_rgb = ultimate_bg_rgb
        else:
            bg_hex, bg_a_int = existing
            bg_rgb = self._hex_to_rgb(bg_hex)
            bg_a_norm = (bg_a_int / 255.0) if self.render_pixel_alpha_var.get() else 1.0
            r = bg_rgb[0] * bg_a_norm + ultimate_bg_rgb[0] * (1.0 - bg_a_norm)
            g = bg_rgb[1] * bg_a_norm + ultimate_bg_rgb[1] * (1.0 - bg_a_norm)
            b = bg_rgb[2] * bg_a_norm + ultimate_bg_rgb[2] * (1.0 - bg_a_norm)
            base_rgb = (r, g, b)
        r_out = fg_rgb[0] * fg_a_norm + base_rgb[0] * (1.0 - fg_a_norm)
        g_out = fg_rgb[1] * fg_a_norm + base_rgb[1] * (1.0 - fg_a_norm)
        b_out = fg_rgb[2] * fg_a_norm + base_rgb[2] * (1.0 - fg_a_norm)
        final_rgb = tuple(
            min(255, max(0, int(round(c)))) for c in (r_out, g_out, b_out)
        )
        self.canvas.create_rectangle(
            x0,
            y0,
            x1,
            y1,
            fill=self._rgb_to_hex(*final_rgb),
            outline="",
            tags="preview_stroke",
        )

    def _draw_preview_brush(self, center_x, center_y, is_eraser):
        for px, py in self._get_brush_pixels(center_x, center_y):
            self._draw_preview_rect(px, py, is_eraser)

    def _bresenham_line_pixels(self, x0, y0, x1, y1):
        dx, dy = abs(x1 - x0), abs(y1 - y0)
        sx, sy = (1 if x0 < x1 else -1), (1 if y0 < y1 else -1)
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

    def start_draw(self, event):
        px, py = self.get_pixel_coords(event.x, event.y)
        if px is None:
            return
        if self.eyedropper_mode:
            self.pick_color_from_canvas_tool(px, py)
            return
        self.drawing = True
        self.stroke_pixels_drawn_this_stroke.clear()
        tool = self.tool_var.get()
        if tool == "shape":
            self.start_shape_point = (px, py)
        else:
            self.last_draw_pixel_x, self.last_draw_pixel_y = px, py
            if tool == "fill":
                self.flood_fill(px, py, self.current_color, self.current_alpha)
            else:
                self._draw_preview_brush(px, py, tool == "eraser")
                for brush_px, brush_py in self._get_brush_pixels(px, py):
                    self.stroke_pixels_drawn_this_stroke.add((brush_px, brush_py))

    def draw(self, event):
        if not self.drawing or self.eyedropper_mode:
            return
        curr_px, curr_py = self.get_pixel_coords(event.x, event.y)
        tool = self.tool_var.get()
        if tool == "shape":
            if curr_px is None or self.start_shape_point is None:
                return
            if self.preview_shape_item:
                self.canvas.delete(self.preview_shape_item)
            x0, y0 = self.start_shape_point
            shape_type = self.shape_type_var.get()
            lock_aspect = self.lock_aspect_var.get() and (
                str(self.lock_aspect_checkbox.cget("state")) == "normal"
            )
            if shape_type == "Line":
                x_s, y_s, x_c, y_c = (
                    (x0 + 0.5) * self.pixel_size,
                    (y0 + 0.5) * self.pixel_size,
                    (curr_px + 0.5) * self.pixel_size,
                    (curr_py + 0.5) * self.pixel_size,
                )
                self.preview_shape_item = self.canvas.create_line(
                    x_s, y_s, x_c, y_c, fill=self.current_color, width=1, dash=(4, 2)
                )
            elif shape_type == "Rectangle":
                ex, ey = curr_px, curr_py
                if lock_aspect:
                    side = max(abs(curr_px - x0), abs(curr_py - y0))
                    ex = x0 + side * (-1 if curr_px < x0 else 1)
                    ey = y0 + side * (-1 if curr_py < y0 else 1)
                c_x0, c_y0 = (
                    min(x0, ex) * self.pixel_size,
                    min(y0, ey) * self.pixel_size,
                )
                c_x1, c_y1 = (max(x0, ex) + 1) * self.pixel_size, (
                    max(y0, ey) + 1
                ) * self.pixel_size
                self.preview_shape_item = self.canvas.create_rectangle(
                    c_x0, c_y0, c_x1, c_y1, outline=self.current_color, dash=(4, 2)
                )
            elif shape_type == "Ellipse":
                cx, cy = (x0 + 0.5) * self.pixel_size, (y0 + 0.5) * self.pixel_size
                rx_u, ry_u = abs((curr_px + 0.5) * self.pixel_size - cx), abs(
                    (curr_py + 0.5) * self.pixel_size - cy
                )
                rx_f, ry_f = (
                    (max(rx_u, ry_u), max(rx_u, ry_u)) if lock_aspect else (rx_u, ry_u)
                )
                self.preview_shape_item = self.canvas.create_oval(
                    cx - rx_f,
                    cy + ry_f,
                    cx + rx_f,
                    cy - ry_f,
                    outline=self.current_color,
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
            is_eraser = tool == "eraser"
            if self.last_draw_pixel_x is not None:
                for p_x, p_y in self._bresenham_line_pixels(
                    self.last_draw_pixel_x, self.last_draw_pixel_y, curr_px, curr_py
                ):
                    for brush_px, brush_py in self._get_brush_pixels(p_x, p_y):
                        if (
                            brush_px,
                            brush_py,
                        ) not in self.stroke_pixels_drawn_this_stroke:
                            self.stroke_pixels_drawn_this_stroke.add(
                                (brush_px, brush_py)
                            )
                            self._draw_preview_rect(brush_px, brush_py, is_eraser)
            self.last_draw_pixel_x, self.last_draw_pixel_y = curr_px, curr_py

    def stop_draw(self, event):
        if not self.drawing:
            return
        self.drawing = False
        self.canvas.delete("preview_stroke")
        tool = self.tool_var.get()
        action = Action()
        pixels_to_process = set()

        if tool == "shape":
            if self.preview_shape_item:
                self.canvas.delete(self.preview_shape_item)
                self.preview_shape_item = None
            end_px, end_py = self.get_pixel_coords(event.x, event.y)
            if self.start_shape_point is None or end_px is None:
                self.start_shape_point = None
                return
            x0, y0 = self.start_shape_point
            shape_type = self.shape_type_var.get()
            lock_aspect = self.lock_aspect_var.get() and (
                str(self.lock_aspect_checkbox.cget("state")) == "normal"
            )

            if shape_type == "Line":
                pixels_to_process.update(
                    self._bresenham_line_pixels(x0, y0, end_px, end_py)
                )
            elif shape_type == "Rectangle":
                ex, ey = end_px, end_py
                if lock_aspect:
                    side = max(abs(end_px - x0), abs(end_py - y0))
                    ex = x0 + side * (-1 if end_px < x0 else 1)
                    ey = y0 + side * (-1 if end_py < y0 else 1)
                xs, ys, xe, ye = min(x0, ex), min(y0, ey), max(x0, ex), max(y0, ey)
                for x in range(xs, xe + 1):
                    pixels_to_process.add((x, ys))
                    pixels_to_process.add((x, ye))
                for y in range(ys + 1, ye):
                    pixels_to_process.add((xs, y))
                    pixels_to_process.add((xe, y))
            elif shape_type == "Ellipse":
                rx_u, ry_u = abs(end_px - x0), abs(end_py - y0)
                rx, ry = (
                    (max(rx_u, ry_u), max(rx_u, ry_u)) if lock_aspect else (rx_u, ry_u)
                )
                bbox_x0, bbox_y0 = x0 - rx, y0 - ry
                bbox_x1, bbox_y1 = x0 + rx, y0 + ry

                for y in range(bbox_y0, bbox_y1 + 1):
                    for x in range(bbox_x0, bbox_x1 + 1):
                        if ((x - x0) / rx) ** 2 + ((y - y0) / ry) ** 2 <= 1:
                            pixels_to_process.add((x, y))

            if pixels_to_process:
                for px, py in pixels_to_process:
                    action.pixels_before[(px, py)] = self.pixel_data.get((px, py))

            if shape_type == "Line":
                for px, py in pixels_to_process:
                    self.draw_pixel(px, py, self.current_color, self.current_alpha)
            elif shape_type == "Rectangle":
                for px, py in pixels_to_process:
                    self.draw_pixel(px, py, self.current_color, self.current_alpha)
            elif shape_type == "Ellipse":

                self._draw_ellipse_pixels(
                    x0, y0, rx, ry, self.current_color, self.current_alpha
                )

            self.start_shape_point = None

        elif tool in ["pencil", "eraser"]:
            pixels_to_process = self.stroke_pixels_drawn_this_stroke.copy()
            if pixels_to_process:
                for px, py in pixels_to_process:
                    action.pixels_before[(px, py)] = self.pixel_data.get((px, py))

                is_eraser = tool == "eraser"
                color, alpha = (
                    ("transparent", 0)
                    if is_eraser
                    else (self.current_color, self.current_alpha)
                )
                for px, py in pixels_to_process:
                    self.draw_pixel(px, py, color, alpha)

            self.last_draw_pixel_x = self.last_draw_pixel_y = None

        if pixels_to_process:
            for px, py in pixels_to_process:
                action.pixels_after[(px, py)] = self.pixel_data.get((px, py))
            self.add_action(action)
            self._rescale_canvas()

    def _core_pick_color_at_pixel(self, px, py):
        if px is None:
            return False

        pixel_data = self.pixel_data.get((px, py))
        if pixel_data:
            self.current_color, self.current_alpha = pixel_data
            self.update_inputs_from_current_color()
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

    def change_tool(self):
        new_tool = self.tool_var.get()
        if self.current_tool != "eraser":
            self.last_used_tool = self.current_tool
        self.current_tool = new_tool

        if self.eyedropper_mode:
            self.toggle_eyedropper()
        if self.current_tool != "shape" and self.preview_shape_item:
            self.canvas.delete(self.preview_shape_item)
            self.preview_shape_item = None
            self.start_shape_point = None
            self.drawing = False
        self._update_shape_controls_state()
        self._update_brush_controls_state()

    def toggle_eyedropper(self):
        self.eyedropper_mode = not self.eyedropper_mode
        self.canvas.configure(cursor="dotbox" if self.eyedropper_mode else "")
        if self.eyedropper_mode and self.tool_var.get() == "fill":
            self.tool_var.set("pencil")
            self.change_tool()

    def pick_color_from_canvas_tool(self, px, py):
        self._core_pick_color_at_pixel(px, py)
        self.toggle_eyedropper()

    def choose_canvas_background_color(self):
        dialog = tk.Toplevel(self.root)
        dialog.title("Canvas Background Color")
        dialog.transient(self.root)
        dialog.grab_set()
        dialog.resizable(False, False)
        dialog.geometry(
            f"250x360+{self .root .winfo_x ()+(self .root .winfo_width ()-250 )//2 }+{self .root .winfo_y ()+(self .root .winfo_height ()-360 )//2 }"
        )
        main_frame = ttk.Frame(dialog, padding=15)
        main_frame.pack(fill=tk.BOTH, expand=True)

        state = {"hex": self.canvas_bg_color, "updating": False}
        hex_var, r_var, g_var, b_var = (
            tk.StringVar(),
            tk.StringVar(),
            tk.StringVar(),
            tk.StringVar(),
        )
        preview = tk.Label(main_frame, relief="sunken", height=2)
        preview.pack(pady=(0, 15), fill=tk.X)

        def update_ui(source=None):
            if state["updating"]:
                return
            state["updating"] = True
            preview.config(bg=state["hex"])
            if source != "wheel":
                color_wheel.set_color(state["hex"])
            if source != "hex":
                hex_var.set(state["hex"].lstrip("#"))
            if source != "rgb":
                r, g, b = self._hex_to_rgb(state["hex"])
                r_var.set(str(r))
                g_var.set(str(g))
                b_var.set(str(b))
            state["updating"] = False

        def from_wheel(new_hex):
            state["hex"] = new_hex
            update_ui("wheel")

        color_wheel = ColorWheelPicker(main_frame, from_wheel)
        color_wheel.pack()
        inputs_frame = ttk.Frame(main_frame)
        inputs_frame.pack(pady=(15, 0))

        def from_hex_input(e):
            hex_val = hex_var.get().lstrip("#")
            if len(hex_val) > 6:
                hex_val = hex_val[:6]
                hex_var.set(hex_val)
            if re.fullmatch(r"[0-9a-fA-F]{6}", hex_val):
                state["hex"] = f"#{hex_val .lower ()}"
                update_ui("hex")

        def from_rgb_input(e=None):
            try:
                r_val = int(r_var.get() or 0)
                g_val = int(g_var.get() or 0)
                b_val = int(b_var.get() or 0)

                if r_val > 255:
                    r_var.set("255")
                if g_val > 255:
                    g_var.set("255")
                if b_val > 255:
                    b_var.set("255")

                state["hex"] = self._rgb_to_hex(
                    min(255, r_val), min(255, g_val), min(255, b_val)
                )
                update_ui("rgb")
            except (ValueError, tk.TclError):
                pass

        def on_rgb_focus_out(e):
            (v.set("0") for v in [r_var, g_var, b_var] if not v.get())
            from_rgb_input()

        ttk.Label(inputs_frame, text="HEX:", width=5).grid(
            row=0, column=0, sticky="w", padx=(0, 5)
        )
        hex_entry = ttk.Entry(inputs_frame, textvariable=hex_var, width=12)
        hex_entry.grid(row=0, column=1, columnspan=3, sticky="we")
        hex_entry.bind("<KeyRelease>", from_hex_input)
        hex_entry.bind("<FocusOut>", from_hex_input)
        ttk.Label(inputs_frame, text="RGB:", width=5).grid(
            row=1, column=0, sticky="w", pady=(5, 0), padx=(0, 5)
        )
        vcmd = (self.root.register(lambda v: v == "" or v.isdigit()), "%P")
        r_e = ttk.Entry(
            inputs_frame,
            textvariable=r_var,
            width=4,
            validate="key",
            validatecommand=vcmd,
        )
        r_e.grid(row=1, column=1, pady=(5, 0), sticky="w")
        g_e = ttk.Entry(
            inputs_frame,
            textvariable=g_var,
            width=4,
            validate="key",
            validatecommand=vcmd,
        )
        g_e.grid(row=1, column=2, pady=(5, 0), sticky="w")
        b_e = ttk.Entry(
            inputs_frame,
            textvariable=b_var,
            width=4,
            validate="key",
            validatecommand=vcmd,
        )
        b_e.grid(row=1, column=3, pady=(5, 0), sticky="w")
        for e in [r_e, g_e, b_e]:
            e.bind("<KeyRelease>", from_rgb_input)
            e.bind("<FocusOut>", on_rgb_focus_out)

        button_frame = ttk.Frame(dialog)
        button_frame.pack(pady=(10, 15), side=tk.BOTTOM)

        def apply_choice():
            if self.canvas_bg_color != state["hex"]:
                self.canvas_bg_color = state["hex"]
                self._force_full_redraw = True
                self._update_canvas_workarea_color()
                if self.show_canvas_background_var.get():
                    self._update_visible_canvas_image()
            dialog.destroy()

        ttk.Button(
            button_frame, text="OK", command=apply_choice, style="Accent.TButton"
        ).pack(side=tk.LEFT, padx=5)
        ttk.Button(button_frame, text="Cancel", command=dialog.destroy).pack(
            side=tk.LEFT, padx=5
        )
        state["hex"] = self.canvas_bg_color
        update_ui()
        dialog.bind("<Return>", lambda e: apply_choice())
        dialog.bind("<Escape>", lambda e: dialog.destroy())

    def toggle_grid_visibility(self):
        self._rescale_canvas()

    def toggle_canvas_background_display(self):
        self._update_canvas_workarea_color()
        self._force_full_redraw = True
        self._rescale_canvas()
        self._update_save_background_menu_state()

    def toggle_pixel_alpha_rendering(self):
        self._force_full_redraw = True
        self._rescale_canvas()

    def new_canvas(self):
        if not self.pixel_data or messagebox.askokcancel(
            "New", "Clear canvas? Unsaved changes may be lost."
        ):
            self.pixel_data.clear()
            self.current_filename = None
            self.canvas_bg_color = "#FFFFFF"
            self.root.title("Pixel Art Drawing App")
            self._update_canvas_workarea_color()
            self._clear_history()
            self._force_full_redraw = True
            self.create_canvas()

    def open_file(self):
        if self.pixel_data and not messagebox.askokcancel(
            "Open", "Clear canvas? Unsaved changes may be lost."
        ):
            return
        filename = filedialog.askopenfilename(
            title="Open PNG", filetypes=[("PNG", "*.png"), ("All", "*.*")]
        )
        if not filename:
            return

        self._load_image_from_path(filename)

    def _load_image_from_path(self, filename):

        try:
            with Image.open(filename) as img:
                img = img.convert("RGBA")
                old_w, old_h = self.canvas_width, self.canvas_height
                self.canvas_width, self.canvas_height = img.width, img.height
                self.pixel_data.clear()
                for y in range(img.height):
                    for x in range(img.width):
                        r, g, b, a = img.getpixel((x, y))
                        if a > 0:
                            self.pixel_data[(x, y)] = (self._rgb_to_hex(r, g, b), a)

                self._clear_history()
                self._force_full_redraw = True
                self.create_canvas()

                self.current_filename = filename
                self.root.title(
                    f"Pixel Art Drawing App - {os .path .basename (filename )}"
                )
                if (old_w, old_h) != (self.canvas_width, self.canvas_height):
                    messagebox.showinfo(
                        "Canvas Resized",
                        f"Canvas resized to {self .canvas_width }x{self .canvas_height } to fit image.",
                        parent=self.root,
                    )
        except Exception as e:
            messagebox.showerror("Error", f"Failed to open: {e }")

    def save_file(self):
        if self.current_filename:
            self.export_to_png(self.current_filename)
        else:
            self.export_png()

    def export_png(self):
        filename = filedialog.asksaveasfilename(
            title="Export PNG As", defaultextension=".png", filetypes=[("PNG", "*.png")]
        )
        if filename:
            self.export_to_png(filename)

    def export_to_png(self, filename):
        try:
            if self.show_canvas_background_var.get() and self.save_background_var.get():
                bg_color_tuple = self._hex_to_rgb(self.canvas_bg_color) + (255,)
                img = Image.new(
                    "RGBA", (self.canvas_width, self.canvas_height), bg_color_tuple
                )

                pixel_layer = Image.new(
                    "RGBA", (self.canvas_width, self.canvas_height), (0, 0, 0, 0)
                )
                for (x, y), (h, a) in self.pixel_data.items():
                    if h != "transparent" and a > 0:
                        pixel_layer.putpixel((x, y), self._hex_to_rgb(h) + (a,))

                img = Image.alpha_composite(img, pixel_layer)
            else:
                img = Image.new(
                    "RGBA", (self.canvas_width, self.canvas_height), (255, 255, 255, 0)
                )
                for (x, y), (h, a) in self.pixel_data.items():
                    if h != "transparent" and a > 0:
                        img.putpixel((x, y), self._hex_to_rgb(h) + (a,))
            img.save(filename, "PNG")
            if filename == self.current_filename or self.current_filename is None:
                self.current_filename = filename
                self.root.title(
                    f"Pixel Art Drawing App - {os .path .basename (filename )}"
                )
            messagebox.showinfo(
                "Saved", f"Image saved to {filename }", parent=self.root
            )
        except Exception as e:
            messagebox.showerror("Error", f"Failed to save: {e }")


def main():

    root = TkinterDnD.Tk()

    PixelArtApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
