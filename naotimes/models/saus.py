from typing import Any, Dict, List, Optional, Union

from naotimes.utils import AttributeDict

__all__ = ("SausResultItem", "SausResult", "SausMultiResult")


class SausResultItem(AttributeDict):
    title: str
    source: Optional[str]
    thumbnail: str
    indexer: str
    confidence: Union[float, int]
    extra_info: Optional[Dict[str, Any]]


class SausResult(AttributeDict):
    _total: int
    items: List[SausResultItem]


class SausMultiResult(AttributeDict):
    saucenao: SausResult
    iqdb: SausResult
