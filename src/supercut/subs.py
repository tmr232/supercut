import pysubs2


def format_event(event: pysubs2.SSAEvent) -> str:
    text = event.plaintext.replace("\n", " ").replace("  ", " ")
    return f"{event.name}: {text}"
