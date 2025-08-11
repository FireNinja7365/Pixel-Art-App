import tkinter as tk
from tkinter import ttk, filedialog, messagebox, colorchooser, simpledialog
from PIL import Image, ImageTk, ImageDraw
from pathlib import Path
import os
import math
import colorsys
import re

class ColorWheelPicker(ttk.Frame):
    def __init__(self, parent, color_change_callback):
        super().__init__(parent)
        self.pack(pady=5)
        self.color_change_callback = color_change_callback

        self.hue = 0.0
        self.saturation = 1.0
        self.value = 1.0
        self.indicator_radius = 5
        self.sv_indicator_radius = 8
        self.drag_mode = None

        canvas_size = 150
        self.sv_box_size = 72
        self.sv_box_offset = (canvas_size - self.sv_box_size) / 2

        self.color_canvas = tk.Canvas(self, width=canvas_size, height=canvas_size, highlightthickness=0)
        self.color_canvas.pack()

        self.create_hue_wheel()

        hue_angle = 0.0
        wheel_radius = 63.75
        canvas_center = 75
        hue_indicator_x = canvas_center + wheel_radius * math.cos(hue_angle)
        hue_indicator_y = canvas_center + wheel_radius * math.sin(hue_angle)
        self.hue_indicator = self.color_canvas.create_oval(
            hue_indicator_x - self.indicator_radius, hue_indicator_y - self.indicator_radius,
            hue_indicator_x + self.indicator_radius, hue_indicator_y + self.indicator_radius,
            fill='white', outline='black', width=2, tags=("hue_indicator",)
        )

        sv_x = self.sv_box_offset + self.saturation * (self.sv_box_size - 1)
        sv_y = self.sv_box_offset + (1.0 - self.value) * (self.sv_box_size - 1)
        r = self.sv_indicator_radius
        self.sv_indicator = self.color_canvas.create_oval(
            sv_x - r, sv_y - r, sv_x + r, sv_y + r,
            fill='white', outline='black', width=2, tags=("sv_indicator",)
        )

        self.update_sv_box()
        self.update_color_display()

        self.color_canvas.tag_bind("hue_area", "<Button-1>", self.start_hue_drag)
        self.color_canvas.tag_bind("hue_indicator", "<Button-1>", self.start_hue_drag)
        self.color_canvas.tag_bind("sv_area", "<Button-1>", self.start_sv_drag)
        self.color_canvas.tag_bind("sv_indicator", "<Button-1>", self.start_sv_drag)
        self.color_canvas.bind('<B1-Motion>', self.on_canvas_drag)
        self.color_canvas.bind('<ButtonRelease-1>', self.stop_drag)

    def _hex_to_rgb(self, hex_color_str):
        h = hex_color_str.lstrip('#')
        if len(h) != 6: return (0, 0, 0)
        try: return tuple(int(h[i:i+2], 16) for i in (0, 2, 4))
        except ValueError: return (0, 0, 0)

    def set_color(self, hex_color):
        if not hex_color or not hex_color.startswith('#'): return

        r, g, b = self._hex_to_rgb(hex_color)
        h, s, v = colorsys.rgb_to_hsv(r / 255.0, g / 255.0, b / 255.0)

        self.hue, self.saturation, self.value = h, s, v

        self.update_sv_box()

        angle = self.hue * 2 * math.pi
        radius = 63.75
        center_x, center_y = 75, 75
        indicator_x = center_x + radius * math.cos(angle)
        indicator_y = center_y - radius * math.sin(-angle)
        r_hue = self.indicator_radius
        self.color_canvas.coords(self.hue_indicator, indicator_x - r_hue, indicator_y - r_hue, indicator_x + r_hue, indicator_y + r_hue)

        sv_x = self.sv_box_offset + self.saturation * (self.sv_box_size - 1)
        sv_y = self.sv_box_offset + (1.0 - self.value) * (self.sv_box_size - 1)
        r_sv = self.sv_indicator_radius
        self.color_canvas.coords(self.sv_indicator, sv_x - r_sv, sv_y - r_sv, sv_x + r_sv, sv_y + r_sv)

        self.update_color_display(run_callback=False)

    def create_hue_wheel(self):
        size = 150
        radius = size // 2
        center_x, center_y = radius, radius
        image = Image.new("RGBA", (size, size), (0, 0, 0, 0))
        pixels = image.load()

        for y in range(size):
            for x in range(size):
                dx, dy = x - center_x, y - center_y
                distance = math.sqrt(dx**2 + dy**2)
                if radius * 0.7 < distance < radius:
                    angle = math.atan2(-dy, dx)
                    hue = (angle / (2 * math.pi)) % 1.0
                    rgb_float = colorsys.hsv_to_rgb(hue, 1.0, 1.0)
                    rgb_int = tuple(int(c * 255) for c in rgb_float)
                    pixels[x, y] = rgb_int + (255,)

        self.hue_wheel_image = ImageTk.PhotoImage(image)
        self.color_canvas.create_image(center_x, center_y, image=self.hue_wheel_image, tags="hue_area")

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
            self.sv_box_offset, self.sv_box_offset,
            anchor=tk.NW, image=self.sv_image, tags=("sv_area", "gradient")
        )
        self.color_canvas.tag_raise("hue_indicator")
        self.color_canvas.tag_raise("sv_indicator")

    def start_hue_drag(self, event): self.drag_mode = 'hue'; self.update_hue(event.x, event.y)
    def start_sv_drag(self, event): self.drag_mode = 'sv'; self.update_sv(event.x, event.y)
    def stop_drag(self, event): self.drag_mode = None

    def on_canvas_drag(self, event):
        if self.drag_mode == 'hue': self.update_hue(event.x, event.y)
        elif self.drag_mode == 'sv': self.update_sv(event.x, event.y)

    def update_hue(self, x, y):
        center_x, center_y = 75, 75
        dx, dy = x - center_x, y - center_y
        if dx == 0 and dy == 0: return
        angle = math.atan2(-dy, dx)
        self.hue = (angle / (2 * math.pi)) % 1.0
        self.update_sv_box()
        self.update_color_display()
        radius = 63.75
        indicator_x = center_x + radius * math.cos(angle)
        indicator_y = center_y - radius * math.sin(angle)
        r = self.indicator_radius
        self.color_canvas.coords(self.hue_indicator, indicator_x - r, indicator_y - r, indicator_x + r, indicator_y + r)

    def update_sv(self, x, y):
        x = max(self.sv_box_offset, min(x, self.sv_box_offset + self.sv_box_size - 1))
        y = max(self.sv_box_offset, min(y, self.sv_box_offset + self.sv_box_size - 1))
        self.saturation = max(0.0, min(1.0, (x - self.sv_box_offset) / (self.sv_box_size - 1)))
        self.value = max(0.0, min(1.0, 1.0 - (y - self.sv_box_offset) / (self.sv_box_size - 1)))
        self.update_color_display()
        r = self.sv_indicator_radius
        self.color_canvas.coords(self.sv_indicator, x - r, y - r, x + r, y + r)

    def update_color_display(self, run_callback=True):
        rgb_float = colorsys.hsv_to_rgb(self.hue, self.saturation, self.value)
        rgb_int = tuple(int(c * 255) for c in rgb_float)
        hex_color = f'#{rgb_int[0]:02x}{rgb_int[1]:02x}{rgb_int[2]:02x}'
        if run_callback:
            self.color_change_callback(hex_color)

class PixelArtApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Pixel Art Drawing App")
        self.root.geometry("1000x700")

        script_dir = os.path.dirname(__file__)
        self.icon_path = Path(__file__).parent / "assets" / "app.ico"

        try:
            if self.icon_path.exists(): self.root.iconbitmap(str(self.icon_path))
        except Exception as e: print(f"Warning: Could not set application icon: {e}")

        self.canvas_width = 32
        self.canvas_height = 32
        self.canvas_bg_color = "#FFFFFF"

        self.pixel_size = 15
        self.min_pixel_size = 5
        self.max_pixel_size = 60
        self.zoom_factor = 1.2

        self.grid_color = "#cccccc"

        self.current_color = "#ff0000"
        self.current_alpha = 255
        self.drawing = False
        self.current_tool = "pencil"
        self.eyedropper_mode = False

        self._updating_color_inputs = False


        self.mmb_eyedropper_active = False
        self.original_cursor_before_mmb = ""
        self.original_cursor_before_pan = ""

        self.current_filename = None

        self.pixel_data = {}

        self.art_sprite_image = None
        self.art_sprite_canvas_item = None
        self._after_id_render = None
        self._after_id_resize = None

        self.last_draw_pixel_x = None
        self.last_draw_pixel_y = None
        self.stroke_pixels_drawn_this_stroke = set()

        self.show_canvas_background_var = tk.BooleanVar(value=False)
        self.render_pixel_alpha_var = tk.BooleanVar(value=True)
        self.color_blending_var = tk.BooleanVar(value=False)
        self.show_grid_var = tk.BooleanVar(value=False)

        self.start_shape_point = None
        self.preview_shape_item = None

        self.color_preview_image_tk = None

        self.setup_menu()
        self.setup_ui()
        self.create_canvas()
        self._update_shape_controls_state()
        self.update_inputs_from_current_color()

    def _hex_to_rgb(self, hex_color_str):
        h = hex_color_str.lstrip('#')
        if len(h) != 6: return (0, 0, 0)
        try: return tuple(int(h[i:i+2], 16) for i in (0, 2, 4))
        except ValueError: return (0, 0, 0)

    def _rgb_to_hex(self, r, g, b):
        return f"#{int(r):02x}{int(g):02x}{int(b):02x}"

    def setup_menu(self):
        menubar = tk.Menu(self.root)
        self.root.config(menu=menubar)
        file_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="File", menu=file_menu)
        file_menu.add_command(label="New", command=self.new_canvas, accelerator="Ctrl+N")
        file_menu.add_separator()
        file_menu.add_command(label="Open PNG...", command=self.open_file, accelerator="Ctrl+O")
        file_menu.add_separator()
        file_menu.add_command(label="Save PNG", command=self.save_file, accelerator="Ctrl+S")
        file_menu.add_command(label="Export PNG As...", command=self.export_png, accelerator="Ctrl+Shift+S")
        file_menu.add_separator()
        file_menu.add_command(label="Exit", command=self.root.quit, accelerator="Ctrl+Q")

        canvas_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="Canvas", menu=canvas_menu)
        canvas_menu.add_command(label="Resize Canvas...", command=self.show_resize_dialog)
        canvas_menu.add_command(label="Set Background Color...", command=self.choose_canvas_background_color)
        canvas_menu.add_separator()
        canvas_menu.add_checkbutton(label="Show Background", variable=self.show_canvas_background_var, command=self.toggle_canvas_background_display)
        canvas_menu.add_checkbutton(label="Show Grid", variable=self.show_grid_var, command=self.toggle_grid_visibility)
        canvas_menu.add_checkbutton(label="Color Blending", variable=self.color_blending_var)
        canvas_menu.add_checkbutton(label="Render Pixel Alpha", variable=self.render_pixel_alpha_var, command=self.toggle_pixel_alpha_rendering)

        self.root.bind('<Control-n>', lambda e: self.new_canvas())
        self.root.bind('<Control-o>', lambda e: self.open_file())
        self.root.bind('<Control-s>', lambda e: self.save_file())
        self.root.bind('<Control-Shift-S>', lambda e: self.export_png())
        self.root.bind('<Control-q>', lambda e: self.root.quit())

    def show_resize_dialog(self):
        dialog = tk.Toplevel(self.root); dialog.title("Resize Canvas"); dialog.geometry("250x150"); dialog.resizable(False, False); dialog.transient(self.root); dialog.grab_set(); dialog.geometry("+%d+%d" % (self.root.winfo_rootx() + 50, self.root.winfo_rooty() + 50))
        main_frame = ttk.Frame(dialog, padding=20); main_frame.pack(fill=tk.BOTH, expand=True)
        ttk.Label(main_frame, text="Width:").grid(row=0, column=0, sticky=tk.W, padx=(0, 10)); width_var = tk.StringVar(value=str(self.canvas_width)); width_entry = ttk.Entry(main_frame, textvariable=width_var, width=10); width_entry.grid(row=0, column=1, pady=(0, 10))
        ttk.Label(main_frame, text="Height:").grid(row=1, column=0, sticky=tk.W, padx=(0, 10)); height_var = tk.StringVar(value=str(self.canvas_height)); height_entry = ttk.Entry(main_frame, textvariable=height_var, width=10); height_entry.grid(row=1, column=1, pady=(0, 20))
        button_frame = ttk.Frame(main_frame); button_frame.grid(row=2, column=0, columnspan=2)
        def apply_resize():
            try:
                new_width = int(width_var.get()); new_height = int(height_var.get())
                if 1 <= new_width <= 200 and 1 <= new_height <= 200:
                    if self.canvas_width != new_width or self.canvas_height != new_height:
                        self.canvas_width = new_width
                        self.canvas_height = new_height
                        self.create_canvas()
                    dialog.destroy()
                else: messagebox.showerror("Error", "Canvas size must be between 1 and 200 pixels", parent=dialog)
            except ValueError: messagebox.showerror("Error", "Please enter valid numbers for canvas size", parent=dialog)
        ttk.Button(button_frame, text="Apply", command=apply_resize).pack(side=tk.LEFT, padx=(0, 10)); ttk.Button(button_frame, text="Cancel", command=dialog.destroy).pack(side=tk.LEFT)
        width_entry.focus(); width_entry.select_range(0, tk.END); dialog.bind('<Return>', lambda e: apply_resize()); dialog.bind('<Escape>', lambda e: dialog.destroy())

    def create_transparent_color_preview(self, parent_frame, width=60, height=40):
        preview_canvas = tk.Canvas(parent_frame, width=width, height=height, relief=tk.SUNKEN, bd=2, highlightthickness=0);
        return preview_canvas

    def update_color_preview(self):
        if not hasattr(self, 'color_preview_canvas'): return
        width = self.color_preview_canvas.winfo_width(); height = self.color_preview_canvas.winfo_height()
        if width <= 1 or height <= 1: self.root.after(50, self.update_color_preview); return
        checker_size = 6; bg_img = Image.new("RGBA", (width, height)); draw_bg = ImageDraw.Draw(bg_img)
        for x_bg in range(0, width, checker_size):
            for y_bg in range(0, height, checker_size):
                fill_c = (224,224,224,255) if (x_bg//checker_size + y_bg//checker_size)%2 else (245,245,245,255)
                draw_bg.rectangle([x_bg, y_bg, x_bg+checker_size, y_bg+checker_size], fill=fill_c)
        try: r_val,g_val,b_val = self._hex_to_rgb(self.current_color); a_val = self.current_alpha
        except ValueError: r_val,g_val,b_val,a_val = 0,0,0,255

        overlay_img = Image.new("RGBA", (width, height), (r_val, g_val, b_val, a_val)); final_img = Image.alpha_composite(bg_img, overlay_img)
        self.color_preview_image_tk = ImageTk.PhotoImage(final_img); self.color_preview_canvas.delete("all"); self.color_preview_canvas.create_image(0,0, image=self.color_preview_image_tk, anchor="nw")

    def on_window_resize(self, event):
        if event.widget == self.root:
            if self._after_id_resize: self.root.after_cancel(self._after_id_resize)
            self._after_id_resize = self.root.after(50, self._update_visible_canvas_image)

    def setup_ui(self):
        main_frame = ttk.Frame(self.root); main_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        left_panel = ttk.Frame(main_frame, width=250); left_panel.pack(side=tk.LEFT, fill=tk.Y, padx=(0,10)); left_panel.pack_propagate(False)

        tools_frame = ttk.LabelFrame(left_panel, text="Tools", padding=10); tools_frame.pack(fill=tk.X, pady=(0,10))
        self.tool_var = tk.StringVar(value="pencil")

        ttk.Radiobutton(tools_frame, text="Pencil", variable=self.tool_var, value="pencil", command=self.change_tool).pack(anchor=tk.W)
        ttk.Radiobutton(tools_frame, text="Eraser", variable=self.tool_var, value="eraser", command=self.change_tool).pack(anchor=tk.W)
        ttk.Radiobutton(tools_frame, text="Fill", variable=self.tool_var, value="fill", command=self.change_tool).pack(anchor=tk.W)

        shape_line_frame = ttk.Frame(tools_frame)
        shape_line_frame.pack(fill=tk.X, anchor=tk.W, pady=(2, 0))
        ttk.Radiobutton(shape_line_frame, text="Shape", variable=self.tool_var, value="shape", command=self.change_tool).pack(side=tk.LEFT, anchor=tk.W)
        
        self.shape_type_var = tk.StringVar(value="Line")
        shape_types = ["Line", "Rectangle", "Ellipse"]
        self.shape_combobox = ttk.Combobox(shape_line_frame, textvariable=self.shape_type_var, values=shape_types, state="readonly", width=12)
        self.shape_combobox.pack(side=tk.LEFT, padx=(5,0), anchor=tk.W)
        self.shape_combobox.bind("<<ComboboxSelected>>", self.on_shape_type_change)

        self.lock_aspect_var = tk.BooleanVar(value=False)
        lock_aspect_frame = ttk.Frame(tools_frame)
        lock_aspect_frame.pack(fill=tk.X, anchor=tk.W)
        self.lock_aspect_checkbox = ttk.Checkbutton(lock_aspect_frame, text="Lock Aspect", variable=self.lock_aspect_var)
        self.lock_aspect_checkbox.pack(pady=(2,0), padx=(20,0), anchor=tk.W)


        color_frame = ttk.LabelFrame(left_panel, text="Color Picker", padding=10); color_frame.pack(fill=tk.X, pady=(0,10))

        preview_container = ttk.Frame(color_frame)
        preview_container.pack(pady=(0, 10))
        self.color_preview_canvas = self.create_transparent_color_preview(preview_container, width=120, height=40)
        self.color_preview_canvas.pack()

        self.color_wheel = ColorWheelPicker(color_frame, self._on_color_wheel_change)

        color_inputs_frame = ttk.Frame(color_frame); color_inputs_frame.pack(pady=(10,0))
        self.hex_var = tk.StringVar(); self.r_var = tk.StringVar(); self.g_var = tk.StringVar(); self.b_var = tk.StringVar()

        ttk.Label(color_inputs_frame, text="HEX:", width=5).grid(row=0, column=0, padx=(0,5), sticky='w')
        hex_entry = ttk.Entry(color_inputs_frame, textvariable=self.hex_var, width=10); hex_entry.grid(row=0, column=1, columnspan=3, sticky='we')
        hex_entry.bind("<KeyRelease>", self.on_hex_input); hex_entry.bind("<FocusOut>", self.on_hex_input)

        ttk.Label(color_inputs_frame, text="RGB:", width=5).grid(row=1, column=0, padx=(0,5), pady=(5,0), sticky='w')
        rgb_vcmd = (self.root.register(self.validate_rgb_input), '%P')
        r_entry = ttk.Entry(color_inputs_frame, textvariable=self.r_var, width=4, validate='key', validatecommand=rgb_vcmd); r_entry.grid(row=1, column=1, pady=(5,0), sticky='w')
        g_entry = ttk.Entry(color_inputs_frame, textvariable=self.g_var, width=4, validate='key', validatecommand=rgb_vcmd); g_entry.grid(row=1, column=2, pady=(5,0), sticky='w')
        b_entry = ttk.Entry(color_inputs_frame, textvariable=self.b_var, width=4, validate='key', validatecommand=rgb_vcmd); b_entry.grid(row=1, column=3, pady=(5,0), sticky='w')

        r_entry.bind("<KeyRelease>", self.on_rgb_input); g_entry.bind("<KeyRelease>", self.on_rgb_input); b_entry.bind("<KeyRelease>", self.on_rgb_input)
        r_entry.bind("<FocusOut>", self.on_rgb_input_focus_out); g_entry.bind("<FocusOut>", self.on_rgb_input_focus_out); b_entry.bind("<FocusOut>", self.on_rgb_input_focus_out)


        alpha_frame = ttk.Frame(color_frame); alpha_frame.pack(fill=tk.X, pady=(10,0))
        self.alpha_var = tk.StringVar(value="255"); vcmd = (self.root.register(lambda v: v == "" or v.isdigit()), '%P')

        ttk.Label(alpha_frame, text="A:", width=2).pack(side=tk.LEFT, padx=(0,5))
        alpha_entry = ttk.Entry(alpha_frame, textvariable=self.alpha_var, width=6, validate='key', validatecommand=vcmd); alpha_entry.pack(side=tk.LEFT, padx=(0,10))
        alpha_entry.bind('<KeyRelease>', self.on_alpha_entry_change); alpha_entry.bind('<FocusOut>', self.on_alpha_entry_focus_out)

        self.alpha_slider = tk.Scale(alpha_frame, from_=0, to=255, orient=tk.HORIZONTAL, showvalue=0, length=120, resolution=1, command=self.on_alpha_slider_change, bg='#A0A0A0', troughcolor='#E0E0E0', activebackground='#606060', sliderrelief=tk.RAISED, width=15, sliderlength=20, highlightthickness=0, bd=0)
        self.alpha_slider.pack(side=tk.LEFT, fill=tk.X, expand=True); self.alpha_slider.set(self.current_alpha)

        ttk.Button(color_frame, text="Pick Color (Eyedropper)", command=self.toggle_eyedropper).pack(pady=10)

        canvas_frame = ttk.Frame(main_frame); canvas_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        v_scroll = ttk.Scrollbar(canvas_frame, orient=tk.VERTICAL); h_scroll = ttk.Scrollbar(canvas_frame, orient=tk.HORIZONTAL)
        self.canvas = tk.Canvas(canvas_frame, bg="white", yscrollcommand=v_scroll.set, xscrollcommand=h_scroll.set, highlightthickness=0)
        v_scroll.config(command=self.on_scroll_y); h_scroll.config(command=self.on_scroll_x)
        v_scroll.pack(side=tk.RIGHT, fill=tk.Y); h_scroll.pack(side=tk.BOTTOM, fill=tk.X); self.canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        self.canvas.bind("<Button-1>", self.start_draw); self.canvas.bind("<B1-Motion>", self.draw); self.canvas.bind("<ButtonRelease-1>", self.stop_draw)
        self.canvas.bind("<Button-2>", self.start_mmb_eyedropper); self.canvas.bind("<B2-Motion>", self.mmb_eyedropper_motion); self.canvas.bind("<ButtonRelease-2>", self.stop_mmb_eyedropper)
        self.canvas.bind("<Button-3>", self.start_pan); self.canvas.bind("<B3-Motion>", self.pan_motion); self.canvas.bind("<ButtonRelease-3>", self.stop_pan)
        self.canvas.bind("<MouseWheel>", self.on_canvas_scroll); self.canvas.bind("<Button-4>", self.on_canvas_scroll); self.canvas.bind("<Button-5>", self.on_canvas_scroll)
        self.root.bind('<Configure>', self.on_window_resize)

    def _on_color_wheel_change(self, new_hex_color):
        self.current_color = new_hex_color
        self.update_inputs_from_current_color()
        self.update_color_preview()

    def on_hex_input(self, event):
        if self._updating_color_inputs: return
        hex_val = self.hex_var.get().lstrip('#')
        if len(hex_val) > 6: hex_val = hex_val[:6]; self.hex_var.set(hex_val)
        if re.fullmatch(r'[0-9a-fA-F]{6}', hex_val):
            new_color = f"#{hex_val.lower()}"
            if self.current_color != new_color:
                self.current_color = new_color
                self.update_inputs_from_current_color(source='hex')

    def on_rgb_input(self, event=None):
        if self._updating_color_inputs: return
        try:
            r = int(self.r_var.get() or 0)
            g = int(self.g_var.get() or 0)
            b = int(self.b_var.get() or 0)
            new_color = self._rgb_to_hex(r, g, b)
            if self.current_color != new_color:
                self.current_color = new_color
                self.update_inputs_from_current_color(source='rgb')
        except (ValueError, tk.TclError): pass

    def validate_rgb_input(self, proposed_value):
        if proposed_value == "" or (proposed_value.isdigit() and 0 <= int(proposed_value) <= 255):
            return True
        return False

    def on_rgb_input_focus_out(self, event):
        if self._updating_color_inputs: return
        try:
            for var in [self.r_var, self.g_var, self.b_var]:
                if not var.get(): var.set("0")
        except tk.TclError: pass
        self.on_rgb_input()

    def on_alpha_entry_change(self, event):
        try:
            value_str = self.alpha_var.get();
            if not value_str: return
            num = int(value_str)
            if num > 255: self.alpha_var.set("255"); event.widget.icursor(tk.END)
            elif num < 0: self.alpha_var.set("0"); event.widget.icursor(tk.END)
            self.current_alpha = int(self.alpha_var.get())
            if self.alpha_slider.get() != self.current_alpha: self.alpha_slider.set(self.current_alpha)
            self.update_color_preview()
        except ValueError: pass

    def on_alpha_entry_focus_out(self, event):
        try:
            value_str = self.alpha_var.get()
            if not value_str: self.alpha_var.set("255")
            else: self.alpha_var.set(str(max(0, min(255, int(value_str)))))
            self.current_alpha = int(self.alpha_var.get())
            self.alpha_slider.set(self.current_alpha)
            self.update_color_preview()
        except (ValueError, tk.TclError):
            self.alpha_var.set("255"); self.alpha_slider.set(255); self.current_alpha = 255
            self.update_color_preview()

    def on_alpha_slider_change(self, value):
        val_int_str = str(int(float(value)))
        self.current_alpha = int(val_int_str)
        if self.alpha_var.get() != val_int_str: self.alpha_var.set(val_int_str)
        self.update_color_preview()

    def on_scroll_y(self, *args): self.canvas.yview(*args); self._update_visible_canvas_image()
    def on_scroll_x(self, *args): self.canvas.xview(*args); self._update_visible_canvas_image()

    def on_canvas_scroll(self, event):
        old_pixel_size = self.pixel_size
        current_canvas_x = self.canvas.canvasx(event.x); current_canvas_y = self.canvas.canvasy(event.y)
        zoom_in = (event.delta > 0 or event.num == 4)
        if zoom_in: new_pixel_size = self.pixel_size * self.zoom_factor
        else: new_pixel_size = self.pixel_size / self.zoom_factor
        new_pixel_size = max(self.min_pixel_size, min(self.max_pixel_size, round(new_pixel_size)))
        if new_pixel_size == old_pixel_size: return
        self.pixel_size = new_pixel_size
        self._update_canvas_scaling()
        pixel_x_at_cursor = current_canvas_x / old_pixel_size; pixel_y_at_cursor = current_canvas_y / old_pixel_size
        new_canvas_x_for_pixel = pixel_x_at_cursor * self.pixel_size; new_canvas_y_for_pixel = pixel_y_at_cursor * self.pixel_size
        new_scroll_x_abs = new_canvas_x_for_pixel - event.x; new_scroll_y_abs = new_canvas_y_for_pixel - event.y
        total_canvas_width = self.canvas_width * self.pixel_size; total_canvas_height = self.canvas_height * self.pixel_size
        x_fraction = new_scroll_x_abs / total_canvas_width if total_canvas_width > 0 else 0
        y_fraction = new_scroll_y_abs / total_canvas_height if total_canvas_height > 0 else 0
        self.canvas.xview_moveto(x_fraction); self.canvas.yview_moveto(y_fraction)
        self._update_visible_canvas_image()

    def _update_canvas_scaling(self):
        total_width = self.canvas_width * self.pixel_size; total_height = self.canvas_height * self.pixel_size
        h_lines = self.canvas.find_withtag("grid_h"); v_lines = self.canvas.find_withtag("grid_v")
        grid_state = 'normal' if self.show_grid_var.get() else 'hidden'
        for i, line_id in enumerate(h_lines):
            y = (i + 1) * self.pixel_size; self.canvas.coords(line_id, 0, y, total_width, y); self.canvas.itemconfig(line_id, state=grid_state)
        for i, line_id in enumerate(v_lines):
            x = (i + 1) * self.pixel_size; self.canvas.coords(line_id, x, 0, x, total_height); self.canvas.itemconfig(line_id, state=grid_state)
        self.canvas.configure(scrollregion=(0, 0, total_width, total_height))

    def _rescale_canvas(self): self._update_canvas_scaling(); self._update_visible_canvas_image()

    def on_shape_type_change(self, event=None):
        shape = self.shape_type_var.get(); is_shape_tool_active = self.tool_var.get() == "shape"
        checkbox_text = "Lock Aspect"; new_state_for_checkbox_widget = tk.DISABLED
        if is_shape_tool_active:
            if shape == "Rectangle": checkbox_text = "Lock Square"; new_state_for_checkbox_widget = tk.NORMAL
            elif shape == "Ellipse": checkbox_text = "Lock Circle"; new_state_for_checkbox_widget = tk.NORMAL
        self.lock_aspect_checkbox.config(text=checkbox_text, state=new_state_for_checkbox_widget)

    def _update_shape_controls_state(self):
        is_shape_tool = self.tool_var.get() == "shape"
        self.shape_combobox.config(state="readonly" if is_shape_tool else tk.DISABLED)
        self.on_shape_type_change()

    def update_inputs_from_current_color(self, source=None):
        if not self.current_color or not hasattr(self, 'color_wheel'): return

        self._updating_color_inputs = True

        if source != 'wheel': self.color_wheel.set_color(self.current_color)

        r, g, b = self._hex_to_rgb(self.current_color)
        if source != 'rgb':
            self.r_var.set(str(r)); self.g_var.set(str(g)); self.b_var.set(str(b))

        hex_str = self.current_color.lstrip('#')
        if source != 'hex':
            if self.hex_var.get() != hex_str: self.hex_var.set(hex_str)

        alpha_str = str(self.current_alpha)
        if self.alpha_var.get() != alpha_str: self.alpha_var.set(alpha_str)
        if self.alpha_slider.get() != self.current_alpha: self.alpha_slider.set(self.current_alpha)

        self.update_color_preview()

        self._updating_color_inputs = False


    def create_canvas(self):
        self.canvas.delete("all")
        self.art_sprite_image = None
        self.art_sprite_canvas_item = self.canvas.create_image(0, 0, anchor="nw", tags="art_sprite")
        for i in range(self.canvas_height - 1): self.canvas.create_line(0,0,0,0, fill=self.grid_color, tags="grid_h")
        for i in range(self.canvas_width - 1): self.canvas.create_line(0,0,0,0, fill=self.grid_color, tags="grid_v")
        self._rescale_canvas()
        self.canvas.tag_raise("grid_h", "art_sprite"); self.canvas.tag_raise("grid_v", "art_sprite")

    def _update_visible_canvas_image(self):
        if self._after_id_render: self.root.after_cancel(self._after_id_render); self._after_id_render = None
        viewport_w = self.canvas.winfo_width(); viewport_h = self.canvas.winfo_height()
        if viewport_w <= 1 or viewport_h <= 1: self._after_id_render = self.root.after(50, self._update_visible_canvas_image); return
        canvas_x_start = self.canvas.canvasx(0); canvas_y_start = self.canvas.canvasy(0)
        pixel_x_start = max(0, math.floor(canvas_x_start / self.pixel_size)); pixel_y_start = max(0, math.floor(canvas_y_start / self.pixel_size))
        pixel_x_end = min(self.canvas_width, math.ceil((canvas_x_start + viewport_w) / self.pixel_size)); pixel_y_end = min(self.canvas_height, math.ceil((canvas_y_start + viewport_h) / self.pixel_size))
        if pixel_x_start >= pixel_x_end or pixel_y_start >= pixel_y_end: self.canvas.itemconfig(self.art_sprite_canvas_item, image=""); self.art_sprite_image = None; return
        crop_w = pixel_x_end - pixel_x_start; crop_h = pixel_y_end - pixel_y_start
        final_w, final_h = crop_w * self.pixel_size, crop_h * self.pixel_size
        if final_w <= 0 or final_h <= 0: return
        art_image_cropped = Image.new("RGBA", (crop_w, crop_h), (0, 0, 0, 0))
        rgb_cache = {}
        for (px, py), (hex_color, alpha) in self.pixel_data.items():
            if pixel_x_start <= px < pixel_x_end and pixel_y_start <= py < pixel_y_end:
                if hex_color not in rgb_cache: rgb_cache[hex_color] = self._hex_to_rgb(hex_color)
                e_alpha = alpha if self.render_pixel_alpha_var.get() else 255
                art_image_cropped.putpixel((px - pixel_x_start, py - pixel_y_start), rgb_cache[hex_color] + (e_alpha,))
        if not self.show_canvas_background_var.get():
            bg_small = Image.new("RGBA", (crop_w, crop_h)); draw_bg = ImageDraw.Draw(bg_small)
            c1, c2 = (224,224,224), (240,240,240)
            for y_bg in range(crop_h):
                for x_bg in range(crop_w): draw_bg.point((x_bg, y_bg), fill=c1 if (x_bg + pixel_x_start + y_bg + pixel_y_start) % 2 == 0 else c2)
            final_small = Image.alpha_composite(bg_small, art_image_cropped)
        else:
            final_small = Image.new("RGBA", (crop_w, crop_h), self.canvas_bg_color); final_small = Image.alpha_composite(final_small, art_image_cropped)
        final_image = final_small.resize((final_w, final_h), Image.NEAREST); self.art_sprite_image = ImageTk.PhotoImage(final_image)
        self.canvas.itemconfig(self.art_sprite_canvas_item, image=self.art_sprite_image)
        img_x_pos = pixel_x_start * self.pixel_size; img_y_pos = pixel_y_start * self.pixel_size
        self.canvas.coords(self.art_sprite_canvas_item, img_x_pos, img_y_pos); self.canvas.tag_lower(self.art_sprite_canvas_item)

    def get_pixel_coords(self, event_x, event_y):
        canvas_x, canvas_y = self.canvas.canvasx(event_x), self.canvas.canvasy(event_y)
        px, py = int(canvas_x/self.pixel_size), int(canvas_y/self.pixel_size)
        return (px, py) if 0<=px<self.canvas_width and 0<=py<self.canvas_height else (None,None)

    def draw_pixel(self, x, y, source_hex_color, source_alpha):
        if x is None or y is None or not (0 <= x < self.canvas_width and 0 <= y < self.canvas_height): return
        applied_hex_color, applied_alpha = source_hex_color, source_alpha
        if self.color_blending_var.get() and 0 < source_alpha < 255:
            existing = self.pixel_data.get((x, y))
            if existing and existing[1] > 0:
                bg_hex, bg_a_int = existing
                fg_r, fg_g, fg_b = self._hex_to_rgb(source_hex_color); bg_r, bg_g, bg_b = self._hex_to_rgb(bg_hex)
                fa, ba = source_alpha / 255.0, bg_a_int / 255.0; out_a_norm = fa + ba * (1.0 - fa)
                if out_a_norm == 0: applied_alpha, applied_hex_color = 0, "transparent"
                else:
                    applied_alpha = min(255, int(round(out_a_norm * 255.0)))
                    applied_hex_color = self._rgb_to_hex( min(255, max(0, int(round((fg_r*fa + bg_r*ba*(1-fa))/out_a_norm)))), min(255, max(0, int(round((fg_g*fa + bg_g*ba*(1-fa))/out_a_norm)))), min(255, max(0, int(round((fg_b*fa + bg_b*ba*(1-fa))/out_a_norm)))))
        if applied_alpha == 0:
            if (x, y) in self.pixel_data: del self.pixel_data[(x, y)]
        else: self.pixel_data[(x, y)] = (applied_hex_color, applied_alpha)

    def _draw_line_between_pixels(self, x0, y0, x1, y1, color_hex, alpha, tool_is_eraser):
        dx, dy = abs(x1 - x0), abs(y1 - y0); sx, sy = 1 if x0 < x1 else -1, 1 if y0 < y1 else -1; err = dx - dy; curr_x, curr_y = x0, y0
        while True:
            if (curr_x, curr_y) not in self.stroke_pixels_drawn_this_stroke:
                self.draw_pixel(curr_x, curr_y, "transparent" if tool_is_eraser else color_hex, 0 if tool_is_eraser else alpha)
                self.stroke_pixels_drawn_this_stroke.add((curr_x, curr_y))
            if curr_x == x1 and curr_y == y1: break
            e2 = 2 * err;
            if e2 > -dy: err -= dy; curr_x += sx
            if e2 < dx: err += dx; curr_y += sy

    def _draw_ellipse_pixels(self, xc, yc, rx, ry, color_hex, alpha):
        pixels_to_draw = set(); rx, ry = abs(rx), abs(ry)
        if rx == 0 and ry == 0: pixels_to_draw.add((xc, yc))
        elif rx == 0:
            for y_off in range(-ry, ry + 1): pixels_to_draw.add((xc, yc + y_off))
        elif ry == 0:
            for x_off in range(-rx, rx + 1): pixels_to_draw.add((xc + x_off, yc))
        else:
            for x_off in range(-rx, rx + 1):
                if 1 - (x_off / rx)**2 >= 0: y_abs = ry * math.sqrt(1-(x_off/rx)**2); pixels_to_draw.add((xc+x_off, yc+round(y_abs))); pixels_to_draw.add((xc+x_off, yc-round(y_abs)))
            for y_off in range(-ry, ry + 1):
                if 1 - (y_off / ry)**2 >= 0: x_abs = rx * math.sqrt(1-(y_off/ry)**2); pixels_to_draw.add((xc+round(x_abs), yc+y_off)); pixels_to_draw.add((xc-round(x_abs), yc+y_off))
        for px, py_coord in pixels_to_draw: self.draw_pixel(px, py_coord, color_hex, alpha)

    def flood_fill(self, start_x, start_y, new_color_hex, new_alpha):
        if start_x is None or start_y is None: return
        target_data = self.pixel_data.get((start_x,start_y), ("transparent",0))
        if target_data == (new_color_hex, new_alpha) and not (self.color_blending_var.get() and 0 < new_alpha < 255): return
        if target_data == ("transparent", 0) and new_alpha == 0: return
        stack = [(start_x, start_y)]; processed = set()
        while stack:
            x,y = stack.pop()
            if not (0<=x<self.canvas_width and 0<=y<self.canvas_height) or (x,y) in processed: continue
            if self.pixel_data.get((x,y), ("transparent",0)) == target_data:
                processed.add((x,y)); self.draw_pixel(x,y, new_color_hex, new_alpha)
                for dx,dy in [(0,1),(0,-1),(1,0),(-1,0)]: stack.append((x+dx, y+dy))
        self._rescale_canvas()

    def _draw_preview_rect(self, x, y, is_eraser):
        if x is None or y is None: return
        x0, y0 = x * self.pixel_size, y * self.pixel_size; x1, y1 = x0 + self.pixel_size, y0 + self.pixel_size
        fill_color = "#FFFFFF" if is_eraser else self.current_color
        outline_color = "#000000" if is_eraser else ""
        self.canvas.create_rectangle(x0, y0, x1, y1, fill=fill_color, outline=outline_color, width=1, tags="preview_stroke")

    def _bresenham_line_pixels(self, x0, y0, x1, y1):
        dx, dy = abs(x1 - x0), abs(y1 - y0); sx, sy = (1 if x0 < x1 else -1), (1 if y0 < y1 else -1)
        err = dx - dy; curr_x, curr_y = x0, y0
        while True:
            yield (curr_x, curr_y)
            if curr_x == x1 and curr_y == y1: break
            e2 = 2 * err
            if e2 > -dy: err -= dy; curr_x += sx
            if e2 < dx: err += dx; curr_y += sy

    def start_draw(self, event):
        px, py = self.get_pixel_coords(event.x, event.y)
        if px is None: return
        if self.eyedropper_mode: self.pick_color_from_canvas_tool(px,py); return
        self.drawing = True; self.stroke_pixels_drawn_this_stroke.clear(); tool = self.tool_var.get()
        if tool == "shape": self.start_shape_point = (px, py)
        else:
            self.last_draw_pixel_x, self.last_draw_pixel_y = px, py
            if tool == "fill": self.flood_fill(px,py, self.current_color, self.current_alpha)
            else: self._draw_preview_rect(px, py, tool == "eraser"); self.stroke_pixels_drawn_this_stroke.add((px,py))

    def draw(self, event):
        if not self.drawing or self.eyedropper_mode: return
        curr_px, curr_py = self.get_pixel_coords(event.x, event.y); tool = self.tool_var.get()
        if tool == "shape":
            if curr_px is None or curr_py is None: return
            if self.preview_shape_item: self.canvas.delete(self.preview_shape_item); self.preview_shape_item = None
            if self.start_shape_point is None: return
            x0_pix, y0_pix = self.start_shape_point; shape_type = self.shape_type_var.get()
            is_checkbox_var_true = self.lock_aspect_var.get(); checkbox_widget_state_str = str(self.lock_aspect_checkbox.cget("state"))
            is_checkbox_widget_enabled = (checkbox_widget_state_str == "normal"); lock_aspect = is_checkbox_var_true and is_checkbox_widget_enabled
            if shape_type == "Line":
                x_start_c, y_start_c = (x0_pix+0.5)*self.pixel_size, (y0_pix+0.5)*self.pixel_size; x_curr_c, y_curr_c = (curr_px+0.5)*self.pixel_size, (curr_py+0.5)*self.pixel_size
                self.preview_shape_item = self.canvas.create_line(x_start_c, y_start_c, x_curr_c, y_curr_c, fill=self.current_color, width=1, dash=(4,2))
            elif shape_type == "Rectangle":
                eff_end_px, eff_end_py = curr_px, curr_py
                if lock_aspect: dx_abs, dy_abs = abs(curr_px - x0_pix), abs(curr_py - y0_pix); side = max(dx_abs, dy_abs); eff_end_px = x0_pix + side*(1 if curr_px >= x0_pix else -1); eff_end_py = y0_pix + side*(1 if curr_py >= y0_pix else -1)
                c_x0, c_y0 = min(x0_pix, eff_end_px)*self.pixel_size, min(y0_pix, eff_end_py)*self.pixel_size; c_x1, c_y1 = (max(x0_pix, eff_end_px)+1)*self.pixel_size, (max(y0_pix, eff_end_py)+1)*self.pixel_size
                self.preview_shape_item = self.canvas.create_rectangle(c_x0, c_y0, c_x1, c_y1, outline=self.current_color, dash=(4,2))
            elif shape_type == "Ellipse":
                cx_c, cy_c = (x0_pix+0.5)*self.pixel_size, (y0_pix+0.5)*self.pixel_size; rx_unl, ry_unl = abs((curr_px+0.5)*self.pixel_size - cx_c), abs((curr_py+0.5)*self.pixel_size - cy_c)
                final_rx_c, final_ry_c = (max(rx_unl, ry_unl), max(rx_unl, ry_unl)) if lock_aspect else (rx_unl, ry_unl)
                self.preview_shape_item = self.canvas.create_oval(cx_c-final_rx_c, cy_c+final_ry_c, cx_c+final_rx_c, cy_c-final_ry_c, outline=self.current_color, dash=(4,2))
            if self.preview_shape_item: self.canvas.tag_raise(self.preview_shape_item)
        elif tool == "fill": return
        else:
            if curr_px is None: self.last_draw_pixel_x, self.last_draw_pixel_y = None, None; return
            if curr_px == self.last_draw_pixel_x and curr_py == self.last_draw_pixel_y: return
            is_eraser = (tool == "eraser")
            if self.last_draw_pixel_x is not None and self.last_draw_pixel_y is not None:
                for p_x, p_y in self._bresenham_line_pixels(self.last_draw_pixel_x, self.last_draw_pixel_y, curr_px, curr_py):
                    if (p_x, p_y) not in self.stroke_pixels_drawn_this_stroke: self.stroke_pixels_drawn_this_stroke.add((p_x, p_y)); self._draw_preview_rect(p_x, p_y, is_eraser)
            else:
                if (curr_px, curr_py) not in self.stroke_pixels_drawn_this_stroke: self.stroke_pixels_drawn_this_stroke.add((curr_px, curr_py)); self._draw_preview_rect(curr_px, curr_py, is_eraser)
            self.last_draw_pixel_x, self.last_draw_pixel_y = curr_px, curr_py

    def stop_draw(self, event):
        if not self.drawing: return
        self.drawing = False; tool = self.tool_var.get(); self.canvas.delete("preview_stroke")
        if tool == "shape":
            if self.preview_shape_item: self.canvas.delete(self.preview_shape_item); self.preview_shape_item = None
            end_px, end_py = self.get_pixel_coords(event.x, event.y)
            if self.start_shape_point is None or end_px is None or end_py is None : self.start_shape_point = None; return
            x0_pix, y0_pix = self.start_shape_point; shape_type = self.shape_type_var.get()
            is_checkbox_var_true = self.lock_aspect_var.get(); is_checkbox_widget_enabled = (str(self.lock_aspect_checkbox.cget("state")) == "normal"); lock_aspect = is_checkbox_var_true and is_checkbox_widget_enabled
            if shape_type == "Line": self._draw_line_between_pixels(x0_pix, y0_pix, end_px, end_py, self.current_color, self.current_alpha, False)
            elif shape_type == "Rectangle":
                eff_edge_px, eff_edge_py = end_px, end_py
                if lock_aspect: dx_abs, dy_abs = abs(end_px - x0_pix), abs(end_py - y0_pix); side = max(dx_abs, dy_abs); eff_edge_px = x0_pix + side * (1 if end_px >= x0_pix else -1); eff_edge_py = y0_pix + side * (1 if end_py >= y0_pix else -1)
                rect_x_s, rect_y_s = min(x0_pix, eff_edge_px), min(y0_pix, eff_edge_py); rect_x_e, rect_y_e = max(x0_pix, eff_edge_px), max(y0_pix, eff_edge_py)
                pixels_to_draw = set()
                for x_r in range(rect_x_s, rect_x_e + 1): pixels_to_draw.add((x_r, rect_y_s)); pixels_to_draw.add((x_r, rect_y_e))
                for y_r in range(rect_y_s + 1, rect_y_e): pixels_to_draw.add((rect_x_s, y_r)); pixels_to_draw.add((rect_x_e, y_r))
                for px_r, py_r in pixels_to_draw: self.draw_pixel(px_r, py_r, self.current_color, self.current_alpha)
            elif shape_type == "Ellipse":
                rx_unl, ry_unl = abs(end_px - x0_pix), abs(end_py - y0_pix)
                final_rx, final_ry = (max(rx_unl,ry_unl), max(rx_unl,ry_unl)) if lock_aspect else (rx_unl, ry_unl)
                self._draw_ellipse_pixels(x0_pix, y0_pix, final_rx, final_ry, self.current_color, self.current_alpha)
            self._rescale_canvas(); self.start_shape_point = None
        else:
            if tool in ["pencil", "eraser"]:
                is_eraser = (tool == "eraser"); color_to_apply = "transparent" if is_eraser else self.current_color; alpha_to_apply = 0 if is_eraser else self.current_alpha
                for px, py in self.stroke_pixels_drawn_this_stroke: self.draw_pixel(px, py, color_to_apply, alpha_to_apply)
                if self.stroke_pixels_drawn_this_stroke: self._rescale_canvas()
            self.last_draw_pixel_x, self.last_draw_pixel_y = None, None

    def _core_pick_color_at_pixel(self, px, py):
        if px is None or py is None: return False
        data = self.pixel_data.get((px, py))
        if data: self.current_color, self.current_alpha = data[0], data[1]
        else: self.current_color, self.current_alpha = "#ffffff", 0
        self.update_inputs_from_current_color(); return True

    def start_mmb_eyedropper(self, event):
        px,py = self.get_pixel_coords(event.x,event.y);
        if px is None: return
        self.mmb_eyedropper_active=True; self.original_cursor_before_mmb=self.canvas.cget("cursor"); self.canvas.configure(cursor="dotbox"); self._core_pick_color_at_pixel(px,py)

    def mmb_eyedropper_motion(self, event):
        if not self.mmb_eyedropper_active: return
        self._core_pick_color_at_pixel(*self.get_pixel_coords(event.x,event.y))

    def stop_mmb_eyedropper(self, event):
        if not self.mmb_eyedropper_active: return
        self.mmb_eyedropper_active=False; self.canvas.configure(cursor=self.original_cursor_before_mmb)

    def start_pan(self, event): self.original_cursor_before_pan = self.canvas.cget("cursor"); self.canvas.config(cursor="fleur"); self.canvas.scan_mark(event.x, event.y)
    def pan_motion(self, event): self.canvas.scan_dragto(event.x, event.y, gain=1); self._update_visible_canvas_image()
    def stop_pan(self, event): self.canvas.config(cursor=self.original_cursor_before_pan)

    def change_tool(self):
        self.current_tool = self.tool_var.get()
        if self.eyedropper_mode: self.toggle_eyedropper()
        if self.current_tool != "shape" and self.preview_shape_item: self.canvas.delete(self.preview_shape_item); self.preview_shape_item=None; self.start_shape_point=None; self.drawing=False
        self._update_shape_controls_state()

    def toggle_eyedropper(self):
        self.eyedropper_mode = not self.eyedropper_mode; self.canvas.configure(cursor="dotbox" if self.eyedropper_mode else "")
        if self.eyedropper_mode and self.tool_var.get() == "fill": self.tool_var.set("pencil"); self.change_tool()

    def pick_color_from_canvas_tool(self, px,py): self._core_pick_color_at_pixel(px,py); self.toggle_eyedropper()

    def choose_canvas_background_color(self):
        dialog = tk.Toplevel(self.root)
        dialog.title("Canvas Background Color")
        dialog.transient(self.root)
        dialog.grab_set()
        dialog.resizable(False, False)

        self.root.update_idletasks()
        root_x, root_y = self.root.winfo_x(), self.root.winfo_y()
        root_w, root_h = self.root.winfo_width(), self.root.winfo_height()
        dialog_w, dialog_h = 250, 360
        x = root_x + (root_w - dialog_w) // 2
        y = root_y + (root_h - dialog_h) // 2
        dialog.geometry(f'{dialog_w}x{dialog_h}+{x}+{y}')

        main_frame = ttk.Frame(dialog, padding=15)
        main_frame.pack(fill=tk.BOTH, expand=True)

        state = {'hex': self.canvas_bg_color, 'updating': False}
        hex_var, r_var, g_var, b_var = tk.StringVar(), tk.StringVar(), tk.StringVar(), tk.StringVar()

        preview = tk.Label(main_frame, relief="sunken", height=2)
        preview.pack(pady=(0, 15), fill=tk.X)

        def update_ui(source=None):
            if state['updating']: return
            state['updating'] = True

            hex_color = state['hex']
            preview.config(bg=hex_color)

            if source != 'wheel': color_wheel.set_color(hex_color)
            if source != 'hex': hex_var.set(hex_color.lstrip('#'))

            if source != 'rgb':
                r, g, b = self._hex_to_rgb(hex_color)
                r_var.set(str(r)); g_var.set(str(g)); b_var.set(str(b))

            state['updating'] = False

        def from_wheel(new_hex):
            state['hex'] = new_hex
            update_ui('wheel')

        color_wheel = ColorWheelPicker(main_frame, from_wheel)
        color_wheel.pack()

        inputs_frame = ttk.Frame(main_frame)
        inputs_frame.pack(pady=(15, 0))

        def from_hex_input(event):
            hex_val = hex_var.get().lstrip('#')
            if len(hex_val) > 6: hex_val = hex_val[:6]; hex_var.set(hex_val)
            if re.fullmatch(r'[0-9a-fA-F]{6}', hex_val):
                new_color = f"#{hex_val.lower()}"
                if state['hex'] != new_color: state['hex'] = new_color; update_ui('hex')

        def from_rgb_input(event=None):
            try:
                r = int(r_var.get() or 0); g = int(g_var.get() or 0); b = int(b_var.get() or 0)
                new_color = self._rgb_to_hex(r, g, b)
                if state['hex'] != new_color: state['hex'] = new_color; update_ui('rgb')
            except (ValueError, tk.TclError): pass

        def on_rgb_focus_out(event):
            try:
                for var in [r_var, g_var, b_var]:
                    if not var.get(): var.set("0")
            except tk.TclError: pass
            from_rgb_input()

        ttk.Label(inputs_frame, text="HEX:", width=5).grid(row=0, column=0, padx=(0,5), sticky='w')
        hex_entry = ttk.Entry(inputs_frame, textvariable=hex_var, width=12); hex_entry.grid(row=0, column=1, columnspan=3, sticky='we')
        hex_entry.bind("<KeyRelease>", from_hex_input); hex_entry.bind("<FocusOut>", from_hex_input)

        ttk.Label(inputs_frame, text="RGB:", width=5).grid(row=1, column=0, padx=(0,5), pady=(5,0), sticky='w')
        vcmd = (self.root.register(self.validate_rgb_input), '%P')
        r_entry = ttk.Entry(inputs_frame, textvariable=r_var, width=4, validate='key', validatecommand=vcmd); r_entry.grid(row=1, column=1, pady=(5,0), sticky='w')
        g_entry = ttk.Entry(inputs_frame, textvariable=g_var, width=4, validate='key', validatecommand=vcmd); g_entry.grid(row=1, column=2, pady=(5,0), sticky='w')
        b_entry = ttk.Entry(inputs_frame, textvariable=b_var, width=4, validate='key', validatecommand=vcmd); b_entry.grid(row=1, column=3, pady=(5,0), sticky='w')

        for entry, action in [(r_entry, from_rgb_input), (g_entry, from_rgb_input), (b_entry, from_rgb_input)]:
            entry.bind("<KeyRelease>", action)
            entry.bind("<FocusOut>", on_rgb_focus_out)

        button_frame = ttk.Frame(dialog)
        button_frame.pack(pady=(10, 15), side=tk.BOTTOM)

        def apply_choice():
            self.canvas_bg_color = state['hex']
            if self.show_canvas_background_var.get(): self._update_visible_canvas_image()
            dialog.destroy()

        ttk.Button(button_frame, text="OK", command=apply_choice, style="Accent.TButton").pack(side=tk.LEFT, padx=5)
        ttk.Button(button_frame, text="Cancel", command=dialog.destroy).pack(side=tk.LEFT, padx=5)

        state['hex'] = self.canvas_bg_color

        update_ui()
        dialog.bind('<Return>', lambda e: apply_choice())
        dialog.bind('<Escape>', lambda e: dialog.destroy())

    def toggle_grid_visibility(self): self._rescale_canvas()
    def toggle_canvas_background_display(self): self._rescale_canvas()
    def toggle_pixel_alpha_rendering(self): self._rescale_canvas()

    def new_canvas(self):
        if self.pixel_data and not messagebox.askokcancel("New", "Clear canvas? Unsaved changes may be lost."): return
        self.pixel_data.clear(); self.current_filename=None; self.canvas_bg_color = "#FFFFFF"; self.root.title("Pixel Art Drawing App"); self.create_canvas()

    def open_file(self):
        if self.pixel_data and not messagebox.askokcancel("Open", "Clear canvas? Unsaved changes may be lost."): return
        filename = filedialog.askopenfilename(title="Open PNG", filetypes=[("PNG","*.png"),("All","*.*")])
        if not filename: return
        try:
            img = Image.open(filename).convert("RGBA"); old_w,old_h = self.canvas_width,self.canvas_height
            self.canvas_width,self.canvas_height = img.width,img.height; self.pixel_data.clear(); pixels = img.load()
            for y in range(img.height):
                for x in range(img.width):
                    r,g,b,a = pixels[x,y]
                    if a > 0: self.pixel_data[(x,y)] = (self._rgb_to_hex(r,g,b), a)
            self.create_canvas(); self.current_filename=filename; self.root.title(f"Pixel Art Drawing App - {os.path.basename(filename)}")
            if (old_w,old_h) != (self.canvas_width,self.canvas_height): messagebox.showinfo("Canvas Resized", f"Canvas resized to {self.canvas_width}x{self.canvas_height} to fit image.", parent=self.root)
        except Exception as e: messagebox.showerror("Error", f"Failed to open: {e}")

    def save_file(self):
        if self.current_filename: self.export_to_png(self.current_filename)
        else: self.export_png()

    def export_png(self):
        filename = filedialog.asksaveasfilename(title="Export PNG As",defaultextension=".png",filetypes=[("PNG","*.png")])
        if filename: self.export_to_png(filename)

    def export_to_png(self, filename_to_save):
        try:
            img = Image.new("RGBA", (self.canvas_width,self.canvas_height), (255,255,255,0))
            for (x,y), (h,a) in self.pixel_data.items():
                if h!="transparent" and a>0: img.putpixel((x,y), self._hex_to_rgb(h)+(a,))
            img.save(filename_to_save, "PNG")
            if filename_to_save==self.current_filename or self.current_filename is None: self.current_filename=filename_to_save; self.root.title(f"Pixel Art Drawing App - {os.path.basename(filename_to_save)}")
            messagebox.showinfo("Saved", f"Image saved to {filename_to_save}", parent=self.root)
        except Exception as e: messagebox.showerror("Error", f"Failed to save: {e}")

def main():
    root = tk.Tk()
    app = PixelArtApp(root)
    root.mainloop()

if __name__ == "__main__":
    main()