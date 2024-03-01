import subprocess

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.reactive import reactive
from textual.widgets import Footer, Header, ListItem, ListView, Static

from supercut import subs, vlc


class SubtitleDisplay(Static):
    pass


class Cut(Static):

    enabled = reactive(True)

    def __init__(self, text: str):
        super().__init__()
        self.text = text

    def compose(self) -> ComposeResult:
        yield SubtitleDisplay(self.text)

    def watch_enabled(self):
        if self.enabled:
            self.remove_class("disabled")
        else:
            self.add_class("disabled")

    def toggle(self) -> None:
        self.enabled ^= True


class EditableLineView(ListView):
    def __init__(self, lines: list[str]):
        super().__init__(*(ListItem(Cut(line)) for line in lines))

        self.indices = list(range(len(lines)))

    @property
    def state(self) -> list[tuple[int, bool]]:
        def _iter():
            for index, item in zip(self.indices, self.query(Cut).nodes):
                yield index, item.enabled

        return list(_iter())

    def move_up(self):
        if not self.index:
            # Nothing is highlighted, or the first item
            return

        prev = self.children[self.index - 1]
        curr = self.children[self.index]

        self.indices[self.index], self.indices[self.index - 1] = (
            self.indices[self.index - 1],
            self.indices[self.index],
        )

        self.move_child(curr, before=prev)
        self.index = self.index - 1

    def move_down(self):
        if self.index is None or self.index >= len(self) - 1:
            # Nothing is highlighted, or the first item
            return

        curr = self.children[self.index]
        next = self.children[self.index + 1]

        self.indices[self.index], self.indices[self.index + 1] = (
            self.indices[self.index + 1],
            self.indices[self.index],
        )

        self.move_child(curr, after=next)
        self.index = self.index + 1


class SupercutApp(App):

    CSS_PATH = "Supercut.tcss"
    BINDINGS = [
        Binding(key="space", action="toggle_enabled", description="Enable/Disable"),
        Binding(key="ctrl+up", action="move_up", description="Move Up"),
        Binding(key="ctrl+down", action="move_down", description="Move Down"),
        Binding(key="p", action="preview_one", description="Preview Selected"),
        Binding(key="ctrl+p", action="preview_all", description="Preview All"),
    ]

    def __init__(
        self,
        cuts: list,
    ):
        super().__init__()
        self.cuts = cuts
        self.lines = [
            f"{i:-4} | {subs.format_event(cut.event)}" for i, cut in enumerate(cuts)
        ]

    def compose(self) -> ComposeResult:
        yield Header()
        yield Footer()
        list_view = EditableLineView(self.lines)
        yield list_view

    def action_toggle_enabled(self):
        self.query_one(ListView).highlighted_child.query_one(Cut).toggle()

    def action_move_up(self):
        list_view = self.query_one(EditableLineView)
        list_view.move_up()

    def action_move_down(self):
        list_view = self.query_one(EditableLineView)
        list_view.move_down()

    def action_preview_all(self):
        list_view = self.query_one(EditableLineView)

        cuts = [self.cuts[index] for index, enabled in list_view.state if enabled]
        vlc_clips = []
        for cut in cuts:
            vlc_clips.append(cut.to_vlc())
        playlist = vlc.make_playlist(vlc_clips)
        vlc.view_playlist(playlist)

    def action_preview_one(self):
        list_view = self.query_one(EditableLineView)

        cut = self.cuts[list_view.state[list_view.index][0]]

        playlist = vlc.make_playlist([cut.to_vlc()])
        vlc.view_playlist(playlist)

