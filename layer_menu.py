import tkinter as tk
from tkinter import ttk
from utilities import validate_int_entry, sanitize_int_input


class LayerMenu(tk.Toplevel):
    def __init__(self, master, app, layer_index, x, y):
        super().__init__(master)
        self.app = app
        self.layer_index = layer_index
        self.target_layer = self.app.layers[layer_index]

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

        num_layers = len(app.layers)
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
        self.app.move_layer_up()
        self.destroy()

    def _cmd_move_down(self):
        self.app.move_layer_down()
        self.destroy()

    def _cmd_merge_down(self):
        self.app.merge_layer_down()
        self.destroy()

    def _cmd_duplicate(self):
        self.app.duplicate_layer()
        self.destroy()

    def _cmd_rename(self):
        self.destroy()

        self.app.rename_selected_layer()

    def _cmd_delete(self):
        self.app.delete_layer()
        self.destroy()
