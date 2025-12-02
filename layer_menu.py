import tkinter as tk
from tkinter import ttk, messagebox
import copy

from utilities import validate_int_entry, sanitize_int_input, handle_slider_click
import canvas_cython_helpers
from actions import (
    AddLayerAction,
    DuplicateLayerAction,
    DeleteLayerAction,
    MoveLayerAction,
    RenameLayerAction,
    MergeLayerAction,
)


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
        self.opacity = 255


class LayerPanel(ttk.Frame):
    def __init__(self, parent, app):
        super().__init__(parent)
        self.app = app
        self.layers = []
        self.active_layer_index = -1

        self.drag_start_item = None
        self.drag_floating_window = None

        self._setup_ui()
        self.initialize_layers()

    @property
    def active_layer(self):
        return (
            self.layers[self.active_layer_index]
            if self.layers and 0 <= self.active_layer_index < len(self.layers)
            else None
        )

    def _setup_ui(self):

        self.pack(fill=tk.BOTH, expand=True)

        tree_frame = ttk.Frame(self)
        tree_frame.pack(fill=tk.BOTH, expand=True)

        self.tree = ttk.Treeview(
            tree_frame, columns=("vis", "name"), show="tree", selectmode="browse"
        )
        self.tree.column("#0", width=0, stretch=tk.NO)
        self.tree.column("vis", width=25, anchor="center", stretch=False)
        self.tree.column("name", stretch=True)
        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        tree_scroll = ttk.Scrollbar(
            tree_frame, orient="vertical", command=self.tree.yview
        )
        tree_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        self.tree.configure(yscrollcommand=tree_scroll.set)
        self.tree.tag_configure("active", background="#cce5ff")

        self.tree.bind("<<TreeviewSelect>>", self._on_layer_select)
        self.tree.bind("<Button-1>", self._on_layer_tree_click)
        self.tree.bind("<Button-3>", self._on_layer_right_click)
        self.tree.bind("<Double-1>", self._on_layer_rename_start)

        self.tree.bind("<ButtonPress-1>", self.on_layer_drag_start, add="+")
        self.tree.bind("<B1-Motion>", self.on_layer_drag_motion, add="+")
        self.tree.bind("<ButtonRelease-1>", self.on_layer_drag_release, add="+")

        self.context_menu = tk.Menu(self.tree, tearoff=0)
        self.context_menu.add_command(label="Add Layer", command=self.add_layer)

        buttons_frame = ttk.Frame(self)
        buttons_frame.pack(fill=tk.X, pady=(10, 0))
        ttk.Button(buttons_frame, text="Add Layer", command=self.add_layer).pack(
            fill=tk.X, expand=True, padx=2
        )

    def initialize_layers(self):
        Layer._counter = 1
        self.layers.clear()
        self.active_layer_index = -1
        self.add_layer(select=True, add_to_history=False)

    def update_ui(self):
        for item in self.tree.get_children():
            self.tree.delete(item)
        for i, layer in reversed(list(enumerate(self.layers))):
            self.tree.insert(
                "",
                tk.END,
                iid=str(i),
                values=("✅" if layer.visible else "❌", layer.name),
                tags=("active",) if i == self.active_layer_index else (),
            )
        if self.layers and 0 <= self.active_layer_index < len(self.layers):
            active_item_id = str(self.active_layer_index)
            if active_item_id not in self.tree.selection():
                self.tree.selection_set(active_item_id)
            self.tree.see(active_item_id)

    def _on_layer_select(self, event):
        if self.drag_start_item:
            return
        selected_items = self.tree.selection()
        if not selected_items:
            return
        new_index = int(selected_items[0])

        if new_index != self.active_layer_index:
            self.active_layer_index = new_index
            self.update_ui()

    def _on_layer_tree_click(self, event):
        region = self.tree.identify_region(event.x, event.y)
        if region == "cell":
            item_id = self.tree.identify_row(event.y)
            column = self.tree.identify_column(event.x)
            if item_id and column == "#1":
                layer_index = int(item_id)
                self.layers[layer_index].visible = not self.layers[layer_index].visible
                self.app.pixel_canvas.force_redraw()
                self.update_ui()
                return "break"

    def _on_layer_right_click(self, event):
        item_id = self.tree.identify_row(event.y)
        if not item_id:
            self.context_menu.post(event.x_root, event.y_root)
            return
        self.tree.selection_set(item_id)
        LayerMenu(
            self.app.root, self.app, self, int(item_id), event.x_root, event.y_root
        )

    def _on_layer_rename_start(self, event):
        region = self.tree.identify_region(event.x, event.y)
        if region == "cell" and self.tree.identify_column(event.x) == "#2":
            if item_id := self.tree.identify_row(event.y):
                self.tree.selection_set(item_id)
                self.rename_selected_layer()

    def on_layer_drag_start(self, event):
        region = self.tree.identify_region(event.x, event.y)
        if region == "tree" or region == "cell":
            item = self.tree.identify_row(event.y)
            if item:
                self.drag_start_item = item
                item_values = self.tree.item(item, "values")
                if item_values:
                    display_text = f"{item_values [0 ]} {item_values [1 ]}"
                    self.drag_floating_window = tk.Toplevel(self.app.root)
                    self.drag_floating_window.overrideredirect(True)
                    self.drag_floating_window.attributes("-topmost", True)
                    lbl = tk.Label(
                        self.drag_floating_window,
                        text=display_text,
                        bg="#e1e1e1",
                        fg="#000000",
                        relief="solid",
                        borderwidth=1,
                    )
                    lbl.pack()
                    self.drag_floating_window.geometry(
                        f"+{event .x_root +15 }+{event .y_root }"
                    )
                    self.tree.item(item, values=("", ""))

    def on_layer_drag_motion(self, event):
        if self.drag_floating_window:
            self.drag_floating_window.geometry(
                f"+{event .x_root +15 }+{event .y_root }"
            )
        if self.drag_start_item:
            target = self.tree.identify_row(event.y)
            if target:
                self.tree.selection_set(target)
            return "break"

    def on_layer_drag_release(self, event):
        if self.drag_floating_window:
            self.drag_floating_window.destroy()
            self.drag_floating_window = None

        if not self.drag_start_item:
            return

        target_item = self.tree.identify_row(event.y)
        to_index = -1

        if target_item:
            to_index = int(target_item)
        else:
            if event.y < 0:
                to_index = len(self.layers) - 1
            else:
                to_index = 0

        from_index = int(self.drag_start_item)
        self.drag_start_item = None

        if to_index != -1 and to_index != from_index:
            prev_active_index = self.active_layer_index
            active_layer_obj = self.layers[self.active_layer_index]

            layer_to_move = self.layers.pop(from_index)
            self.layers.insert(to_index, layer_to_move)

            self.active_layer_index = self.layers.index(active_layer_obj)

            action = MoveLayerAction(
                from_index=from_index,
                to_index=to_index,
                active_index_before=prev_active_index,
                active_index_after=self.active_layer_index,
            )
            self.app.add_action(action)
            self.app.pixel_canvas.force_redraw()
            self.update_ui()
        else:
            self.update_ui()

        self.drag_start_item = None

    def add_layer(self, name=None, select=False, add_to_history=True):
        new_layer, prev_idx = Layer(name), self.active_layer_index
        insert_pos = prev_idx + 1 if prev_idx != -1 else 0
        self.layers.insert(insert_pos, new_layer)
        self.active_layer_index = insert_pos
        if add_to_history:
            self.app.add_action(AddLayerAction(new_layer, insert_pos, prev_idx))
        self.update_ui()

    def delete_layer(self):
        if len(self.layers) <= 1:
            return
        prev_idx, del_idx = self.active_layer_index, self.active_layer_index
        deleted_layer = self.layers[del_idx]
        del self.layers[del_idx]
        new_idx = prev_idx if prev_idx < len(self.layers) else len(self.layers) - 1
        self.active_layer_index = new_idx
        self.app.add_action(
            DeleteLayerAction(deleted_layer, del_idx, prev_idx, new_idx)
        )
        self.app.pixel_canvas.force_redraw()
        self.update_ui()

    def move_layer_up(self):
        idx = self.active_layer_index
        if idx >= len(self.layers) - 1:
            return
        prev_active_idx = self.active_layer_index
        self.layers[idx], self.layers[idx + 1] = self.layers[idx + 1], self.layers[idx]
        self.active_layer_index += 1
        self.app.add_action(
            MoveLayerAction(
                from_index=idx,
                to_index=idx + 1,
                active_index_before=prev_active_idx,
                active_index_after=self.active_layer_index,
            )
        )
        self.app.pixel_canvas.force_redraw()
        self.update_ui()

    def move_layer_down(self):
        idx = self.active_layer_index
        if idx <= 0:
            return
        prev_active_idx = self.active_layer_index
        self.layers[idx], self.layers[idx - 1] = self.layers[idx - 1], self.layers[idx]
        self.active_layer_index -= 1
        self.app.add_action(
            MoveLayerAction(
                from_index=idx,
                to_index=idx - 1,
                active_index_before=prev_active_idx,
                active_index_after=self.active_layer_index,
            )
        )
        self.app.pixel_canvas.force_redraw()
        self.update_ui()

    def merge_layer_down(self):
        idx = self.active_layer_index
        if idx <= 0:
            return

        upper_orig = copy.deepcopy(self.layers[idx])
        lower_orig = copy.deepcopy(self.layers[idx - 1])

        upper = self.layers[idx]
        lower = self.layers[idx - 1]

        merged_data = {}
        lower_opacity_factor = lower.opacity / 255.0

        for coord, (hex_val, alpha) in lower.pixel_data.items():
            baked_alpha = int(alpha * lower_opacity_factor)
            if baked_alpha > 0:
                merged_data[coord] = (hex_val, baked_alpha)

        upper_opacity_factor = upper.opacity / 255.0

        for coord, (upper_hex, upper_alpha) in upper.pixel_data.items():
            effective_alpha = int(upper_alpha * upper_opacity_factor)
            if effective_alpha == 0:
                continue

            bg_pixel = merged_data.get(coord)
            final_hex, final_alpha = upper_hex, effective_alpha

            if (
                self.app.color_blending_var.get()
                and 0 < effective_alpha < 255
                and bg_pixel
            ):
                bg_hex, bg_a_int = bg_pixel
                final_hex, final_alpha = canvas_cython_helpers.blend_colors_cy(
                    upper_hex, effective_alpha, bg_hex, bg_a_int
                )

            if final_alpha > 0:
                merged_data[coord] = (final_hex, final_alpha)
            elif coord in merged_data:
                del merged_data[coord]

        lower.pixel_data = merged_data
        lower.opacity = 255

        self.layers.pop(idx)
        self.active_layer_index = idx - 1

        merged_lower_final = copy.deepcopy(self.layers[idx - 1])

        action = MergeLayerAction(upper_orig, lower_orig, merged_lower_final, idx)
        self.app.add_action(action)

        self.app.pixel_canvas.force_redraw()
        self.update_ui()

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
        new_layer.opacity = orig_layer.opacity
        action = DuplicateLayerAction(new_layer, insert_pos, prev_idx)
        action.redo(self.app)
        self.app.add_action(action)
        self.app.pixel_canvas.force_redraw()
        self.update_ui()

    def rename_selected_layer(self):
        selected_items = self.tree.selection()
        if not selected_items:
            return
        layer_index = int(selected_items[0])
        x, y, width, height = self.tree.bbox(selected_items[0], "name")
        entry = ttk.Entry(self.tree)
        entry.place(x=x, y=y, width=width, height=height)
        entry.insert(0, self.layers[layer_index].name)
        entry.focus_force()
        entry.select_range(0, "end")

        def on_finish(e):
            old_name = self.layers[layer_index].name
            new_name = entry.get().strip()
            if new_name and new_name != old_name:
                self.layers[layer_index].name = new_name
                self.app.add_action(RenameLayerAction(layer_index, old_name, new_name))
            entry.destroy()
            self.update_ui()

        entry.bind("<Return>", on_finish)
        entry.bind("<FocusOut>", on_finish)


class LayerMenu(tk.Toplevel):
    def __init__(self, master, app, layer_panel, layer_index, x, y):
        super().__init__(master)
        self.app = app
        self.layer_panel = layer_panel
        self.layer_index = layer_index
        self.target_layer = self.layer_panel.layers[layer_index]

        self.overrideredirect(True)
        self.attributes("-topmost", True)
        self.geometry(f"+{x }+{y }")

        self.configure(bg="#e1e1e1")

        self.style = ttk.Style()
        self.style.configure("Danger.TButton", foreground="red")
        self.style.map("Danger.TButton", foreground=[("active", "#cc0000")])

        self.container = tk.Frame(self, bg="#d0d0d0", bd=1, relief="solid")
        self.container.pack(fill=tk.BOTH, expand=True)

        self.frame = ttk.Frame(self.container, padding=5)
        self.frame.pack(fill=tk.BOTH, expand=True, padx=1, pady=1)

        header = ttk.Label(
            self.frame, text=self.target_layer.name, font=("Segoe UI", 9, "bold")
        )
        header.pack(fill=tk.X, pady=(0, 5))

        ttk.Separator(self.frame, orient="horizontal").pack(fill=tk.X, pady=(0, 5))

        opacity_frame = ttk.Frame(self.frame)
        opacity_frame.pack(fill=tk.X, pady=(0, 5))

        ttk.Label(opacity_frame, text="Opacity:").pack(side=tk.LEFT, padx=(0, 2))

        self.opacity_var = tk.IntVar(value=self.target_layer.opacity)

        self.opacity_slider = tk.Scale(
            opacity_frame,
            from_=0,
            to=255,
            orient=tk.HORIZONTAL,
            variable=self.opacity_var,
            command=self._on_slider_change,
            showvalue=0,
            bg="#e1e1e1",
            troughcolor="#c0c0c0",
            activebackground="#a0a0a0",
            sliderrelief=tk.RAISED,
            highlightthickness=0,
            bd=0,
            width=10,
            length=100,
        )
        self.opacity_slider.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 5))
        self.opacity_slider.bind(
            "<Button-1>", lambda e: handle_slider_click(e, self.opacity_slider)
        )

        vcmd = (self.register(validate_int_entry), "%P")
        self.opacity_entry = ttk.Entry(
            opacity_frame, width=4, validate="key", validatecommand=vcmd
        )
        self.opacity_entry.pack(side=tk.LEFT)
        self.opacity_entry.insert(0, str(self.target_layer.opacity))

        self.opacity_entry.bind("<KeyRelease>", self._on_entry_change)
        self.opacity_entry.bind("<FocusOut>", self._on_entry_focus_out)
        self.opacity_entry.bind("<Return>", self._on_entry_focus_out)

        ttk.Separator(self.frame, orient="horizontal").pack(fill=tk.X, pady=5)

        num_layers = len(self.layer_panel.layers)
        can_move_up = layer_index < num_layers - 1
        can_move_down = layer_index > 0
        can_merge_down = layer_index > 0
        can_delete = num_layers > 1

        self._add_button("Move Up", self._cmd_move_up, can_move_up)
        self._add_button("Move Down", self._cmd_move_down, can_move_down)

        ttk.Separator(self.frame, orient="horizontal").pack(fill=tk.X, pady=5)

        self._add_button("Merge Down", self._cmd_merge_down, can_merge_down)
        self._add_button("Duplicate", self._cmd_duplicate, True)

        ttk.Separator(self.frame, orient="horizontal").pack(fill=tk.X, pady=5)

        self._add_button("Rename", self._cmd_rename, True)

        self._add_button("Delete", self._cmd_delete, can_delete, style="Danger.TButton")

        self.after(10, self._set_initial_focus)
        self.bind("<FocusOut>", self._on_focus_out)
        self.bind("<Escape>", lambda e: self.destroy())

    def _add_button(self, text, command, enabled, style=None):
        state = tk.NORMAL if enabled else tk.DISABLED
        if style:
            btn = ttk.Button(
                self.frame, text=text, command=command, state=state, style=style
            )
        else:
            btn = ttk.Button(self.frame, text=text, command=command, state=state)
        btn.pack(fill=tk.X, pady=1)

    def _set_initial_focus(self):
        self.focus_force()

    def _on_focus_out(self, event):
        new_focus = self.focus_get()
        if new_focus is None:
            self.destroy()
            return
        if new_focus != self and not str(new_focus).startswith(str(self)):
            self.destroy()

    def _on_slider_change(self, value):
        val = int(value)
        current_entry = self.opacity_entry.get()
        if current_entry != str(val):
            self.opacity_entry.delete(0, tk.END)
            self.opacity_entry.insert(0, str(val))
        if self.target_layer.opacity != val:
            self.target_layer.opacity = val
            self.app.pixel_canvas.force_redraw()

    def _on_entry_change(self, event):
        val_str = self.opacity_entry.get()
        sanitized = sanitize_int_input(val_str)
        if sanitized is not None:
            if sanitized != val_str:
                self.opacity_entry.delete(0, tk.END)
                self.opacity_entry.insert(0, sanitized)
                self.opacity_entry.icursor(tk.END)
                val_str = sanitized
            val = int(val_str)
            if val > 255:
                val = 255
                self.opacity_entry.delete(0, tk.END)
                self.opacity_entry.insert(0, "255")
            self.opacity_var.set(val)
            if self.target_layer.opacity != val:
                self.target_layer.opacity = val
                self.app.pixel_canvas.force_redraw()

    def _on_entry_focus_out(self, event):
        val_str = self.opacity_entry.get()
        if not val_str:
            self.opacity_entry.insert(0, str(self.target_layer.opacity))
        else:
            sanitized = sanitize_int_input(val_str)
            if sanitized:
                val = int(sanitized)
                if val > 255:
                    val = 255
                self.opacity_entry.delete(0, tk.END)
                self.opacity_entry.insert(0, str(val))
                self.opacity_var.set(val)
                if self.target_layer.opacity != val:
                    self.target_layer.opacity = val
                    self.app.pixel_canvas.force_redraw()

    def _cmd_move_up(self):
        self.layer_panel.move_layer_up()
        self.destroy()

    def _cmd_move_down(self):
        self.layer_panel.move_layer_down()
        self.destroy()

    def _cmd_merge_down(self):
        self.layer_panel.merge_layer_down()
        self.destroy()

    def _cmd_duplicate(self):
        self.layer_panel.duplicate_layer()
        self.destroy()

    def _cmd_rename(self):
        self.destroy()
        self.layer_panel.rename_selected_layer()

    def _cmd_delete(self):
        self.layer_panel.delete_layer()
        self.destroy()
