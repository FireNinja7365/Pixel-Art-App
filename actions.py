class Action:

    def undo(self, app):

        raise NotImplementedError

    def redo(self, app):

        raise NotImplementedError


class PixelAction(Action):

    def __init__(self, layer_index, pixels_before, pixels_after):
        self.layer_index = layer_index
        self.pixels_before = pixels_before
        self.pixels_after = pixels_after

    def undo(self, app):
        layer_data = app.layers[self.layer_index].pixel_data
        for (x, y), data_before in self.pixels_before.items():
            if data_before:
                layer_data[(x, y)] = data_before
            elif (x, y) in layer_data:
                del layer_data[(x, y)]
            app._update_dirty_bbox(x, y)

    def redo(self, app):
        layer_data = app.layers[self.layer_index].pixel_data
        for (x, y), data_after in self.pixels_after.items():
            if data_after:
                layer_data[(x, y)] = data_after
            elif (x, y) in layer_data:
                del layer_data[(x, y)]
            app._update_dirty_bbox(x, y)


class AddLayerAction(Action):

    def __init__(self, layer_obj, index, prev_active_index):
        self.layer_obj = layer_obj
        self.index = index
        self.prev_active_index = prev_active_index

    def undo(self, app):
        app.layers.pop(self.index)
        app.active_layer_index = self.prev_active_index

    def redo(self, app):
        app.layers.insert(self.index, self.layer_obj)
        app.active_layer_index = self.index


class DuplicateLayerAction(Action):

    def __init__(self, layer_obj, index, prev_active_index):
        self.layer_obj = layer_obj
        self.index = index
        self.prev_active_index = prev_active_index

    def undo(self, app):
        app.layers.pop(self.index)
        app.active_layer_index = self.prev_active_index
        app._force_full_redraw = True
        app._rescale_canvas()
        app._update_layers_ui()

    def redo(self, app):
        app.layers.insert(self.index, self.layer_obj)
        app.active_layer_index = self.index


class DeleteLayerAction(Action):

    def __init__(self, layer_obj, index, prev_active_index, new_active_index):
        self.layer_obj = layer_obj
        self.index = index
        self.prev_active_index = prev_active_index
        self.new_active_index = new_active_index

    def undo(self, app):
        app.layers.insert(self.index, self.layer_obj)
        app.active_layer_index = self.prev_active_index

    def redo(self, app):
        app.layers.pop(self.index)
        app.active_layer_index = self.new_active_index


class MoveLayerAction(Action):

    def __init__(self, from_index, to_index, active_index_after):
        self.from_index = from_index
        self.to_index = to_index
        self.active_index_after = active_index_after

    def undo(self, app):
        layer = app.layers.pop(self.to_index)
        app.layers.insert(self.from_index, layer)
        app.active_layer_index = self.from_index

    def redo(self, app):
        layer = app.layers.pop(self.from_index)
        app.layers.insert(self.to_index, layer)
        app.active_layer_index = self.active_index_after


class RenameLayerAction(Action):

    def __init__(self, layer_index, old_name, new_name):
        self.layer_index = layer_index
        self.old_name = old_name
        self.new_name = new_name

    def undo(self, app):
        app.layers[self.layer_index].name = self.old_name

    def redo(self, app):
        app.layers[self.layer_index].name = self.new_name


class MergeLayerAction(Action):

    def __init__(self, upper_layer_obj, lower_layer_obj, upper_layer_index):
        self.upper_layer_obj = upper_layer_obj
        self.lower_layer_obj = lower_layer_obj
        self.upper_layer_index = upper_layer_index

    def undo(self, app):
        app.layers.pop(self.upper_layer_index - 1)
        app.layers.insert(self.upper_layer_index - 1, self.lower_layer_obj)
        app.layers.insert(self.upper_layer_index, self.upper_layer_obj)
        app.active_layer_index = self.upper_layer_index

    def redo(self, app):
        upper = app.layers[self.upper_layer_index]
        lower = app.layers[self.upper_layer_index - 1]

        merged_data = lower.pixel_data.copy()
        for (x, y), (upper_hex, upper_alpha) in upper.pixel_data.items():
            if upper_alpha == 0:
                continue

            original_pixel = merged_data.get((x, y))
            final_hex, final_alpha = upper_hex, upper_alpha

            if (
                app.color_blending_var.get()
                and 0 < upper_alpha < 255
                and original_pixel
                and original_pixel[1] > 0
            ):
                bg_hex, bg_a_int = original_pixel
                fg_r, fg_g, fg_b = app._hex_to_rgb(upper_hex)
                bg_r, bg_g, bg_b = app._hex_to_rgb(bg_hex)

                fa, ba = upper_alpha / 255.0, bg_a_int / 255.0
                out_a_norm = fa + ba * (1.0 - fa)

                if out_a_norm > 0:
                    final_alpha = min(255, int(round(out_a_norm * 255.0)))
                    r = min(
                        255,
                        max(
                            0,
                            int(round((fg_r * fa + bg_r * ba * (1 - fa)) / out_a_norm)),
                        ),
                    )
                    g = min(
                        255,
                        max(
                            0,
                            int(round((fg_g * fa + bg_g * ba * (1 - fa)) / out_a_norm)),
                        ),
                    )
                    b = min(
                        255,
                        max(
                            0,
                            int(round((fg_b * fa + bg_b * ba * (1 - fa)) / out_a_norm)),
                        ),
                    )
                    final_hex = app._rgb_to_hex(r, g, b)
                else:
                    final_alpha = 0

            if final_alpha > 0:
                merged_data[(x, y)] = (final_hex, final_alpha)
            elif (x, y) in merged_data:
                del merged_data[(x, y)]

        lower.pixel_data = merged_data
        app.layers.pop(self.upper_layer_index)
        app.active_layer_index = self.upper_layer_index - 1
