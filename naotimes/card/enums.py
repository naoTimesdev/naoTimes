"""
MIT License

Copyright (c) 2019-2021 naoTimesdev

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
"""

from typing import Any, Dict, NamedTuple, Union, get_args, get_origin

from pyppeteer.page import Page

__all__ = ("CardBase", "CardTemplate", "CardTemplate", "CardGeneratorNav")


class _MissingSentinel:
    def __eq__(self, other):
        return False

    def __bool__(self):
        return False

    def __repr__(self):
        return "..."


class CardBase:
    def __init__(self, *args, **kwargs):
        self._factual_data: Dict[str, Any] = {}
        try:
            annotations = self.__annotations__
            annotate = list(annotations.copy().keys())
            mapping_final = {}
            for a, b in zip(annotate, args):
                mapping_final[a] = b
            for name, value in kwargs.items():
                if name in annotate:
                    mapping_final[name] = value
            for n, v in mapping_final.items():
                setattr(self, n, v)
                self._factual_data[n] = v
            for name, anno in annotations.items():
                x_ = getattr(self, name, _MissingSentinel)
                if name not in mapping_final:
                    if self.is_list(anno) and x_ is _MissingSentinel:
                        setattr(self, name, [])
                        self._factual_data[name] = []
                    elif self.is_optional(anno) and x_ is _MissingSentinel:
                        setattr(self, name, None)
                        self._factual_data[name] = None
                    elif not self.is_optional(anno) and x_ is _MissingSentinel:
                        raise TypeError(f"Missing required keyword argument: {name}")
        except AttributeError:
            pass

    def __repr__(self):
        cls_name = self.__class__.__name__
        _origin = []
        for k, v in self._factual_data.items():
            _origin.append(f"{k}={v!r}")
        return f"<{cls_name} {' '.join(_origin)}>"

    @staticmethod
    def is_optional(field):
        return get_origin(field) is Union and type(None) in get_args(field)

    @staticmethod
    def is_list(field):
        return get_origin(field) is list

    def serialize(self):
        """Serialize back the data into JSON format."""
        return self._factual_data


class CardTemplate(NamedTuple):
    name: str
    html: str
    max_width: int
    pad_height: int = 0


class CardGeneratorNav(NamedTuple):
    card: CardTemplate
    page: Page
