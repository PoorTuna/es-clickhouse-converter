"""Internal field model produced by parsing an Elasticsearch ``_mapping``.

Pure data containers - no project imports, no I/O, no ClickHouse knowledge.
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
class JsonRoot:
    """An open-ended ES subtree that becomes a ClickHouse ``JSON`` column.

    Triggered by ``dynamic: true``/``runtime`` or ``enabled: false``. ``path``
    is the dotted path to the object (e.g. ``labels``); ``fields`` are any
    leaves ES still declared under it explicitly. Those render as typed path
    hints inside ``JSON(...)`` while the column stays open to new dynamic paths.
    """

    path: str
    fields: tuple[EsField, ...] = ()


@dataclass(frozen=True, slots=True)
class NestedGroup:
    """An ES ``type: nested`` subtree: a fixed-schema array of sub-documents.

    ``path`` is the dotted path to the nested field (e.g. ``tags``); ``fields``
    are its scalar leaves, each carrying its full dotted path (``tags.key``).
    The DDL layer renders this as a ClickHouse ``Nested(...)`` column so the
    per-element correlation ES guarantees survives the conversion.
    """

    path: str
    fields: tuple[EsField, ...]


@dataclass(frozen=True, slots=True)
class MappingModel:
    """Parsed mapping: typed fields plus everything dynamic about the index.

    ``json_roots`` are subtrees ES declares open-ended (``dynamic: true``,
    ``runtime``, or ``enabled: false``); each becomes a ClickHouse ``JSON``
    column, carrying any explicitly declared leaves as typed path hints.
    ``nested_groups`` are ``type: nested`` subtrees rendered as
    ``Nested(...)`` columns. ``root_dynamic`` is the top-level ``dynamic``
    setting verbatim (``None`` when unset, where ES defaults to dynamic), and
    ``has_dynamic_templates`` flags ``dynamic_templates`` rules. The DDL layer
    turns these into a catch-all column or a suggestion.
    """

    fields: tuple[EsField, ...]
    json_roots: tuple[JsonRoot, ...] = ()
    nested_groups: tuple[NestedGroup, ...] = ()
    runtime_fields: tuple[str, ...] = ()
    root_dynamic: str | None = None
    has_dynamic_templates: bool = False
