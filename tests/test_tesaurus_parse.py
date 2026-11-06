"""
Regression tests for the Tesaurus Tematis parser.

Run from the repository root with ``python -m tests.test_tesaurus_parse`` (no
pytest needed); the tests are also compatible with pytest collection.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from pathlib import Path

from naotimes.http.tesaurus import TesaurusGalat, parse_entri

_FIXTURE = Path(__file__).parent / "fixtures" / "tesaurus_makan.html"


def _fixture() -> str:
    return _FIXTURE.read_text(encoding="utf-8")


def _assert_raises(exc_type: type[BaseException], callback: Callable[[], object]) -> BaseException:
    try:
        _ = callback()
    except exc_type as exc:
        return exc
    raise AssertionError(f"{exc_type.__name__} was not raised")


def test_fixture_uses_the_broken_comment_terminator():
    # The live page closes its analytics comment with "--!>" (a valid HTML5
    # comment terminator that Python's html.parser does not understand).
    # Keeping it in the fixture is what makes these tests meaningful.
    assert "--!>" in _fixture()


def test_parse_entri_splits_word_classes():
    entri = parse_entri(_fixture())

    assert [kelas.kelas_kata for kelas in entri] == ["nomina", "verba"]

    nomina, verba = entri
    assert len(nomina.entri) == 1
    assert nomina.entri[0].label == "makanan"
    assert nomina.entri[0].sublabel == "makanan"
    assert nomina.entri[0].lema == ["pangan", "santapan"]

    assert len(verba.entri) == 1
    assert verba.entri[0].label == "tindakan"
    assert verba.entri[0].sublabel == "menyantap"
    assert verba.entri[0].lema == ["makan", "menyantap"]


def test_parse_entri_falls_back_to_requested_word_class():
    # Word-class filtered pages (e.g. /tematis/lema/makan/verba) have no
    # result-postag markers at all, so the requested class must be reused.
    html = re.sub(r'<div class="result-postag">.*?</div>\s*', "", _fixture())

    entri = parse_entri(html, "verba")

    assert len(entri) == 1
    assert entri[0].kelas_kata == "verba"
    assert [lema.label for lema in entri[0].entri] == ["makanan", "tindakan"]


def test_parse_entri_requires_result_container():
    html = '<html><body><div class="container"></div></body></html>'

    exc = _assert_raises(TesaurusGalat, lambda: parse_entri(html))

    assert "div.contain" in str(exc)


if __name__ == "__main__":
    tests = (
        test_fixture_uses_the_broken_comment_terminator,
        test_parse_entri_splits_word_classes,
        test_parse_entri_falls_back_to_requested_word_class,
        test_parse_entri_requires_result_container,
    )
    for test in tests:
        test()
        print(f"PASS {test.__name__}")
    print(f"\n{len(tests)} test(s) passed")
