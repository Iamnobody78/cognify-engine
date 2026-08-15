"""Tool-name normalization — single source of truth (TASK-REAL-010).

Extracted from src/main.py (was _norm_tool_name / _CONFUSABLE_MAP) so the
tool-lethality table (src/lethality.py), the OpenAI chat path and any future
consumer share ONE pipeline: NFKC -> confusable map -> casefold.
"""

import unicodedata as _unicodedata

# Homoglyph confusables: characters that LOOK like ASCII but are NOT folded
# by NFKC/casefold (Greek iota vs Latin i, Cyrillic lookalikes, Roman
# numerals). Reviewer finding R2: 'delete_fιle' (U+03B9) passes an
# exact-match blacklist and is NOT caught by NFKC alone — casefold keeps
# it as U+03B9. This map is the deliberate, documented defense-in-depth.
CONFUSABLE_MAP = str.maketrans({
    # Greek iota lookalikes -> i
    "\u03b9": "i", "\u0399": "i", "\u03ca": "i", "\u03aa": "i",
    # Cyrillic lookalikes (a, e, o, p, c, i, b)
    "\u0430": "a", "\u0435": "e", "\u043e": "o", "\u0440": "p",
    "\u0441": "c", "\u0456": "i", "\u0406": "i",
    # Roman numerals I/i
    "\u2160": "i", "\u2170": "i",
})


def norm_tool_name(name) -> str:
    """Normalize a tool name for comparison.

    Pipeline: NFKC (compat decomposition, folds fullwidth forms) ->
    confusable map (homoglyph lookalikes) -> casefold (case variants).
    Agent frameworks normalize before tool lookup, so every consumer must
    match — otherwise 'Delete_File', 'delete＿file' (fullwidth U+FF3F) or
    'delete_fιle' (U+03B9) slip past name-based checks.
    """
    if not isinstance(name, str):
        return ""
    return (
        _unicodedata.normalize("NFKC", name)
        .translate(CONFUSABLE_MAP)
        .casefold()
    )
