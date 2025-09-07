import tkinter as tk
from tkinter import ttk, filedialog, messagebox, colorchooser, simpledialog
from PIL import Image, ImageTk, ImageDraw
from pathlib import Path
import os
import math
import colorsys
import re
import copy
import numpy

from tkinterdnd2 import DND_FILES, TkinterDnD
from color_wheel_picker import ColorWheelPicker
from pixel_canvas import PixelCanvas
from actions import (
    PixelAction,
    AddLayerAction,
    DuplicateLayerAction,
    DeleteLayerAction,
    MoveLayerAction,
    RenameLayerAction,
    MergeLayerAction,
)
from utilities import hex_to_rgb, rgb_to_hex, handle_slider_click
import canvas_cython_helpers


class Layer:
    _counter = 1

    def __init__(self, name=None):
        if name is None:
            self.name = f"Layer {Layer ._counter }"
            Layer._counter += 1
        else:
            self.name = name
        self.pixel_data = {}
        self.visible = True


class PixelArtApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Pixel Art Drawing App")
        self.root.geometry("1260x720")
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
        self.current_tool, self.last_used_tool = "pencil", "pencil"
        self.eyedropper_mode = False
        self.current_filename = None
        self.layers, self.active_layer_index = [], -1
        self.undo_stack, self.redo_stack = [], []

        self.last_known_width = 0
        self.last_known_height = 0

        self.show_canvas_background_var, self.save_background_var = tk.BooleanVar(
            value=False
        ), tk.BooleanVar(value=False)
        self.render_pixel_alpha_var, self.color_blending_var = tk.BooleanVar(
            value=True
        ), tk.BooleanVar(value=True)
        self.show_grid_var = tk.BooleanVar(value=False)
        self.brush_size_var = tk.IntVar(value=self.brush_size)
        self.fill_shape_var = tk.BooleanVar(value=False)
        self.tool_var = tk.StringVar(value="pencil")
        self.canvas_menu, self.layer_context_menu, self.layer_area_context_menu = (
            None,
            None,
            None,
        )

        self.setup_menu()
        self.setup_ui()
        self.setup_layers_ui()
        self.setup_drag_and_drop()
        self._initialize_layers()
        self.create_canvas()
        self.root.bind("<Configure>", self.on_window_resize)
        self._update_shape_controls_state()
        self._update_brush_controls_state()
        self._update_color_picker_from_app_state()
        self._update_history_controls()
        self._update_save_background_menu_state()

    @property
    def active_layer(self):
        return (
            self.layers[self.active_layer_index]
            if self.layers and 0 <= self.active_layer_index < len(self.layers)
            else None
        )

    @property
    def active_layer_data(self):
        return self.active_layer.pixel_data if self.active_layer else {}

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
            label="Open...", command=self.open_file, accelerator="Ctrl+O"
        )
        file_menu.add_separator()
        file_menu.add_command(
            label="Save", command=self.save_file, accelerator="Ctrl+S"
        )
        file_menu.add_command(
            label="Export As...", command=self.export_png, accelerator="Ctrl+Shift+S"
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
        undo_state, redo_state = (tk.NORMAL if self.undo_stack else tk.DISABLED), (
            tk.NORMAL if self.redo_stack else tk.DISABLED
        )
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
        self.undo_stack.append(action)
        self.redo_stack.clear()
        self._update_history_controls()

    def undo(self, event=None):
        if not self.undo_stack:
            return
        action = self.undo_stack.pop()
        action.undo(self)
        self.redo_stack.append(action)
        self.pixel_canvas.force_redraw()
        self._update_layers_ui()
        self._update_history_controls()

    def redo(self, event=None):
        if not self.redo_stack:
            return
        action = self.redo_stack.pop()
        action.redo(self)
        self.undo_stack.append(action)
        self.pixel_canvas.force_redraw()
        self._update_layers_ui()
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
                        for layer in self.layers:
                            layer.pixel_data = {
                                (x, y): data
                                for (x, y), data in layer.pixel_data.items()
                                if 0 <= x < new_width and 0 <= y < new_height
                            }
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

    def on_window_resize(self, event):

        if event.widget == self.root and hasattr(self, "pixel_canvas"):
            if (
                self.last_known_width != event.width
                or self.last_known_height != event.height
            ):
                self.last_known_width = event.width
                self.last_known_height = event.height
                self.pixel_canvas.schedule_rescale()

    def _update_canvas_workarea_color(self):
        if not hasattr(self, "pixel_canvas"):
            return
        canvas = self.pixel_canvas.canvas
        if not self.show_canvas_background_var.get():
            canvas.config(bg="#C0C0C0")
            return
        r, g, b = hex_to_rgb(self.canvas_bg_color)
        gs = int(r * 0.299 + g * 0.587 + b * 0.114)
        new_gs = max(0, min(255, gs - 32 if gs >= 128 else gs + 32))
        canvas.config(bg=rgb_to_hex(new_gs, new_gs, new_gs))

    def setup_ui(self):
        main_frame = ttk.Frame(self.root)
        main_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        left_panel = ttk.Frame(main_frame, width=250)
        left_panel.pack(side=tk.LEFT, fill=tk.Y, padx=(0, 10))
        left_panel.pack_propagate(False)
        self.right_panel = ttk.Frame(main_frame, width=220)
        self.right_panel.pack(side=tk.RIGHT, fill=tk.Y, padx=(10, 0))
        self.right_panel.pack_propagate(False)
        tools_frame = ttk.LabelFrame(left_panel, text="Tools", padding=10)
        tools_frame.pack(fill=tk.X, pady=(0, 10))
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
        shape_options_frame = ttk.Frame(tools_frame)
        shape_options_frame.pack(fill=tk.X, anchor=tk.W, padx=(20, 0))
        self.fill_shape_checkbox = ttk.Checkbutton(
            shape_options_frame, text="Fill Shape", variable=self.fill_shape_var
        )
        self.fill_shape_checkbox.pack(side=tk.LEFT, pady=(2, 0))
        self.lock_aspect_var = tk.BooleanVar(value=False)
        self.lock_aspect_checkbox = ttk.Checkbutton(
            shape_options_frame, text="Lock Aspect", variable=self.lock_aspect_var
        )
        self.lock_aspect_checkbox.pack(side=tk.LEFT, pady=(2, 0), padx=(10, 0))
        self.brush_size_frame = ttk.LabelFrame(
            tools_frame, text="Brush Size", padding=5
        )
        self.brush_size_frame.pack(fill=tk.X, pady=(10, 0), anchor=tk.W)
        bs_inner_frame = ttk.Frame(self.brush_size_frame)
        bs_inner_frame.pack(fill=tk.X)
        self.brush_size_slider = tk.Scale(
            bs_inner_frame,
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
            "<Button-1>",
            lambda e: handle_slider_click(e, self.brush_size_slider),
        )
        self.brush_size_label = ttk.Label(
            bs_inner_frame, text=f"{self .brush_size }", width=5, anchor="e"
        )
        self.brush_size_label.pack(side=tk.RIGHT, padx=(5, 0))
        color_frame = ttk.LabelFrame(left_panel, text="Color Picker", padding=10)
        color_frame.pack(fill=tk.X, pady=(0, 10))
        self.color_wheel = ColorWheelPicker(
            color_frame, self._on_color_wheel_change, show_alpha=True, show_preview=True
        )
        self.color_wheel.pack()
        ttk.Button(
            color_frame, text="Pick Color (Eyedropper)", command=self.toggle_eyedropper
        ).pack(pady=10)
        history_frame = ttk.LabelFrame(left_panel, text="History", padding=10)
        history_frame.pack(fill=tk.X, pady=(0, 10))
        btn_container = ttk.Frame(history_frame)
        btn_container.pack()
        self.undo_button = ttk.Button(btn_container, text="Undo", command=self.undo)
        self.undo_button.pack(side=tk.LEFT, padx=(0, 5))
        self.redo_button = ttk.Button(btn_container, text="Redo", command=self.redo)
        self.redo_button.pack(side=tk.LEFT)
        canvas_frame = ttk.Frame(main_frame)
        canvas_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self.pixel_canvas = PixelCanvas(
            canvas_frame, self, pick_color_callback=self._handle_eyedropper_pick
        )
        self.pixel_canvas.pack(fill=tk.BOTH, expand=True)
        self.pixel_canvas.canvas.bind("<Button-1>", self.on_canvas_press_1)
        self.pixel_canvas.canvas.bind("<B1-Motion>", self.on_canvas_motion_1)
        self.pixel_canvas.canvas.bind("<ButtonRelease-1>", self.on_canvas_release_1)
        self._update_canvas_workarea_color()

    def setup_layers_ui(self):
        layers_frame = ttk.LabelFrame(self.right_panel, text="Layers", padding=10)
        layers_frame.pack(fill=tk.BOTH, expand=True)
        tree_frame = ttk.Frame(layers_frame)
        tree_frame.pack(fill=tk.BOTH, expand=True)
        self.layers_tree = ttk.Treeview(
            tree_frame, columns=("vis", "name"), show="headings", selectmode="browse"
        )
        self.layers_tree.heading("vis", text="")
        self.layers_tree.heading("name", text="")
        self.layers_tree.column("vis", width=25, anchor="center", stretch=False)
        self.layers_tree.column("name", stretch=True)
        self.layers_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        tree_scroll = ttk.Scrollbar(
            tree_frame, orient="vertical", command=self.layers_tree.yview
        )
        tree_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        self.layers_tree.configure(yscrollcommand=tree_scroll.set)
        self.layers_tree.tag_configure("active", background="#cce5ff")
        self.layer_context_menu = tk.Menu(self.layers_tree, tearoff=0)
        self.layer_context_menu.add_command(label="Move Up", command=self.move_layer_up)
        self.layer_context_menu.add_command(
            label="Move Down", command=self.move_layer_down
        )
        self.layer_context_menu.add_separator()
        self.layer_context_menu.add_command(
            label="Merge Down", command=self.merge_layer_down
        )
        self.layer_context_menu.add_command(
            label="Duplicate", command=self.duplicate_layer
        )
        self.layer_context_menu.add_separator()
        self.layer_context_menu.add_command(
            label="Rename", command=self.rename_selected_layer
        )
        self.layer_context_menu.add_command(label="Delete", command=self.delete_layer)
        self.layer_area_context_menu = tk.Menu(self.layers_tree, tearoff=0)
        self.layer_area_context_menu.add_command(
            label="Add Layer", command=self.add_layer
        )
        self.layers_tree.bind("<<TreeviewSelect>>", self._on_layer_select)
        self.layers_tree.bind("<Button-1>", self._on_layer_tree_click)
        self.layers_tree.bind("<Button-3>", self._on_layer_right_click)
        self.layers_tree.bind("<Double-1>", self._on_layer_rename_start)
        buttons_frame = ttk.Frame(layers_frame)
        buttons_frame.pack(fill=tk.X, pady=(10, 0))
        ttk.Button(buttons_frame, text="Add Layer", command=self.add_layer).pack(
            fill=tk.X, expand=True, padx=2
        )

    def _initialize_layers(self):
        Layer._counter = 1
        self.layers.clear()
        self.active_layer_index = -1
        self.add_layer(select=True, add_to_history=False)

    def _update_layers_ui(self):
        for item in self.layers_tree.get_children():
            self.layers_tree.delete(item)
        for i, layer in reversed(list(enumerate(self.layers))):
            self.layers_tree.insert(
                "",
                tk.END,
                iid=str(i),
                values=("👁" if layer.visible else " ", layer.name),
                tags=("active",) if i == self.active_layer_index else (),
            )
        if self.layers and 0 <= self.active_layer_index < len(self.layers):
            active_item_id = str(self.active_layer_index)
            if active_item_id not in self.layers_tree.selection():
                self.layers_tree.selection_set(active_item_id)
            self.layers_tree.see(active_item_id)

    def _on_layer_select(self, event):
        selected_items = self.layers_tree.selection()
        if not selected_items:
            return
        new_index = int(selected_items[0])
        if new_index != self.active_layer_index:
            self.active_layer_index = new_index
            self._update_layers_ui()

    def _on_layer_tree_click(self, event):
        region = self.layers_tree.identify_region(event.x, event.y)
        if region == "cell":
            item_id = self.layers_tree.identify_row(event.y)
            column = self.layers_tree.identify_column(event.x)
            if item_id and column == "#1":
                layer_index = int(item_id)
                self.layers[layer_index].visible = not self.layers[layer_index].visible
                self.pixel_canvas.force_redraw()
                self._update_layers_ui()

    def _on_layer_right_click(self, event):
        item_id = self.layers_tree.identify_row(event.y)
        if not item_id:
            self.layer_area_context_menu.post(event.x_root, event.y_root)
            return
        self.layers_tree.selection_set(item_id)
        idx, num = int(item_id), len(self.layers)
        self.layer_context_menu.entryconfig(
            "Move Up", state=tk.NORMAL if idx < num - 1 else tk.DISABLED
        )
        self.layer_context_menu.entryconfig(
            "Move Down", state=tk.NORMAL if idx > 0 else tk.DISABLED
        )
        self.layer_context_menu.entryconfig(
            "Merge Down", state=tk.NORMAL if idx > 0 else tk.DISABLED
        )
        self.layer_context_menu.entryconfig(
            "Delete", state=tk.NORMAL if num > 1 else tk.DISABLED
        )
        self.layer_context_menu.post(event.x_root, event.y_root)

    def rename_selected_layer(self):
        selected_items = self.layers_tree.selection()
        if not selected_items:
            return
        layer_index = int(selected_items[0])
        x, y, width, height = self.layers_tree.bbox(selected_items[0], "name")
        entry = ttk.Entry(self.layers_tree)
        entry.place(x=x, y=y, width=width, height=height)
        entry.insert(0, self.layers[layer_index].name)
        entry.focus_force()
        entry.select_range(0, "end")

        def on_finish(e):
            old_name = self.layers[layer_index].name
            new_name = entry.get().strip()
            if new_name and new_name != old_name:
                self.layers[layer_index].name = new_name
                self.add_action(RenameLayerAction(layer_index, old_name, new_name))
            entry.destroy()
            self._update_layers_ui()

        entry.bind("<Return>", on_finish)
        entry.bind("<FocusOut>", on_finish)

    def _on_layer_rename_start(self, event):
        region = self.layers_tree.identify_region(event.x, event.y)
        if region == "cell" and self.layers_tree.identify_column(event.x) == "#2":
            if item_id := self.layers_tree.identify_row(event.y):
                self.layers_tree.selection_set(item_id)
                self.rename_selected_layer()

    def add_layer(self, name=None, select=False, add_to_history=True):
        new_layer, prev_idx = Layer(name), self.active_layer_index
        insert_pos = prev_idx + 1 if prev_idx != -1 else 0
        self.layers.insert(insert_pos, new_layer)
        self.active_layer_index = insert_pos
        if add_to_history:
            self.add_action(AddLayerAction(new_layer, insert_pos, prev_idx))
        self._update_layers_ui()

    def delete_layer(self):
        if len(self.layers) <= 1:
            return
        prev_idx, del_idx = self.active_layer_index, self.active_layer_index
        deleted_layer = self.layers[del_idx]
        del self.layers[del_idx]
        new_idx = prev_idx if prev_idx < len(self.layers) else len(self.layers) - 1
        self.active_layer_index = new_idx
        self.add_action(DeleteLayerAction(deleted_layer, del_idx, prev_idx, new_idx))
        self.pixel_canvas.force_redraw()
        self._update_layers_ui()

    def move_layer_up(self):
        idx = self.active_layer_index
        if idx >= len(self.layers) - 1:
            return
        self.layers[idx], self.layers[idx + 1] = self.layers[idx + 1], self.layers[idx]
        self.active_layer_index += 1
        self.add_action(
            MoveLayerAction(
                from_index=idx,
                to_index=idx + 1,
                active_index_after=self.active_layer_index,
            )
        )
        self.pixel_canvas.force_redraw()
        self._update_layers_ui()

    def move_layer_down(self):
        idx = self.active_layer_index
        if idx <= 0:
            return
        self.layers[idx], self.layers[idx - 1] = self.layers[idx - 1], self.layers[idx]
        self.active_layer_index -= 1
        self.add_action(
            MoveLayerAction(
                from_index=idx,
                to_index=idx - 1,
                active_index_after=self.active_layer_index,
            )
        )
        self.pixel_canvas.force_redraw()
        self._update_layers_ui()

    def merge_layer_down(self):
        idx = self.active_layer_index
        if idx <= 0:
            return

        upper_orig = copy.deepcopy(self.layers[idx])
        lower_orig = copy.deepcopy(self.layers[idx - 1])

        upper = self.layers[idx]
        lower = self.layers[idx - 1]

        merged_data = lower.pixel_data.copy()
        for (x, y), (upper_hex, upper_alpha) in upper.pixel_data.items():
            if upper_alpha == 0:
                continue

            original_pixel = merged_data.get((x, y))
            final_hex, final_alpha = upper_hex, upper_alpha

            if (
                self.color_blending_var.get()
                and 0 < upper_alpha < 255
                and original_pixel
                and original_pixel[1] > 0
            ):
                bg_hex, bg_a_int = original_pixel
                final_hex, final_alpha = canvas_cython_helpers.blend_colors_cy(
                    upper_hex, upper_alpha, bg_hex, bg_a_int
                )

            if final_alpha > 0:
                merged_data[(x, y)] = (final_hex, final_alpha)
            elif (x, y) in merged_data:
                del merged_data[(x, y)]

        lower.pixel_data = merged_data
        self.layers.pop(idx)
        self.active_layer_index = idx - 1

        merged_lower_final = copy.deepcopy(self.layers[idx - 1])

        action = MergeLayerAction(upper_orig, lower_orig, merged_lower_final, idx)
        self.add_action(action)

        self.pixel_canvas.force_redraw()
        self._update_layers_ui()

    def duplicate_layer(self):
        if not self.active_layer:
            return
        orig_layer, prev_idx = self.active_layer, self.active_layer_index
        insert_pos = prev_idx + 1
        new_layer = Layer(name=f"{orig_layer .name } copy")
        new_layer.pixel_data, new_layer.visible = (
            copy.deepcopy(orig_layer.pixel_data),
            orig_layer.visible,
        )
        action = DuplicateLayerAction(new_layer, insert_pos, prev_idx)
        action.redo(self)
        self.add_action(action)
        self.pixel_canvas.force_redraw()
        self._update_layers_ui()

    def setup_drag_and_drop(self):
        self.root.drop_target_register(DND_FILES)
        self.root.dnd_bind("<<Drop>>", self.handle_drop)

    def handle_drop(self, event):
        filepath = event.data.strip("{}")
        if filepath.lower().endswith(
            (".png", ".jpg", ".jpeg", ".gif", ".bmp")
        ) and messagebox.askyesno(
            "Open Dropped File",
            "Open this image? Unsaved changes will be lost.",
            parent=self.root,
        ):
            self._load_image_from_path(filepath)

    def _get_tool_options(self):
        return {
            "tool": self.tool_var.get(),
            "color": self.current_color,
            "alpha": self.current_alpha,
            "brush_size": self.brush_size_var.get(),
            "shape_type": self.shape_type_var.get(),
            "fill_shape": self.fill_shape_var.get(),
            "lock_aspect": self.lock_aspect_var.get()
            and (str(self.lock_aspect_checkbox.cget("state")) == "normal"),
            "active_layer": self.active_layer,
            "active_layer_data": self.active_layer_data,
            "active_layer_index": self.active_layer_index,
        }

    def on_canvas_press_1(self, event):
        self.pixel_canvas.start_draw(event, self._get_tool_options())

    def on_canvas_motion_1(self, event):
        self.pixel_canvas.draw(event, self._get_tool_options())

    def on_canvas_release_1(self, event):
        self.pixel_canvas.stop_draw(event, self._get_tool_options())

    def _handle_eyedropper_pick(self, color, alpha):
        self.current_color, self.current_alpha = color, alpha
        self._update_color_picker_from_app_state()

    def _on_color_wheel_change(self, new_hex_color, new_alpha):
        if self.current_tool == "eraser":
            self.tool_var.set(self.last_used_tool)
            self.change_tool()
        self.current_color, self.current_alpha = new_hex_color, new_alpha

    def on_brush_size_change(self, value):
        self.brush_size_label.config(text=f"{self .brush_size_var .get ()}")

    def on_shape_type_change(self, event=None):
        shape = self.shape_type_var.get()
        checkbox_text, new_state = "Lock Aspect", tk.DISABLED
        if self.tool_var.get() == "shape" and shape in ["Rectangle", "Ellipse"]:
            checkbox_text, new_state = (
                "Lock Square" if shape == "Rectangle" else "Lock Circle"
            ), tk.NORMAL
        self.lock_aspect_checkbox.config(text=checkbox_text, state=new_state)

    def _update_shape_controls_state(self):
        is_shape_tool = self.tool_var.get() == "shape"
        self.shape_combobox.config(state="readonly" if is_shape_tool else tk.DISABLED)
        self.fill_shape_checkbox.config(
            state=tk.NORMAL if is_shape_tool else tk.DISABLED
        )
        self.on_shape_type_change()

    def _update_brush_controls_state(self):
        new_state = (
            tk.NORMAL if self.tool_var.get() in ["pencil", "eraser"] else tk.DISABLED
        )
        self.brush_size_slider.config(state=new_state)
        self.brush_size_label.config(state=new_state)

    def _update_color_picker_from_app_state(self):
        if hasattr(self, "color_wheel"):
            self.color_wheel.set_color(
                self.current_color, self.current_alpha, run_callback=False
            )

    def create_canvas(self):
        self.pixel_canvas.create_canvas()

    def show_hidden_layer_warning(self):
        messagebox.showinfo(
            "Hidden Layer", "You cannot draw on a hidden layer.", parent=self.root
        )

    def change_tool(self):
        new_tool = self.tool_var.get()
        if self.current_tool != "eraser":
            self.last_used_tool = self.current_tool
        self.current_tool = new_tool
        if self.eyedropper_mode:
            self.toggle_eyedropper()
        if self.current_tool != "shape" and self.pixel_canvas.preview_shape_item:
            self.pixel_canvas.canvas.delete(self.pixel_canvas.preview_shape_item)
            self.pixel_canvas.preview_shape_item = (
                self.pixel_canvas.start_shape_point
            ) = None
            self.pixel_canvas.drawing = False
        self._update_shape_controls_state()
        self._update_brush_controls_state()

    def toggle_eyedropper(self):
        self.eyedropper_mode = not self.eyedropper_mode
        self.pixel_canvas.canvas.configure(
            cursor="dotbox" if self.eyedropper_mode else ""
        )
        if self.eyedropper_mode and self.tool_var.get() == "fill":
            self.tool_var.set("pencil")
            self.change_tool()

    def pick_color_from_canvas_tool(self, px, py):
        self.pixel_canvas._core_pick_color_at_pixel(px, py)
        self.toggle_eyedropper()

    def choose_canvas_background_color(self):
        dialog = tk.Toplevel(self.root)
        dialog.title("Canvas Background Color")
        dialog.transient(self.root)
        dialog.grab_set()
        dialog.resizable(False, False)
        dialog.geometry("250x325")
        main_frame = ttk.Frame(dialog, padding=15)
        main_frame.pack(fill=tk.BOTH, expand=True)
        state = {"hex": self.canvas_bg_color}

        def on_dialog_color_change(new_hex, _):
            state["hex"] = new_hex

        color_wheel = ColorWheelPicker(
            main_frame, on_dialog_color_change, show_alpha=False, show_preview=True
        )
        color_wheel.set_color(self.canvas_bg_color)
        color_wheel.pack()
        button_frame = ttk.Frame(main_frame)
        button_frame.pack(side=tk.BOTTOM, pady=(15, 0))

        def apply_choice():
            if self.canvas_bg_color != state["hex"]:
                self.canvas_bg_color = state["hex"]
                self._update_canvas_workarea_color()
                if self.show_canvas_background_var.get():
                    self.pixel_canvas.force_redraw()
            dialog.destroy()

        ttk.Button(button_frame, text="OK", command=apply_choice).pack(
            side=tk.LEFT, padx=5
        )
        ttk.Button(button_frame, text="Cancel", command=dialog.destroy).pack(
            side=tk.LEFT, padx=5
        )
        dialog.bind("<Return>", lambda e: apply_choice())
        dialog.bind("<Escape>", lambda e: dialog.destroy())

    def toggle_grid_visibility(self):
        self.pixel_canvas.rescale_canvas()

    def toggle_canvas_background_display(self):
        self._update_canvas_workarea_color()
        self.pixel_canvas.force_redraw()
        self._update_save_background_menu_state()

    def toggle_pixel_alpha_rendering(self):
        self.pixel_canvas.force_redraw()

    def new_canvas(self):
        if any(
            layer.pixel_data for layer in self.layers
        ) and not messagebox.askokcancel(
            "New", "Clear canvas? Unsaved changes may be lost."
        ):
            return
        self._initialize_layers()
        self.current_filename = None
        self.canvas_bg_color = "#FFFFFF"
        self.root.title("Pixel Art Drawing App")
        self._update_canvas_workarea_color()
        self._clear_history()
        self.create_canvas()
        self._update_layers_ui()

    def open_file(self):
        if any(
            layer.pixel_data for layer in self.layers
        ) and not messagebox.askokcancel(
            "Open", "Clear canvas? Unsaved changes may be lost."
        ):
            return
        if filename := filedialog.askopenfilename(
            title="Open PNG", filetypes=[("PNG", "*.png"), ("All", "*.*")]
        ):
            self._load_image_from_path(filename)

    def _load_image_from_path(self, filename):
        try:
            with Image.open(filename) as img:
                img = img.convert("RGBA")
                old_w, old_h = self.canvas_width, self.canvas_height
                self.canvas_width, self.canvas_height = img.width, img.height

                self._initialize_layers()
                self.layers[0].name = os.path.basename(filename)

                rgba_data = numpy.array(img)
                self.layers[0].pixel_data = canvas_cython_helpers.process_image_data_cy(
                    rgba_data
                )
                self._clear_history()
                self.create_canvas()
                self._update_layers_ui()
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
        (
            self.export_to_png(self.current_filename)
            if self.current_filename
            else self.export_png()
        )

    def export_png(self):
        if filename := filedialog.asksaveasfilename(
            title="Export PNG As", defaultextension=".png", filetypes=[("PNG", "*.png")]
        ):
            self.export_to_png(filename)

    def export_to_png(self, filename):
        try:
            img = Image.new(
                "RGBA",
                (self.canvas_width, self.canvas_height),
                (
                    hex_to_rgb(self.canvas_bg_color) + (255,)
                    if self.show_canvas_background_var.get()
                    and self.save_background_var.get()
                    else (0, 0, 0, 0)
                ),
            )
            for layer in self.layers:
                if not layer.visible:
                    continue
                layer_img = Image.new(
                    "RGBA", (self.canvas_width, self.canvas_height), (0, 0, 0, 0)
                )
                for (x, y), (h, a) in layer.pixel_data.items():
                    if h != "transparent" and a > 0:
                        layer_img.putpixel((x, y), hex_to_rgb(h) + (a,))
                img = Image.alpha_composite(img, layer_img)
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
