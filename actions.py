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

            app.pixel_canvas._update_dirty_bbox(x, y)

    def redo(self, app):
        layer_data = app.layers[self.layer_index].pixel_data
        for (x, y), data_after in self.pixels_after.items():
            if data_after:
                layer_data[(x, y)] = data_after
            elif (x, y) in layer_data:
                del layer_data[(x, y)]

            app.pixel_canvas._update_dirty_bbox(x, y)


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

    def __init__(self, from_index, to_index, active_index_before, active_index_after):
        self.from_index = from_index
        self.to_index = to_index
        self.active_index_before = active_index_before
        self.active_index_after = active_index_after

    def undo(self, app):

        layer = app.layers.pop(self.to_index)
        app.layers.insert(self.from_index, layer)
        app.active_layer_index = self.active_index_before
        app.pixel_canvas.force_redraw()
        app._update_layers_ui()

    def redo(self, app):
        layer = app.layers.pop(self.from_index)
        app.layers.insert(self.to_index, layer)
        app.active_layer_index = self.active_index_after
        app.pixel_canvas.force_redraw()
        app._update_layers_ui()


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

    def __init__(
        self,
        upper_layer_obj,
        lower_layer_obj,
        merged_lower_layer_obj,
        upper_layer_index,
    ):
        self.upper_layer_obj = upper_layer_obj
        self.lower_layer_obj = lower_layer_obj
        self.merged_lower_layer_obj = merged_lower_layer_obj
        self.upper_layer_index = upper_layer_index

    def undo(self, app):
        app.layers.pop(self.upper_layer_index - 1)
        app.layers.insert(self.upper_layer_index - 1, self.lower_layer_obj)
        app.layers.insert(self.upper_layer_index, self.upper_layer_obj)
        app.active_layer_index = self.upper_layer_index

    def redo(self, app):

        app.layers.pop(self.upper_layer_index)
        app.layers.pop(self.upper_layer_index - 1)
        app.layers.insert(self.upper_layer_index - 1, self.merged_lower_layer_obj)
        app.active_layer_index = self.upper_layer_index - 1
