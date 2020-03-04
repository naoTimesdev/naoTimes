#!/usr/bin/python3
# -*- coding: utf-8 -*-

from .showtimes_helper import naoTimesDB
from .romkan import (normalize_double_n, to_hepburn, to_hiragana,
                    to_katakana, to_kana, to_kunrei, to_roma, expand_consonant,
                    is_consonant, is_vowel)

__version__ = "1.2"
