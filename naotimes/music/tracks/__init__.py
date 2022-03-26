"""
naotimes.music.tracks
~~~~~~~~~~~~~~~~~~~~~~~
A collection of track objects for Wavelink.

:copyright: (c) 2019-2021 naoTimesdev
:license: MIT, see LICENSE for more details.
"""

from __future__ import annotations

from typing import List, Union

from wavelink import YouTubeTrack
from wavelink.ext.spotify import SpotifyTrack

from .bandcamp import *
from .soundcloud import *
from .spotify import *
from .tidal import *
from .twitch import *
from .youtube import *

SingleTrackResult = Union[
    BandcampDirectLink,
    SoundcloudDirectLink,
    SpotifyPartialTrack,
    SpotifyDirectTrack,
    TidalDirectLink,
    TidalPartialTrack,
    YoutubeDirectLinkTrack,
    YouTubeTrack,
    SpotifyTrack,
]
MultiTrackResult = Union[
    List[BandcampDirectLink],
    List[SoundcloudDirectLink],
    List[SpotifyPartialTrack],
    List[SpotifyDirectTrack],
    List[TidalDirectLink],
    List[TidalPartialTrack],
    List[YoutubeDirectLinkTrack],
    List[YouTubeTrack],
    List[SpotifyTrack],
]

TrackResults = Union[SingleTrackResult, MultiTrackResult]
