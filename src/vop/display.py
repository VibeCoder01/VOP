"""Human-readable display values; stored measurements retain their precision."""
import math
import re


def duration(seconds):
    tenths = round(float(seconds) * 10)
    hours, rest = divmod(tenths, 36000)
    minutes, rest = divmod(rest, 600)
    return f"{hours:02d}:{minutes:02d}:{rest / 10:04.1f}"


def duration_input(value):
    """Accept H:M:S in forms and legacy numeric seconds from API clients."""
    value = str(value).strip()
    if ':' in value:
        if not re.fullmatch(r'\d+:[0-5]\d:[0-5]\d(?:\.\d+)?', value):
            raise ValueError('Enter a duration as hours:minutes:seconds, for example 00:01:30.')
        hours, minutes, seconds = map(float, value.split(':'))
        result = hours * 3600 + minutes * 60 + seconds
    else:
        result = float(value)
    if not math.isfinite(result) or result < 0:
        raise ValueError('Enter a nonnegative duration as hours:minutes:seconds.')
    return result


def answer_kind(kind):
    return 'Yes/No' if kind == 'binary' else str(kind).capitalize()
