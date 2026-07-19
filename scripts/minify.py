#!/usr/bin/env python3
"""Conservative, deterministic CSS/JS minifiers for the build's generated
output (docs/assets/), using small hand-written scanners rather than a
third-party tool or a fragile regex pass.

Design goals, in order:

1. Never change semantics. The scanners tokenise strings, template
   literals, regex literals (JS) and url()/comments (CSS) and never touch
   their contents. Whitespace is only ever *collapsed to a single
   separator*, never removed in a way that could merge two tokens — for
   JS a whitespace run that contained a newline collapses to a single
   newline, so Automatic Semicolon Insertion is preserved exactly.
2. Deterministic: the same input always produces the same bytes (the
   repository's reproducible-build guarantee).
3. No dependencies, no network: pure Python standard library, so the
   build stays `python3 scripts/build.py` with no Node/npm step.
4. Editable source stays readable: only the *generated* copies under
   docs/assets/ are minified; assets/ keeps the fully commented source.

The savings come from removing comments and indentation (the bulk of
these well-commented modules) — gzip on the host handles the rest. The
minified output is exercised end to end by every Playwright suite, so a
semantic regression fails the browser tests loudly.

A comment beginning ``/*!`` is preserved verbatim (the conventional
"keep this — it's a licence/banner" marker)."""

_JS_WORD = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_$")

# Keywords after which a `/` begins a regex literal rather than division.
_REGEX_PRECEDING_KEYWORDS = {
    "return", "typeof", "instanceof", "in", "of", "new", "delete", "void",
    "do", "else", "case", "yield", "await", "throw",
}
# Punctuators after which a `/` begins a regex literal.
_REGEX_PRECEDING_PUNCT = set("(,=:[!&|?{};+-*/%<>^~")


def _last_word(chars):
    """The trailing identifier word already emitted (for regex/division
    disambiguation after a keyword)."""
    i = len(chars)
    while i > 0 and chars[i - 1] in _JS_WORD:
        i -= 1
    return "".join(chars[i:])


def minify_js(src):
    out = []              # list of emitted chunks (chars or whole tokens)
    i, n = 0, len(src)
    pending = ""          # "" | " " | "\n": whitespace seen since last token
    last_sig = ""         # last significant (non-whitespace) char emitted
    sig_chars = []        # significant chars only, for keyword lookback

    def emit(chunk):
        nonlocal last_sig, pending
        if pending and out:
            out.append(pending)
        pending = ""
        out.append(chunk)
        last_sig = chunk[-1]
        sig_chars.extend(chunk)

    while i < n:
        c = src[i]

        # --- whitespace: collapse, remembering whether a newline occurred
        if c in " \t\r\f\v":
            if pending != "\n":
                pending = " "
            i += 1
            continue
        if c == "\n":
            pending = "\n"
            i += 1
            continue

        # --- comments (a comment is whitespace-equivalent; /*! is kept)
        if c == "/" and i + 1 < n and src[i + 1] == "/":
            j = src.find("\n", i)
            i = n if j == -1 else j
            continue
        if c == "/" and i + 1 < n and src[i + 1] == "*":
            end = src.find("*/", i + 2)
            stop = n if end == -1 else end + 2
            block = src[i:stop]
            if block.startswith("/*!"):
                if pending and out:
                    out.append(pending)
                pending = ""
                out.append(block)
                # a licence banner does not influence regex/division of a
                # following token; leave last_sig unchanged.
            i = stop
            continue

        # --- strings
        if c == '"' or c == "'":
            j = i + 1
            while j < n:
                if src[j] == "\\":
                    j += 2
                    continue
                if src[j] == c:
                    break
                j += 1
            emit(src[i:j + 1])
            i = j + 1
            continue

        # --- template literals (handle nested ${ ... }); modules don't use
        # them today, but supporting them keeps the minifier safe if added.
        if c == "`":
            j = i + 1
            depth = 0
            while j < n:
                ch = src[j]
                if ch == "\\":
                    j += 2
                    continue
                if depth == 0 and ch == "`":
                    break
                if ch == "$" and j + 1 < n and src[j + 1] == "{":
                    depth += 1
                    j += 2
                    continue
                if depth > 0 and ch == "}":
                    depth -= 1
                j += 1
            emit(src[i:j + 1])
            i = j + 1
            continue

        # --- regex literal vs division
        if c == "/":
            is_regex = False
            if last_sig == "" or last_sig in _REGEX_PRECEDING_PUNCT:
                is_regex = True
            elif last_sig in _JS_WORD:
                if _last_word(sig_chars) in _REGEX_PRECEDING_KEYWORDS:
                    is_regex = True
            if is_regex:
                j = i + 1
                in_class = False
                while j < n:
                    ch = src[j]
                    if ch == "\\":
                        j += 2
                        continue
                    if ch == "[":
                        in_class = True
                    elif ch == "]":
                        in_class = False
                    elif ch == "/" and not in_class:
                        break
                    elif ch == "\n":
                        break  # unterminated; bail out safely
                    j += 1
                # include trailing flags
                k = j + 1
                while k < n and src[k] in _JS_WORD:
                    k += 1
                emit(src[i:k])
                i = k
                continue

        # --- ordinary character
        emit(c)
        i += 1

    return "".join(out).strip() + "\n"


# CSS structural delimiters around which surrounding whitespace is always
# safe to drop (they never appear as bare tokens needing separation).
_CSS_DROP_AROUND = set("{};,")


def minify_css(src):
    out = []
    i, n = 0, len(src)
    pending = False  # whitespace seen since last emitted token char

    while i < n:
        c = src[i]

        if c in " \t\r\n\f\v":
            pending = True
            i += 1
            continue

        # comments (keep /*! ... */)
        if c == "/" and i + 1 < n and src[i + 1] == "*":
            end = src.find("*/", i + 2)
            stop = n if end == -1 else end + 2
            block = src[i:stop]
            if block.startswith("/*!"):
                if pending and out and out[-1] not in _CSS_DROP_AROUND:
                    out.append(" ")
                out.append(block)
                pending = False
            else:
                pending = True  # a comment acts as whitespace
            i = stop
            continue

        # strings
        if c == '"' or c == "'":
            j = i + 1
            while j < n:
                if src[j] == "\\":
                    j += 2
                    continue
                if src[j] == c:
                    break
                j += 1
            if pending and out and out[-1] not in _CSS_DROP_AROUND:
                out.append(" ")
            out.append(src[i:j + 1])
            pending = False
            i = j + 1
            continue

        # url( ... ) — may hold an unquoted value with no whitespace of its
        # own; preserve everything up to the matching ) verbatim.
        if (c in "uU") and src[i:i + 4].lower() == "url(":
            end = src.find(")", i)
            stop = n if end == -1 else end + 1
            if pending and out and out[-1] not in _CSS_DROP_AROUND:
                out.append(" ")
            # Normalise only the outer url(...) token's internal edge
            # whitespace conservatively: keep the value exactly.
            out.append(src[i:stop])
            pending = False
            i = stop
            continue

        # ordinary character: emit a single separating space only when the
        # previous and current tokens both need it (neither side is a
        # structural delimiter around which space is redundant).
        if pending:
            if out and out[-1] not in _CSS_DROP_AROUND and c not in _CSS_DROP_AROUND:
                out.append(" ")
            pending = False
        out.append(c)
        i += 1

    return "".join(out).strip() + "\n"
