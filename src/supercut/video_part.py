from pathlib import Path

import attrs


@attrs.frozen
class VideoPart:
    video: Path
    subs: str
    start: int
    end: int

    @property
    def duration_ms(self):
        return self.end - self.start

    @property
    def duration_us(self):
        return self.duration_ms * 1000
