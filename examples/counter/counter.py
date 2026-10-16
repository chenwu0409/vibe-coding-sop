"""Count non-empty lines; whitespace-only lines are empty."""


def count_nonempty(text):
    return sum(bool(line.strip()) for line in text.splitlines())
