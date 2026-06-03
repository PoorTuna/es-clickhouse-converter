"""Column codec selection.

Width handles correctness; codecs handle storage. ``T64`` truncates integers to
their used bit-width at write time, so an ``Int64`` of small values costs about
what a ``UInt16`` would - which is why we default safe-wide and let the codec
reclaim the bytes instead of guessing narrow types.
"""

from ._type_map import is_datetime, is_integer

_INT_CODEC = "T64, ZSTD(1)"
_DATETIME_CODEC = "DoubleDelta, ZSTD(1)"
_COUNTER_CODEC = "Delta, ZSTD(1)"
_DEFAULT_CODEC = "ZSTD(1)"


def default_codec(base_ch_type: str, *, is_counter: bool = False) -> str:
    """Codec for an unwrapped (non-Nullable) base type."""
    if is_counter:
        return _COUNTER_CODEC
    if is_integer(base_ch_type):
        return _INT_CODEC
    if is_datetime(base_ch_type):
        return _DATETIME_CODEC
    return _DEFAULT_CODEC
