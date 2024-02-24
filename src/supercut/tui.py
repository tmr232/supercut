from textual.app import App, ComposeResult
from textual.widgets import Header, Footer, Button, Static, Checkbox, ListView
from textual.containers import ScrollableContainer
from textual.reactive import reactive
class SubtitleDisplay(Static):
    pass
class Cut(Static):

    enabled = reactive(True)
    def compose(self) -> ComposeResult:
        yield SubtitleDisplay("Must display something!")

    def watch_enabled(self):
        if self.enabled:
            self.remove_class("disabled")
        else:
            self.add_class("disabled")

    def on_click(self)->None:
        self.enabled ^= True
class SuercutApp(App):

    CSS_PATH = "Supercut.tcss"
    def compose(self)->ComposeResult:
        yield Header()
        yield Footer()
        yield ScrollableContainer(Cut(), Cut(), Cut())

if __name__ == "__main__":
    app = SuercutApp()
    app.run()