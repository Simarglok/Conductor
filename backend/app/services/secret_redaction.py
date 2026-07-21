"""Conservative text redaction for lifecycle logs, errors, and audit metadata."""

from __future__ import annotations

import re
from re import Match


REDACTED = "[REDACTED]"

_EXACT_SECRET_KEYS = frozenset(
    {
        "PASSWORD",
        "PASSWD",
        "PWD",
        "SECRET",
        "SECRET_KEY",
        "CLIENT_SECRET",
        "API_KEY",
        "APIKEY",
        "ACCESS_TOKEN",
        "AUTH_TOKEN",
        "REFRESH_TOKEN",
        "TOKEN",
        "FERNET_KEY",
        "GIT_TOKEN",
        "GITHUB_TOKEN",
        "GITLAB_TOKEN",
        "DATABASE_URL",
        "DB_URL",
        "CONNECTION_STRING",
        "CREDENTIAL",
        "CREDENTIALS",
    }
)
_SECRET_SEGMENT_SEQUENCES = (
    ("PASSWORD",),
    ("PASSWD",),
    ("PWD",),
    ("SECRET",),
    ("TOKEN",),
    ("APIKEY",),
    ("CREDENTIAL",),
    ("CREDENTIALS",),
    ("API", "KEY"),
    ("FERNET", "KEY"),
    ("PRIVATE", "KEY"),
    ("DATABASE", "URL"),
    ("DB", "URL"),
    ("CONNECTION", "STRING"),
)
_PRIVATE_KEY_LABELS = frozenset(
    {
        "PRIVATE KEY",
        "RSA PRIVATE KEY",
        "EC PRIVATE KEY",
        "DSA PRIVATE KEY",
        "OPENSSH PRIVATE KEY",
        "ENCRYPTED PRIVATE KEY",
    }
)
_PRIVATE_KEY_BEGIN = "-----BEGIN "
_PRIVATE_KEY_MARKER_END = "-----"
_BEARER_TOKEN = re.compile(r"(?i)\b(Bearer)\s+[A-Za-z0-9._~+/=-]{8,}")
_FERNET_TOKEN = re.compile(r"\bgAAAAA[A-Za-z0-9_-]{10,}={0,2}\b")
_GIT_TOKEN = re.compile(
    r"\b(?:github_pat_[A-Za-z0-9_]{10,}|gh[pousr]_[A-Za-z0-9]{20,}|"
    r"glpat-[A-Za-z0-9_-]{10,}|gloas-[A-Za-z0-9_-]{10,}|"
    r"glrt-[A-Za-z0-9_-]{10,}|xox(?:a|b|p|r|s)-[A-Za-z0-9-]{10,})\b"
)
_URL_WITH_AUTHORITY = re.compile(
    r"(?i)\b(?P<scheme>[a-z][a-z0-9+.-]*://)(?P<authority>[^\s/?#]+)"
)


def _redact_url_authority(match: Match[str]) -> str:
    authority = match.group("authority")
    userinfo, separator, host = authority.rpartition("@")
    if not separator or not userinfo or not host:
        return match.group(0)
    return f'{match.group("scheme")}{REDACTED}@{host}'


def _private_key_header_end(value: str, label_start: int) -> tuple[int | None, int]:
    """Find a same-line marker end without stepping over another BEGIN marker."""

    index = label_start
    while index < len(value):
        if value.startswith(_PRIVATE_KEY_BEGIN, index):
            return None, index
        if value.startswith(_PRIVATE_KEY_MARKER_END, index):
            return index, index + len(_PRIVATE_KEY_MARKER_END)
        if value[index] in "\r\n" or (
            value[index] == "\\"
            and index + 1 < len(value)
            and value[index + 1] in "rn"
        ):
            return None, index
        index += 1
    return None, len(value)


def _redact_private_key_blocks(value: str) -> str:
    """Redact matching key blocks in one forward scan, including unmatched begins."""

    output: list[str] = []
    cursor = 0
    while True:
        begin = value.find(_PRIVATE_KEY_BEGIN, cursor)
        if begin == -1:
            output.append(value[cursor:])
            return "".join(output)

        label_start = begin + len(_PRIVATE_KEY_BEGIN)
        header_end, rejected_end = _private_key_header_end(value, label_start)
        if header_end is None:
            output.append(value[cursor:rejected_end])
            cursor = rejected_end
            continue

        label = value[label_start:header_end]
        if label not in _PRIVATE_KEY_LABELS:
            next_cursor = header_end + len(_PRIVATE_KEY_MARKER_END)
            output.append(value[cursor:next_cursor])
            cursor = next_cursor
            continue

        output.append(value[cursor:begin])
        output.append(REDACTED)
        footer = f"-----END {label}-----"
        footer_start = value.find(footer, header_end + len(_PRIVATE_KEY_MARKER_END))
        if footer_start == -1:
            return "".join(output)
        cursor = footer_start + len(footer)


def _is_secret_key(key: str) -> bool:
    """Classify structured and ENV names by complete underscore-delimited segments."""

    normalized = key.upper()
    if normalized in _EXACT_SECRET_KEYS:
        return True

    segments = normalized.split("_")
    for marker in _SECRET_SEGMENT_SEQUENCES:
        marker_length = len(marker)
        if any(
            tuple(segments[index : index + marker_length]) == marker
            for index in range(len(segments) - marker_length + 1)
        ):
            return True
    return False


def _is_key_start(character: str) -> bool:
    return character.isalpha() or character == "_"


def _is_key_character(character: str) -> bool:
    return character.isalnum() or character == "_"


def _quoted_value_end(value: str, quote_start: int) -> int | None:
    quote = value[quote_start]
    index = quote_start + 1
    while index < len(value):
        character = value[index]
        if character == "\\" and quote == '"':
            index = min(index + 2, len(value))
            continue
        if character == quote:
            if quote == "'" and index + 1 < len(value) and value[index + 1] == "'":
                index += 2
                continue
            return index + 1
        index += 1
    return None


def _line_value_end(value: str, value_start: int) -> int:
    line_end = len(value)
    for newline in ("\r", "\n"):
        found = value.find(newline, value_start)
        if found != -1:
            line_end = min(line_end, found)

    comment_start: int | None = None
    index = value_start
    while index < line_end:
        if value[index] == "#" and index > value_start and value[index - 1] in " \t":
            comment_start = index
            break
        index += 1

    end = comment_start if comment_start is not None else line_end
    while end > value_start and value[end - 1] in " \t":
        end -= 1
    return end


def _is_block_scalar_indicator(value: str, start: int, end: int) -> bool:
    indicator = value[start:end]
    if not indicator or indicator[0] not in "|>" or len(indicator) > 3:
        return False

    modifiers = indicator[1:]
    if not modifiers:
        return True
    if len(modifiers) == 1:
        return modifiers in "+-" or modifiers in "123456789"
    return (
        modifiers[0] in "+-"
        and modifiers[1] in "123456789"
        or modifiers[0] in "123456789"
        and modifiers[1] in "+-"
    )


def _next_line_break(value: str, start: int) -> tuple[int, int]:
    index = start
    while index < len(value) and value[index] not in "\r\n":
        index += 1
    if index == len(value):
        return index, index
    if value[index] == "\r" and index + 1 < len(value) and value[index + 1] == "\n":
        return index, index + 2
    return index, index + 1


def _block_scalar_end(value: str, value_start: int, key_start: int) -> int | None:
    indicator_end = _line_value_end(value, value_start)
    if not _is_block_scalar_indicator(value, value_start, indicator_end):
        return None

    header_break_start, line_start = _next_line_break(value, value_start)
    if line_start == header_break_start:
        return len(value)

    line_begin = value.rfind("\n", 0, key_start) + 1
    carriage_return = value.rfind("\r", 0, key_start)
    line_begin = max(line_begin, carriage_return + 1)
    key_indent = key_start - line_begin
    preceding_break_start = header_break_start

    while line_start < len(value):
        line_break_start, next_line_start = _next_line_break(value, line_start)
        first_content = line_start
        while first_content < line_break_start and value[first_content] in " \t":
            first_content += 1

        if first_content < line_break_start and first_content - line_start <= key_indent:
            return preceding_break_start
        if next_line_start == line_break_start:
            return len(value)

        preceding_break_start = line_break_start
        line_start = next_line_start

    return len(value)


def _flow_value_end(value: str, value_start: int) -> int:
    if value.startswith(REDACTED, value_start):
        return value_start + len(REDACTED)

    index = value_start
    delimiters: list[str] = []
    quote: str | None = None
    while index < len(value):
        character = value[index]

        if quote is not None:
            if character == "\\" and quote == '"':
                index = min(index + 2, len(value))
                continue
            if character == quote:
                if quote == "'" and index + 1 < len(value) and value[index + 1] == "'":
                    index += 2
                    continue
                quote = None
            index += 1
            continue

        if character in "\"'":
            quote = character
            index += 1
            continue
        if character in "[{":
            delimiters.append(character)
            index += 1
            continue
        if character in "]}":
            if not delimiters:
                break
            delimiters.pop()
            index += 1
            continue
        if character == "," and not delimiters:
            break
        if character == "#" and index > value_start and value[index - 1] in " \t":
            if not delimiters:
                break
            _, index = _next_line_break(value, index)
            continue
        if character in "\r\n" and not delimiters:
            break
        index += 1

    while index > value_start and value[index - 1] in " \t":
        index -= 1
    return index


def _inline_value_end(value: str, value_start: int) -> int:
    if value.startswith(REDACTED, value_start):
        return value_start + len(REDACTED)

    index = value_start
    while index < len(value) and value[index] not in "\"'&,# \t}]\r\n":
        index += 1
    return index


def _redact_assignments(value: str) -> str:
    """Redact structured, ENV, and query assignments with one forward scan."""

    output: list[str] = []
    unchanged_start = 0
    index = 0
    line_prefix_stage = "start"
    length = len(value)

    while index < length:
        if value[index] in "\r\n":
            line_prefix_stage = "start"
            index += 1
            continue
        if value[index] in " \t":
            index += 1
            continue
        if value[index] == "-" and line_prefix_stage == "start":
            line_prefix_stage = "dash"
            index += 1
            continue

        line_key_position = line_prefix_stage in {"start", "dash", "export"}
        key_start = index
        key_quote = ""
        if value[index] in "\"'":
            key_quote = value[index]
            key_content_start = index + 1
            if key_content_start >= length or not _is_key_start(value[key_content_start]):
                line_prefix_stage = "content"
                index += 1
                continue
            key_end = key_content_start + 1
            while key_end < length and _is_key_character(value[key_end]):
                key_end += 1
            if key_end >= length or value[key_end] != key_quote:
                line_prefix_stage = "content"
                index += 1
                continue
            key = value[key_content_start:key_end]
            delimiter_search = key_end + 1
        elif _is_key_start(value[index]) and (
            index == 0 or not _is_key_character(value[index - 1])
        ):
            key_end = index + 1
            while key_end < length and _is_key_character(value[key_end]):
                key_end += 1
            key = value[index:key_end]
            delimiter_search = key_end
        else:
            line_prefix_stage = "content"
            index += 1
            continue

        if (
            not key_quote
            and line_key_position
            and key == "export"
            and delimiter_search < length
            and value[delimiter_search] in " \t"
        ):
            line_prefix_stage = "export"
            index = delimiter_search
            continue

        line_prefix_stage = "content"

        if not _is_secret_key(key):
            index = delimiter_search
            continue

        while delimiter_search < length and value[delimiter_search] in " \t":
            delimiter_search += 1
        if delimiter_search >= length or value[delimiter_search] not in ":=":
            index = delimiter_search
            continue

        delimiter = value[delimiter_search]
        value_start = delimiter_search + 1
        while value_start < length and value[value_start] in " \t":
            value_start += 1
        if value_start >= length:
            break

        if value[value_start] in "\"'":
            value_end = _quoted_value_end(value, value_start)
            if value_end is None:
                value_end = length
                replacement = f"{value[value_start]}{REDACTED}"
                secret_value = value[value_start + 1 : value_end]
            else:
                replacement = f"{value[value_start]}{REDACTED}{value[value_end - 1]}"
                secret_value = value[value_start + 1 : value_end - 1]
        else:
            is_line_mapping = delimiter == ":" and line_key_position
            is_env_assignment = (
                delimiter == "=" and key == key.upper() and line_key_position
            )
            if is_line_mapping:
                block_scalar_end = _block_scalar_end(value, value_start, key_start)
                value_end = (
                    block_scalar_end
                    if block_scalar_end is not None
                    else _line_value_end(value, value_start)
                )
            elif is_env_assignment:
                value_end = _line_value_end(value, value_start)
            elif delimiter == ":":
                value_end = _flow_value_end(value, value_start)
            else:
                value_end = _inline_value_end(value, value_start)
            replacement = REDACTED
            secret_value = value[value_start:value_end]

        if not secret_value or secret_value == REDACTED:
            index = max(value_end, value_start + 1)
            continue

        output.append(value[unchanged_start:value_start])
        output.append(replacement)
        unchanged_start = value_end
        index = value_end

    output.append(value[unchanged_start:])
    return "".join(output)


def redact_secret_text(value: str) -> str:
    """Remove common credential forms while preserving useful non-secret context."""

    redacted = _redact_private_key_blocks(value)
    redacted = _BEARER_TOKEN.sub(lambda match: f"{match.group(1)} {REDACTED}", redacted)
    redacted = _FERNET_TOKEN.sub(REDACTED, redacted)
    redacted = _GIT_TOKEN.sub(REDACTED, redacted)
    redacted = _URL_WITH_AUTHORITY.sub(_redact_url_authority, redacted)
    return _redact_assignments(redacted)
