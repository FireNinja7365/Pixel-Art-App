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

    DRAG_THRESHOLD = 15
    DRAG_DELAY_MS = 300
    VISIBLE_EMOJI = "✅"
    INVISIBLE_EMOJI = "❌"

    def __init__(self, parent, app):
        super().__init__(parent)
        self.app = app
        self.layers = []
        self.active_layer_index = -1

        self._drag_state = {
            "start_item": None,
            "orig_index": -1,
            "floating_window": None,
            "timer": None,
            "start_x": 0,
            "start_y": 0,
            "candidate_item": None,
        }

        self._setup_ui()
        self.initialize_layers()

    @property
    def active_layer(self):
        if not self.layers or not (0 <= self.active_layer_index < len(self.layers)):
            return None
        return self.layers[self.active_layer_index]

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

        self._bind_events()

        self.context_menu = tk.Menu(self.tree, tearoff=0)
        self.context_menu.add_command(label="Add Layer", command=self.add_layer)

        buttons_frame = ttk.Frame(self)
        buttons_frame.pack(fill=tk.X, pady=(10, 0))
        ttk.Button(buttons_frame, text="Add Layer", command=self.add_layer).pack(
            fill=tk.X, expand=True, padx=2
        )

    def _bind_events(self):

        self.tree.bind("<<TreeviewSelect>>", self._on_layer_select)
        self.tree.bind("<Button-1>", self._on_layer_tree_click)
        self.tree.bind("<Button-3>", self._on_layer_right_click)
        self.tree.bind("<Double-1>", self._on_layer_rename_start)
        self.tree.bind("<ButtonPress-1>", self._on_drag_start, add="+")
        self.tree.bind("<B1-Motion>", self._on_drag_motion, add="+")
        self.tree.bind("<ButtonRelease-1>", self._on_drag_release, add="+")

    def initialize_layers(self):
        Layer._counter = 1
        self.layers.clear()
        self.active_layer_index = -1
        self.add_layer(select=True, add_to_history=False)

    def update_ui(self):

        for item in self.tree.get_children():
            self.tree.delete(item)

        for i, layer in reversed(list(enumerate(self.layers))):
            vis_emoji = self.VISIBLE_EMOJI if layer.visible else self.INVISIBLE_EMOJI
            tags = ("active",) if i == self.active_layer_index else ()
            self.tree.insert(
                "", tk.END, iid=str(i), values=(vis_emoji, layer.name), tags=tags
            )

        if 0 <= self.active_layer_index < len(self.layers):
            active_id = str(self.active_layer_index)
            if active_id not in self.tree.selection():
                self.tree.selection_set(active_id)
            self.tree.see(active_id)

    def _on_layer_select(self, event):
        if self._drag_state["start_item"]:
            return

        selected = self.tree.selection()
        if not selected:
            return

        new_index = int(selected[0])
        if new_index != self.active_layer_index:
            self.active_layer_index = new_index
            self.update_ui()

    def _on_layer_tree_click(self, event):
        region = self.tree.identify_region(event.x, event.y)
        if region == "cell":
            item_id = self.tree.identify_row(event.y)
            column = self.tree.identify_column(event.x)
            if item_id and column == "#1":
                self._toggle_layer_visibility(item_id)
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
        column = self.tree.identify_column(event.x)
        item_id = self.tree.identify_row(event.y)

        if region == "cell" and item_id:
            if column == "#1":
                self._toggle_layer_visibility(item_id)
            elif column == "#2":
                self.tree.selection_set(item_id)
                self.rename_selected_layer()

    def _toggle_layer_visibility(self, item_id):
        layer_index = int(item_id)
        layer = self.layers[layer_index]
        layer.visible = not layer.visible

        emoji = self.VISIBLE_EMOJI if layer.visible else self.INVISIBLE_EMOJI
        self.tree.set(item_id, column="vis", value=emoji)
        self.app.pixel_canvas.force_redraw()

    def _on_drag_start(self, event):
        region = self.tree.identify_region(event.x, event.y)
        if region in ("tree", "cell"):
            item = self.tree.identify_row(event.y)
            if item:
                self._drag_state.update(
                    {
                        "candidate_item": item,
                        "start_x": event.x,
                        "start_y": event.y,
                        "start_item": None,
                        "orig_index": -1,
                    }
                )

                if self._drag_state["timer"]:
                    self.after_cancel(self._drag_state["timer"])
                self._drag_state["timer"] = self.after(
                    self.DRAG_DELAY_MS, lambda: self._trigger_drag_start(event)
                )

    def _trigger_drag_start(self, event):
        self._drag_state["timer"] = None
        if not self._drag_state["candidate_item"]:
            return

        self._drag_state["start_item"] = self._drag_state["candidate_item"]
        self._drag_state["orig_index"] = self.tree.index(self._drag_state["start_item"])

        item_values = self.tree.item(self._drag_state["start_item"], "values")
        if item_values:
            self._create_floating_window(item_values, event)
            self.tree.item(self._drag_state["start_item"], values=("", ""))

    def _create_floating_window(self, item_values, event):

        display_text = f"{item_values [0 ]} {item_values [1 ]}"
        window = tk.Toplevel(self.app.root)
        window.overrideredirect(True)
        window.attributes("-topmost", True)

        lbl = tk.Label(
            window,
            text=display_text,
            bg="#e1e1e1",
            fg="#000000",
            relief="solid",
            borderwidth=1,
        )
        lbl.pack()

        x = event.x_root + 15 if event else self.winfo_pointerx() + 15
        y = event.y_root if event else self.winfo_pointery()
        window.geometry(f"+{x }+{y }")

        self._drag_state["floating_window"] = window

    def _on_drag_motion(self, event):
        if self._drag_state["start_item"]:

            if self._drag_state["floating_window"]:
                self._drag_state["floating_window"].geometry(
                    f"+{event .x_root +15 }+{event .y_root }"
                )

            target_item = self.tree.identify_row(event.y)
            if target_item and target_item != self._drag_state["start_item"]:
                target_index = self.tree.index(target_item)
                current_index = self.tree.index(self._drag_state["start_item"])
                if current_index != target_index:
                    self.tree.move(self._drag_state["start_item"], "", target_index)
            return "break"

        elif self._drag_state["candidate_item"]:

            dx = abs(event.x - self._drag_state["start_x"])
            dy = abs(event.y - self._drag_state["start_y"])
            if dx > self.DRAG_THRESHOLD or dy > self.DRAG_THRESHOLD:
                if self._drag_state["timer"]:
                    self.after_cancel(self._drag_state["timer"])
                    self._drag_state["timer"] = None
                self._trigger_drag_start(event)

    def _on_drag_release(self, event):
        if self._drag_state["timer"]:
            self.after_cancel(self._drag_state["timer"])
            self._drag_state["timer"] = None

        self._drag_state["candidate_item"] = None

        if self._drag_state["floating_window"]:
            self._drag_state["floating_window"].destroy()
            self._drag_state["floating_window"] = None

        if not self._drag_state["start_item"]:
            return

        to_index = self.tree.index(self._drag_state["start_item"])
        from_index = self._drag_state["orig_index"]

        self._drag_state["start_item"] = None
        self._drag_state["orig_index"] = -1

        list_len = len(self.layers)
        list_from_index = list_len - 1 - from_index
        list_to_index = list_len - 1 - to_index

        if list_to_index != list_from_index:
            self._finalize_layer_move(list_from_index, list_to_index)

        self.update_ui()

    def _finalize_layer_move(self, from_idx, to_idx):

        prev_active_index = self.active_layer_index
        active_layer_obj = self.layers[self.active_layer_index]

        layer_to_move = self.layers.pop(from_idx)
        self.layers.insert(to_idx, layer_to_move)

        self.active_layer_index = self.layers.index(active_layer_obj)

        action = MoveLayerAction(
            from_index=from_idx,
            to_index=to_idx,
            active_index_before=prev_active_index,
            active_index_after=self.active_layer_index,
        )
        self.app.add_action(action)
        self.app.pixel_canvas.force_redraw()

    def add_layer(self, name=None, select=False, add_to_history=True):
        new_layer = Layer(name)
        prev_idx = self.active_layer_index
        insert_pos = prev_idx + 1 if prev_idx != -1 else 0
        self.layers.insert(insert_pos, new_layer)
        self.active_layer_index = insert_pos
        if add_to_history:
            self.app.add_action(AddLayerAction(new_layer, insert_pos, prev_idx))
        self.update_ui()

    def delete_layer(self):
        if len(self.layers) <= 1:
            return

        del_idx = self.active_layer_index
        deleted_layer = self.layers[del_idx]
        del self.layers[del_idx]

        new_idx = min(del_idx, len(self.layers) - 1)
        self.active_layer_index = new_idx

        self.app.add_action(DeleteLayerAction(deleted_layer, del_idx, del_idx, new_idx))
        self.app.pixel_canvas.force_redraw()
        self.update_ui()

    def move_layer_up(self):
        idx = self.active_layer_index
        if idx >= len(self.layers) - 1:
            return
        self._swap_layers(idx, idx + 1)

    def move_layer_down(self):
        idx = self.active_layer_index
        if idx <= 0:
            return
        self._swap_layers(idx, idx - 1)

    def _swap_layers(self, from_idx, to_idx):

        prev_active_idx = self.active_layer_index
        self.layers[from_idx], self.layers[to_idx] = (
            self.layers[to_idx],
            self.layers[from_idx],
        )
        self.active_layer_index = to_idx

        self.app.add_action(
            MoveLayerAction(
                from_index=from_idx,
                to_index=to_idx,
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

        merged_data = self._merge_pixel_data(lower, upper)

        lower.pixel_data = merged_data
        lower.opacity = 255

        self.layers.pop(idx)
        self.active_layer_index = idx - 1

        merged_lower_final = copy.deepcopy(self.layers[idx - 1])
        action = MergeLayerAction(upper_orig, lower_orig, merged_lower_final, idx)
        self.app.add_action(action)

        self.app.pixel_canvas.force_redraw()
        self.update_ui()

    def _merge_pixel_data(self, lower, upper):

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

        return merged_data

    def duplicate_layer(self):
        if not self.active_layer:
            return

        orig_layer = self.active_layer
        prev_idx = self.active_layer_index
        insert_pos = prev_idx + 1

        new_layer = Layer(name=f"{orig_layer .name } copy")
        new_layer.pixel_data = copy.deepcopy(orig_layer.pixel_data)
        new_layer.visible = orig_layer.visible
        new_layer.opacity = orig_layer.opacity

        action = DuplicateLayerAction(new_layer, insert_pos, prev_idx)
        action.redo(self.app)
        self.app.add_action(action)
        self.app.pixel_canvas.force_redraw()
        self.update_ui()

    def rename_selected_layer(self):
        selected = self.tree.selection()
        if not selected:
            return

        layer_index = int(selected[0])
        x, y, width, height = self.tree.bbox(selected[0], "name")

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
        self.target_layer = layer_panel.layers[layer_index]

        self.overrideredirect(True)
        self.attributes("-topmost", True)
        self.configure(bg="#e1e1e1")

        self._setup_styles()
        self._create_widgets()
        self._position_menu(x, y)
        self._setup_bindings()

    def _setup_styles(self):

        self.style = ttk.Style()
        self.style.configure("Danger.TButton", foreground="red")
        self.style.map("Danger.TButton", foreground=[("active", "#cc0000")])

    def _create_widgets(self):

        container = tk.Frame(self, bg="#d0d0d0", bd=1, relief="solid")
        container.pack(fill=tk.BOTH, expand=True)

        self.frame = ttk.Frame(container, padding=5)
        self.frame.pack(fill=tk.BOTH, expand=True, padx=1, pady=1)

        header = ttk.Label(
            self.frame, text=self.target_layer.name, font=("Segoe UI", 9, "bold")
        )
        header.pack(fill=tk.X, pady=(0, 5))
        ttk.Separator(self.frame, orient="horizontal").pack(fill=tk.X, pady=(0, 5))

        self._create_opacity_controls()

        ttk.Separator(self.frame, orient="horizontal").pack(fill=tk.X, pady=5)

        num_layers = len(self.layer_panel.layers)
        self._add_button("Merge Down", self._cmd_merge_down, self.layer_index > 0)
        self._add_button("Duplicate", self._cmd_duplicate, True)
        ttk.Separator(self.frame, orient="horizontal").pack(fill=tk.X, pady=5)
        self._add_button("Rename", self._cmd_rename, True)
        self._add_button(
            "Delete", self._cmd_delete, num_layers > 1, style="Danger.TButton"
        )

    def _create_opacity_controls(self):

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

    def _position_menu(self, x, y):

        self.update_idletasks()

        menu_width = self.winfo_reqwidth()
        menu_height = self.winfo_reqheight()
        screen_width = self.winfo_screenwidth()
        screen_height = self.winfo_screenheight()

        x = max(0, min(x, screen_width - menu_width))
        y = max(0, min(y, screen_height - menu_height))

        self.geometry(f"+{x }+{y }")

    def _setup_bindings(self):

        self.after(10, self._set_initial_focus)
        self.bind("<FocusOut>", self._on_focus_out)
        self.bind("<Escape>", lambda e: self.destroy())

    def _add_button(self, text, command, enabled, style=None):

        state = tk.NORMAL if enabled else tk.DISABLED
        btn = ttk.Button(
            self.frame,
            text=text,
            command=command,
            state=state,
            style=style if style else None,
        )
        btn.pack(fill=tk.X, pady=1)

    def _set_initial_focus(self):
        self.focus_force()

    def _on_focus_out(self, event):
        new_focus = self.focus_get()
        if new_focus is None or (
            new_focus != self and not str(new_focus).startswith(str(self))
        ):
            self.destroy()

    def _on_slider_change(self, value):

        val = int(value)
        current = self.opacity_entry.get()
        if current != str(val):
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

            val = min(int(val_str), 255)
            if val != int(val_str):
                self.opacity_entry.delete(0, tk.END)
                self.opacity_entry.insert(0, str(val))

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
                val = min(int(sanitized), 255)
                self.opacity_entry.delete(0, tk.END)
                self.opacity_entry.insert(0, str(val))
                self.opacity_var.set(val)
                if self.target_layer.opacity != val:
                    self.target_layer.opacity = val
                    self.app.pixel_canvas.force_redraw()

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
