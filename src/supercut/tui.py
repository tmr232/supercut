from typing import Type

from rich.console import RenderableType
from textual.app import App, ComposeResult, CSSPathType
from textual.driver import Driver
from textual.widgets import Header, Footer, Button, Static, Checkbox, ListView, ListItem
from textual.containers import ScrollableContainer
from textual.reactive import reactive
from textual.binding import Binding
class SubtitleDisplay(Static):
    pass
class Cut(Static):

    enabled = reactive(True)

    def __init__(self, text:str):
        super().__init__()
        self.text = text
    def compose(self) -> ComposeResult:
        yield SubtitleDisplay(self.text)

    def watch_enabled(self):
        if self.enabled:
            self.remove_class("disabled")
        else:
            self.add_class("disabled")

    def on_click(self)->None:
        self.enabled ^= True


class EditableListView(ListView):
    def move_up(self):
        if not self.index:
            # Nothing is highlighted, or the first item
            return

        prev = self.children[self.index-1]
        curr = self.children[self.index]

        self.move_child(curr, before=prev)
        self.index = self.index - 1

    def move_down(self):
        if self.index is None or self.index >= len(self)-1:
            # Nothing is highlighted, or the first item
            return

        curr = self.children[self.index]
        next = self.children[self.index+1]

        self.move_child(curr, after=next)
        self.index = self.index + 1


class SuercutApp(App):

    CSS_PATH = "Supercut.tcss"
    BINDINGS = [
        Binding(key="space", action="toggle_enabled", description="Enable/Disable"),
        Binding(key="ctrl+up", action="move_up", description="Move Up"),
        Binding(key="ctrl+down", action="move_down", description="Move Down"),
    ]

    def __init__(self, driver_class: Type[Driver] | None = None, css_path: CSSPathType | None = None,
                 watch_css: bool = False):
        super().__init__(driver_class, css_path, watch_css)

        self.lines = [str(i) for i in range(100)]

    def compose(self)->ComposeResult:
        yield Header()
        yield Footer()
        list_view = EditableListView()
        list_view.extend(ListItem(Cut(l)) for l in self.lines)
        print(len(list_view))
        yield list_view
        # list_view.focus()

    def action_toggle_enabled(self):
        self.query_one(ListView).highlighted_child.query_one(Cut).enabled ^= True

    def action_move_up(self):
        list_view = self.query_one(EditableListView)
        list_view.move_up()
    def action_move_down(self):
        list_view = self.query_one(EditableListView)
        list_view.move_down()


app = SuercutApp()
if __name__ == "__main__":
    app.run()