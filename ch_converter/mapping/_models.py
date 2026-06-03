"""Internal field model produced by parsing an Elasticsearch ``_mapping``.

Pure data containers — no project imports, no I/O, no ClickHouse knowledge.
"""

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class EsField:
    """A single concrete leaf field declared in an ES mapping.

    ``path`` is the dotted path from the index root (e.g. ``service.name``).
    Multi-fields (a ``text`` field with a ``.keyword`` sub-field) collapse to
    one ``EsField`` rather than two columns.
    """

    path: str
    es_type: str
    indexed: bool = True
    doc_values: bool = True
    has_keyword_subfield: bool = False
    date_format: str | None = None
    null_value: Any = None


@dataclass(frozen=True, slots=True)
class MappingModel:
    """Parsed mapping: typed fields plus everything dynamic about the index.

    ``json_roots`` are subtree paths ES declares open-ended (``dynamic: true``,
    ``runtime``, or ``enabled: false``); each becomes a ClickHouse ``JSON``
    column. ``root_dynamic`` is the top-level ``dynamic`` setting verbatim
    (``None`` when unset, where ES defaults to dynamic), and
    ``has_dynamic_templates`` flags ``dynamic_templates`` rules. The DDL layer
    turns these into a catch-all column or a suggestion.
    """

    fields: tuple[EsField, ...]
    json_roots: tuple[str, ...] = ()
    runtime_fields: tuple[str, ...] = ()
    root_dynamic: str | None = None
    has_dynamic_templates: bool = False
