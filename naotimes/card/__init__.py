"""
naotimes.card
~~~~~~~~~~~~~~
A module to help generate a card for naoTimes using pyppeteer.

:copyright: (c) 2019-2021 naoTimesdev
:license: MIT, see LICENSE for more details.
"""

from .enums import *
from .generator import *
from .usercard import *

AvailableCardGen = [UserCardGenerator]
