"""Shared strict JSON loading for the project's structured data files.

Every JSON input the build reads (data/*.json, scripts/sitemap.json)
goes through load_json_data(), so all loaders behave the same way:

  required file:  missing, malformed, duplicate-keyed, or wrong-top-level-
                  type files are all build errors.
  optional file:  only a *missing* file is acceptable; a file that exists
                  but is malformed, contains a duplicate key, or has the
                  wrong top-level type is always a build error — it is
                  never silently replaced with {} or any other fallback.

Errors are returned as (file, rule, message, fix) tuples — the same shape
scripts/build.py's Errors collector uses — with the JSON syntax line and
column, the duplicated key name, or the expected top-level type included,
so the failure is actionable. At most one error is produced per file, so
ordering is trivially deterministic. Stdlib only; not a JSON Schema
implementation — field-level validation stays in readable Python in the
individual loaders.
"""
import json


class _DuplicateKey(ValueError):
    def __init__(self, key):
        super().__init__(f'duplicate key "{key}"')
        self.key = key


def _reject_duplicate_keys(pairs):
    seen = {}
    for key, value in pairs:
        if key in seen:
            raise _DuplicateKey(key)
        seen[key] = value
    return seen


_TYPE_NAMES = {dict: "object", list: "array", str: "string", int: "number",
               float: "number", bool: "boolean", type(None): "null"}


def load_json_data(path, rel, *, required=True, expect_type=dict):
    """Load one structured JSON file strictly.

    path:        pathlib.Path to read.
    rel:         repository-relative path string used in error messages.
    required:    if False, a missing file returns (None, []) — every
                 other problem is still an error.
    expect_type: required top-level Python type (dict or list).

    Returns (data, errors) where errors is a list of
    (file, rule, message, fix) tuples; data is None whenever errors is
    non-empty or an optional file is missing.
    """
    expected_name = _TYPE_NAMES[expect_type]
    if not path.exists():
        if not required:
            return None, []
        return None, [(rel, "json-file-missing",
                       f"Required data file {rel} does not exist.",
                       f"Create {rel} (see the README for its format), or restore it "
                       "from version control.")]
    raw = path.read_text(encoding="utf-8")
    try:
        data = json.loads(raw, object_pairs_hook=_reject_duplicate_keys)
    except _DuplicateKey as exc:
        return None, [(rel, "json-duplicate-key",
                       f'Duplicate key "{exc.key}" — the same name appears twice in one '
                       "object, so one of the two values would be silently lost.",
                       f'Remove or rename one of the "{exc.key}" entries so every key '
                       "in the object is unique.")]
    except json.JSONDecodeError as exc:
        return None, [(rel, "json-syntax-error",
                       f"Not valid JSON: {exc.msg} at line {exc.lineno}, column {exc.colno}.",
                       f"Fix the syntax error at line {exc.lineno}, column {exc.colno} "
                       f"of {rel} (a malformed file is never silently ignored or "
                       "replaced with a fallback value).")]
    if not isinstance(data, expect_type):
        return None, [(rel, "json-wrong-top-level-type",
                       f"The top-level JSON value is a {_TYPE_NAMES.get(type(data), type(data).__name__)}, "
                       f"but this file must be a JSON {expected_name}.",
                       f"Make the file's top-level value a JSON {expected_name}.")]
    return data, []
