import asyncio
import logging
from functools import partial
from typing import Callable, List, Optional, Union

import discord
import wavelink
from discord.ext import commands
from wavelink.errors import ZeroConnectedNodes
from wavelink.utils import MISSING

from naotimes.bot import naoTimesBot
from naotimes.context import naoTimesContext
from naotimes.helpgenerator import HelpField, HelpOption
from naotimes.music import UnsupportedURLFormat, format_duration
from naotimes.music.errors import (
    EnsureBotVoiceChannel,
    EnsureHaveRequirement,
    EnsureVoiceChannel,
    SpotifyUnavailable,
    WavelinkNoNodes,
)
from naotimes.music.genius import GeniusLyricHit
from naotimes.music.queue import GuildMusicInstance, TrackEntry, TrackRepeat
from naotimes.music.track import TwitchDirectLink
from naotimes.paginator import DiscordPaginatorUI
from naotimes.timeparse import TimeString
from naotimes.utils import cutoff_text

GENIUS_ICON = "https://assets.genius.com/images/apple-touch-icon.png"


def is_in_voice():
    async def predicate(ctx: naoTimesContext):
        if not ctx.voice_client:
            raise EnsureBotVoiceChannel(ctx)
        return True

    return commands.check(predicate)


def ensure_voice():
    async def predicate(ctx: naoTimesContext):
        author = ctx.author
        if not ctx.voice_client:
            if author.voice is None:
                raise EnsureVoiceChannel(ctx)
            vc_channel = author.voice.channel
            player = await vc_channel.connect(cls=wavelink.Player)
            ctx.bot.ntplayer.create(player)
            ctx.bot.ntplayer.change_dj(player, author)
            ctx.bot.ntplayer.set_channel(player, vc_channel)
            ctx.bot.loop.create_task(
                ctx.bot.ntplayer.play_next(player),
                name=f"naotimes-player-instance-creation-{player.guild.id}-init",
            )
        return True

    return commands.check(predicate)


def user_in_vc():
    async def predicate(ctx: naoTimesContext):
        author = ctx.author
        if author.voice is None:
            return EnsureVoiceChannel(ctx, False)
        return True

    return commands.check(predicate)


def is_god(ctx: naoTimesContext, _p: wavelink.Player, _i: GuildMusicInstance):
    perms = ctx.author.guild_permissions
    if perms.administrator:
        return None
    if perms.manage_guild:
        return None
    if perms.manage_channels:
        return None
    return "Bukan orang yang memiliki hak cukup di Rolenya"


def is_host(ctx: naoTimesContext, _p, instance: GuildMusicInstance):
    if instance.host and ctx.author == instance.host:
        return None
    return "Bukan host atau DJ utama"


def check_requirements(
    *requirements: List[Callable[[naoTimesContext, wavelink.Player, GuildMusicInstance], Optional[str]]]
):
    async def predicate(ctx: naoTimesContext):
        vc: wavelink.Player = ctx.voice_client
        if not vc:
            raise EnsureBotVoiceChannel(ctx)
        instance = ctx.bot.ntplayer.get(vc)
        reason = []
        for requirement in requirements:
            check = requirement(ctx, vc, instance)
            if asyncio.iscoroutinefunction(check):
                check = await check
            reason.append(check)
        has_none = any(r is None for r in reason)
        if not has_none:
            merged_reason = " atau ".join(reason)
            raise EnsureHaveRequirement(ctx, merged_reason)
        return True

    return commands.check(predicate)


def node_available():
    async def predicate(ctx: naoTimesContext):
        try:
            wavelink.NodePool.get_node()
        except ZeroConnectedNodes:
            raise WavelinkNoNodes
        return True

    return commands.check(predicate)


def clean_escapes(argument: str) -> str:
    if "http://" in argument or "https://" in argument:
        if argument.startswith("<") and argument.endswith(">"):
            return argument[1:-1]
        elif argument.startswith("<"):
            return argument[1:]
        elif argument.endswith(">"):
            return argument[:-1]
    return argument


class MusikPlayerCommand(commands.Cog):
    def __init__(self, bot: naoTimesBot):
        self.bot = bot
        self.logger = logging.getLogger("MusicP.Main")

    def _generate_help_embed(self, ctx: naoTimesContext):
        playback = ctx.create_help("musik", "Fitur musik naoTimes")
        _query_help = "`<query>` merupakan URL ataupun kueri pencarian\nKami support: "
        supported_client = ["Youtube", "Twitch", "Bandcamp", "Soundcloud"]
        if self.bot.ntplayer._spotify:
            spoti_client = self.bot.ntplayer._spotify
            is_native = hasattr(spoti_client, "_url_host")
            if is_native:
                supported_client.append("Spotify (Native)")
            else:
                supported_client.append("Spotify (via Youtube)")
        _query_help += ", ".join(supported_client)
        playback.add_fields(
            [
                HelpField(
                    "musik play",
                    "Memutar musik, alias lain: `musik p`",
                    HelpOption("query", _query_help, True),
                ),
                HelpField(
                    "musik join",
                    "Buat bot gabung ke kanal tertentu atau join ke VC anda",
                    HelpOption(
                        "kanal", "Mention kanal atau ketik IDnya, jika tidak diberikan akan pake VC anda!"
                    ),
                ),
                HelpField(
                    "musik stop",
                    "Hentikan semua lagu dan hapus semua queue, "
                    "hanya admin/host yang bisa menggunakan perintah ini",
                ),
                HelpField(
                    "musik leave",
                    "Keluar dari VC dan menghapus semua queue, "
                    "hanya admin/host yang bisa menggunakan perintah ini",
                ),
                HelpField(
                    "musik np",
                    "Melihat lagu yang sedang diputar",
                ),
                HelpField("musik info", "Melihat informasi pemutar musik untuk peladen anda."),
            ]
        )
        playback.add_aliases(["m", "music"])

        _mode_TEXT = "Matikan: `off`, `no`, `matikan`, `mati`\n"
        _mode_TEXT += "Single (Satu lagu): `single`, `satu`, `ini`\n"
        _mode_TEXT += "Semua (Semua lagu): `all`, `semua`"

        queue = ctx.create_help("musik", "Sistem queue musik naoTimes")
        queue.add_fields(
            [
                HelpField(
                    "musik queue",
                    "Melihat queue musik yang sedang diputar, alias lain: `musik q`",
                ),
                HelpField(
                    "musik queue remove",
                    "Menghapus salah satu lagu dari queue, alias lain: `musik q remove`",
                    HelpOption(
                        "indeks",
                        "Posisi lagu yang ingin dihapus, bisa diliat via `!musik q`",
                        True,
                    ),
                ),
                HelpField(
                    "musik queue clear",
                    "Membersihkan queue, hanya admin/host yang bisa menggunakan perintah ini!",
                ),
                HelpField(
                    "musik repeat",
                    "Mengatur sistem repeat untuk pemutar musik peladen anda",
                    HelpOption("mode", f"`<mode>` merupakan mode repeat yang diinginkan\n{_mode_TEXT}", True),
                ),
            ]
        )
        queue.add_aliases(["m", "music"])

        others = ctx.create_help("musik", "Fitur lain-lain musik")
        others.add_fields(
            [
                HelpField(
                    "musik delegasi",
                    "Mengubah host utama ke member lain",
                    HelpOption(
                        "member",
                        "Mention member, nama member, atau ID member",
                        True,
                    ),
                ),
                HelpField(
                    "musik volume",
                    "Mengatur volume pemutar musik",
                    HelpOption(
                        "volume",
                        "Angka dari 1 sampai 100, jika tidak diberikan akan dikasih tau volume sekarang",
                    ),
                ),
                HelpField(
                    "musik lirik",
                    "Mencari lirik lagu yang sedang diputar",
                    HelpOption(
                        "kueri",
                        "Kueri pencarian, ini dapat diabaikan dan bot akan menggunakan judul musik.",
                    ),
                ),
            ]
        )
        others.add_aliases(["m", "music"])
        return [playback.get(), queue.get(), others.get()]

    @commands.group(name="musik", aliases=["m", "music"])
    @commands.guild_only()
    @node_available()
    async def musik_player(self, ctx: naoTimesContext):
        if ctx.invoked_subcommand is None:
            if not ctx.empty_subcommand(2):
                return
            help_collect = self._generate_help_embed(ctx)
            paginator = DiscordPaginatorUI(ctx, help_collect)
            await paginator.interact(30.0)

    @musik_player.command(name="help", aliases=["h", "bantu"])
    async def musik_player_help(self, ctx: naoTimesContext):
        help_collect = self._generate_help_embed(ctx)
        paginator = DiscordPaginatorUI(ctx, help_collect)
        await paginator.interact(30.0)

    def _check_perms(self, permission: discord.Permissions):
        if permission.administrator:
            return True
        if permission.manage_guild:
            return True
        if permission.manage_channels:
            return True
        return False

    async def _create_player_instance(
        self, channel: Union[discord.VoiceChannel, discord.StageChannel], author: discord.Member
    ):
        player = await channel.connect(cls=wavelink.Player)
        self.bot.ntplayer.create(player)
        self.bot.ntplayer.change_dj(player, author)
        self.bot.ntplayer.set_channel(player, channel)
        self.bot.loop.create_task(
            self.bot.ntplayer.play_next(player),
            name=f"naotimes-track-end-{player.guild.id}_init",
        )
        return player

    async def select_track(self, ctx: naoTimesContext, all_tracks: List[wavelink.Track]):
        """Select a track"""

        messages = []
        messages.append("**Mohon ketik angka yang ingin anda tambahkan ke Bot!**")
        max_tracks = all_tracks[:7]
        for ix, track in enumerate(max_tracks, 1):
            messages.append(f"**{ix}**. `{track.title}` [{format_duration(track.duration)}]")
        messages.append("\nKetik `cancel` untuk membatalkan!")

        await ctx.send("\n".join(messages), reference=ctx.message)
        _CANCEL_MSG = ["cancel", "batal", "batalkan"]

        def check(m: discord.Message):
            return (
                m.author == ctx.author
                and m.channel == ctx.channel
                and (
                    (m.content.isdigit() and int(m.content) <= len(max_tracks))
                    or m.content.lower() in _CANCEL_MSG
                )
            )

        res: discord.Message
        self.logger.info(f"Now waiting for {ctx.author} to select one of the tracks")
        try:
            res = await self.bot.wait_for("message", check=check, timeout=30.0)
        except (asyncio.CancelledError, asyncio.TimeoutError):
            self.logger.warning("Message timeout, cancelling...")
            return MISSING
        content = res.content
        if content.lower() in _CANCEL_MSG:
            self.logger.info(f"{ctx.author} cancelled selection")
            return None
        selected = max_tracks[int(content) - 1]
        self.logger.info(f"Selected track #{content} -- {selected}")
        return selected

    @musik_player.command(name="join", aliases=["j", "gabung", "g"])
    async def musik_player_join(self, ctx: naoTimesContext, channel: commands.VoiceChannelConverter = None):
        if ctx.voice_client:
            return await ctx.send(
                f"Bot telah join VC lain ({ctx.voice_client.channel.mention}), "
                "mohon putuskan terlebih dahulu!"
            )

        author = ctx.author
        vc_channel: Union[discord.VoiceChannel, discord.StageChannel] = None
        if not isinstance(channel, (discord.VoiceChannel, discord.StageChannel)):
            vc_me = author.voice
            if vc_me is None:
                return await ctx.send("Mohon join VC atau mention VC yang anda mau!")

            vc_channel = vc_me.channel
        else:
            vc_channel = channel

        self.logger.info(f"PlayerVoice: Joining VC: {vc_channel}")
        await self._create_player_instance(vc_channel, author)
        await ctx.message.add_reaction("🎵")

    @musik_player.command(name="play", aliases=["p", "setel"])
    @ensure_voice()
    @user_in_vc()
    async def musik_player_play(self, ctx: naoTimesContext, *, query: str = None):
        if not query:
            return await ctx.send("Mohon masukkan query musik yang ingin anda putar!")
        # Clean URL if possible
        query = clean_escapes(query)
        author = ctx.author
        vc: wavelink.Player = ctx.voice_client

        if not author.voice:
            return await ctx.send(f"Mohon join voice chat {vc.channel.mention} untuk menyetel lagu!")

        self.logger.info(f"PlayerVoice: <{ctx.guild.id}> Searching for {query}...")
        should_pick = not query.startswith("http")
        try:
            await ctx.send("Mencoba memuat lagu...", reference=ctx.message)
            all_results = await self.bot.ntplayer.search_track(query, vc.node)
        except UnsupportedURLFormat as se:
            return await ctx.send(f"URL tidak didukung: <{se.url}>\n{se.reason}", reference=ctx.message)
        except SpotifyUnavailable:
            return await ctx.send(
                "Anda mencoba menyetel URL Spotify tetapi owner bot tidak mengaktifkan fitur Spotify!",
                reference=ctx.message,
            )
        except Exception:
            self.logger.exception(f"PlayerVoice: <{ctx.guild.id}> Searching for {query} failed")
            return await ctx.send(
                "Terjadi kesalahan saat mencari lagu, mohon coba lagi!", reference=ctx.message
            )

        if not all_results:
            return await ctx.send("Tidak dapat menemukan lagu yang anda inginkan!", reference=ctx.message)

        if isinstance(all_results, list):
            if len(all_results) == 1:
                select_track = all_results[0]
                wrap_in_entry = TrackEntry(select_track, author, ctx.channel)
                await self.bot.ntplayer.enqueue(vc, wrap_in_entry)
                instance = self.bot.ntplayer.get(vc)
                await ctx.send(
                    f"Menambahkan `{select_track.title}` ke pemutar musik! (Posisi {instance.queue.qsize()})",
                    reference=ctx.message,
                )
            elif should_pick:
                select_track = await self.select_track(ctx, all_results)
                if select_track is MISSING:
                    return await ctx.send("Tidak ada lagu yang dipilih!", reference=ctx.message)
                if select_track is None:
                    return await ctx.send("Dibatalkan", reference=ctx.message)
                await self.bot.ntplayer.enqueue(vc, TrackEntry(select_track, author, ctx.channel))
                instance = self.bot.ntplayer.get(vc)
                await ctx.send(
                    f"Menambahkan `{select_track.title}` ke pemutar musik! (Posisi {instance.queue.qsize()})",
                    reference=ctx.message,
                )
            else:
                # Queue all tracks
                self.logger.info(f"PlayerQueue: <{ctx.guild.id}> detected results as playlist, loading...")
                wrapped_tracks: List[TrackEntry] = []
                for track in all_results:
                    wrapped_tracks.append(TrackEntry(track, author, ctx.channel))
                await self.bot.ntplayer.enqueue(vc, wrapped_tracks)

                self.logger.info(f"PlayerQueue: <{ctx.guild.id}> loaded {len(wrapped_tracks)} tracks")
                await ctx.send(
                    f"Menambahkan playlist ke pemutar musik! Total ada: {len(wrapped_tracks)}",
                    reference=ctx.message,
                )
        else:
            # Single track:
            await self.bot.ntplayer.enqueue(vc, TrackEntry(all_results, author, ctx.channel))
            instance = self.bot.ntplayer.get(vc)
            await ctx.send(
                f"Menambahkan `{all_results.title}` ke pemutar musik! (Posisi {instance.queue.qsize()})",
                reference=ctx.message,
            )

    @musik_player.command(name="nowplaying", aliases=["np", "lagu"])
    @is_in_voice()
    async def musik_player_nowplaying(self, ctx: naoTimesContext):
        vc: wavelink.Player = ctx.voice_client
        instance = self.bot.ntplayer.get(vc)
        if instance.current is None:
            return await ctx.send("Tidak ada lagu yang diputar saat ini!")

        current_position = vc.position
        embed = self.bot.ntplayer.generate_track_embed(instance.current, current_position)
        await ctx.send(embed=embed)

    @musik_player.command(name="stop", aliases=["hentikan"])
    @is_in_voice()
    @check_requirements(is_god, is_host)
    async def musik_player_stop(self, ctx: naoTimesContext):
        vc: wavelink.Player = ctx.voice_client
        self.bot.ntplayer.clear(vc)
        await vc.stop()
        await ctx.message.add_reaction("👍")

    @musik_player.command(name="leave", aliases=["dc", "disconnect"])
    @is_in_voice()
    @check_requirements(is_god, is_host)
    async def musik_player_leave(self, ctx: naoTimesContext):
        vc: wavelink.Player = ctx.voice_client
        self.bot.ntplayer.clear(vc)
        await vc.stop()
        await vc.disconnect(force=True)
        await ctx.message.add_reaction("👍")

    @musik_player.command(name="skip", aliases=["lewat"])
    @is_in_voice()
    @user_in_vc()
    async def musik_player_skip(self, ctx: naoTimesContext):
        author = ctx.author
        vc: wavelink.Player = ctx.voice_client
        instance = self.bot.ntplayer.get(vc)

        if instance.current is None and instance.queue.empty():
            return await ctx.send("Tidak ada lagu yang diputar saat ini!", reference=ctx.message)
        if instance.host and instance.host == author:
            await vc.stop()
            return await ctx.send("DJ melewati lagu ini!", reference=ctx.message)
        if self._check_perms(author.guild_permissions):
            await vc.stop()
            return await ctx.send("Admin atau moderator melewati lagu ini!", reference=ctx.message)
        if instance.current.requester == author:
            await vc.stop()
            return await ctx.send("Pemutar lagu ini melewati lagu ini!", reference=ctx.message)

        if not author.voice:
            return await ctx.send(
                f"Mohon join voice chat {vc.channel.mention} untuk melewati lagu!", reference=ctx.message
            )

        if author.id in instance.skip_votes:
            return await ctx.send("Anda sudah voting untuk melewati lagu!", reference=ctx.message)

        self.bot.ntplayer.add_vote(vc, author.id)
        current_vote = len(instance.skip_votes)

        required = self.bot.ntplayer.get_requirements(vc)
        if required <= current_vote:
            await vc.stop()
            await ctx.send(f"Lagu di skip dikarenakan {current_vote} dari {required} orang vote untuk skip")
        else:
            await ctx.send(f"Dibutuhkan {required} untuk nge-skip lagu ({current_vote}/{required} orang)")

    def _vol_emote(self, volume: int):
        if volume < 1:
            return "🔇"
        elif volume < 25:
            return "🔈"
        elif volume < 70:
            return "🔉"
        return "🔊"

    @musik_player.command(name="volume", aliases=["vol", "v"])
    @is_in_voice()
    @user_in_vc()
    @check_requirements(is_god, is_host)
    async def musik_player_volume(self, ctx: naoTimesContext, volume: int = None):
        vc: wavelink.Player = ctx.voice_client
        if not volume:
            vol_real = int(vc.volume)
            embed = discord.Embed(colour=discord.Color.from_rgb(98, 66, 225))
            embed.description = f"{self._vol_emote(vol_real)} Volume sekarang adalah {vol_real}%"
            return await ctx.send(embed=embed)

        if volume < 1 or volume > 100:
            return await ctx.send("Volume harus antara 1-100!")

        await vc.set_volume(volume)
        embed = discord.Embed(colour=discord.Color.from_rgb(98, 66, 225))
        embed.description = f"{self._vol_emote(volume)} Volume diatur ke {volume}%"
        return await ctx.send(embed=embed)

    def _loop_emote(self, mode: TrackRepeat):
        if mode == TrackRepeat.all:
            return "🔁"
        elif mode == TrackRepeat.single:
            return "🔂"
        return "🚫"

    @musik_player.command(name="repeat", aliases=["ulang", "ulangi", "loop"])
    @is_in_voice()
    @user_in_vc()
    @check_requirements(is_god, is_host)
    async def musik_player_repeat(self, ctx: naoTimesContext, mode: str = ""):
        vc: wavelink.Player = ctx.voice_client
        _mode_off = ["off", "no", "matikan", "mati"]
        _mode_single = ["single", "satu", "ini"]
        _mode_all = ["all", "semua"]
        _mode_repeat = [*_mode_off, *_mode_single, *_mode_all]
        instance = self.bot.ntplayer.get(vc)
        if not mode:
            embed = discord.Embed(colour=discord.Color.from_rgb(98, 66, 225))
            embed.description = f"{self._loop_emote(instance.repeat)} {instance.repeat.nice}"
            return await ctx.send(embed=embed)

        mode = mode.lower()
        if mode not in _mode_repeat:
            return await ctx.send("Mode tidak diketahui!")

        mode_change = TrackRepeat.disable
        if mode in _mode_single:
            mode_change = TrackRepeat.single
        elif mode in _mode_all:
            mode_change = TrackRepeat.all
        emote_change = self._loop_emote(mode_change)

        change_res = self.bot.ntplayer.change_repeat_mode(vc, mode_change)
        if change_res is None:
            return await ctx.send("Sudah dalam mode repeat yang anda berikan!")
        if change_res is MISSING:
            return await ctx.send("Mode repeat tidak diketahui!")

        if mode_change == TrackRepeat.single:
            if change_res.current is not None:
                change_res.queue._queue = [change_res.current]
        elif mode_change == TrackRepeat.all:
            if change_res.current is not None:
                change_res.queue.put_nowait(change_res.current)

        embed = discord.Embed(colour=discord.Color.from_rgb(98, 66, 225))
        embed.description = f"{emote_change} {change_res.repeat.nice}"
        await ctx.send(embed=embed)

    @musik_player.command(name="info")
    @is_in_voice()
    async def musik_player_info(self, ctx: naoTimesContext):
        vc: wavelink.Player = ctx.voice_client
        instance = self.bot.ntplayer.get(vc)

        is_playing = "Tidak"
        if vc.is_playing():
            is_playing = "Ya"

        embed = discord.Embed(colour=discord.Color.from_rgb(227, 150, 64))
        embed.set_author(name="🎶 Pemutar Musik", icon_url=self.bot.user.avatar)

        spoti_emote = "<:ntSpotifyX:903302923474337802>"
        via_yt = "<:vtBYT:843473930348920832>"
        if not ctx.me.guild_permissions.use_external_emojis:
            spoti_emote = "🎶 **Spotify**"
            via_yt = "YouTube"

        host_name = "*Tidak ada host, mohon join VC*"
        if instance.host is not None:
            host_name = instance.host.mention

        description = []
        description.append(f"🪧 **Peladen**: {ctx.guild.name}")
        description.append(f"🧑‍🦱 **Host**: {host_name}")
        description.append(f"🎵 **Aktif**? `{is_playing}`")
        volume = int(vc.volume)
        description.append(f"{self._vol_emote(volume)} {volume}%")
        description.append(f"🔁 {instance.repeat.nice}")
        description.append(f"🔢 {instance.queue.qsize()} lagu lagi")
        description.append(f"📍 **Node**: `{vc.node.identifier} - {vc.node.region.name}`")
        spoti_mode = "Tidak"
        spoti_test = vc.node._spotify
        if spoti_test:
            spoti_mode = f"Ya (via {via_yt})"
            if getattr(vc.node, "_url_host", True):
                spoti_mode = "Ya (Native)"
        description.append(f"{spoti_emote} {spoti_mode}")
        embed.description = "\n".join(description)
        await ctx.send(embed=embed)

    @musik_player.command(name="delegasi", aliases=["delegate", "gantidj"])
    @is_in_voice()
    @user_in_vc()
    @check_requirements(is_god, is_host)
    async def musik_player_delegasi(self, ctx: naoTimesContext, member: commands.MemberConverter = None):
        vc: wavelink.Player = ctx.voice_client
        if not isinstance(member, discord.Member):
            return await ctx.send("Tidak dapat menemukan member tersebut!")

        if member.guild != ctx.guild:
            return await ctx.send("Member tersebut bukan member peladen ini!")

        if member.bot:
            return await ctx.send("Member adalah bot, tidak bisa mengubah DJ/host ke bot.")

        self.bot.ntplayer.change_dj(vc, member)
        await ctx.send(f"{member.mention} sekarang menjadi DJ utama!", reference=ctx.message)

    @musik_player.command(name="lirik", aliases=["lyrics", "lyric"])
    @is_in_voice()
    async def musik_player_lyric(self, ctx: naoTimesContext, *, override_query: str = None):
        if not self.bot.genius:
            return await ctx.send("Fitur lirik tidak diaktifkan oleh Owner bot!")
        vc: wavelink.Player = ctx.voice_client
        instance = self.bot.ntplayer.get(vc)
        if not instance.current:
            return await ctx.send("Tidak ada lagu yang sedang disetel untuk diliat liriknya!")

        current = instance.current.track
        if isinstance(current, TwitchDirectLink):
            return await ctx.send("Twitch stream tidak support untuk pencarian lirik!")
        search_query = f"{current.author} - {current.title}"
        if getattr(current, "source", None) == "youtube":
            search_query = f"{current.title}"
        if override_query:
            search_query = override_query
        message_temp = await ctx.send(f"Mencari lirik untuk `{current.title}`...")
        self.logger.info(
            f"GeniusLyric<{vc.guild}>: Searching for track <{current.title}> with query: {search_query}"
        )
        matching_lyrics, error = await self.bot.genius.find_lyrics(search_query)
        if not matching_lyrics:
            self.logger.warning(
                f"GeniusLyric<{vc.guild}>: No match for <{current.title}> with query: {search_query}"
            )
            return await ctx.send(error)

        embed = discord.Embed(colour=discord.Color.from_rgb(227, 150, 64))
        embed.set_author(name="🎶 Lirik Lagu", icon_url=self.bot.user.avatar)
        description_data = []
        for nn, matches in enumerate(matching_lyrics, 1):
            description_data.append(f"**{nn}**. `{matches.title}`")
        embed.description = "\n".join(description_data)

        await message_temp.edit(embed=embed)
        selected: Optional[GeniusLyricHit] = None
        while True:
            temp = await ctx.wait_content(
                "Mohon ketik angka yang anda inginkan",
                delete_prompt=False,
                delete_answer=False,
                timeout=None,
                pass_message=message_temp,
            )
            if temp is False:
                break
            if temp.isdigit():
                number_real = int(temp)
                if number_real > 0 and number_real <= len(matching_lyrics):
                    selected = matching_lyrics[number_real - 1]
                    break
                await ctx.send_timed(f"Mohon masukan angka yang valid! (1-{len(matching_lyrics)})")
            else:
                await ctx.send_timed("Mohon masukan angka yang valid!")

        if selected is None:
            return await ctx.send("Dibatalkan!")

        song_title = selected.title
        self.logger.info(f"GeniusLyric<{vc.guild}>: Requesting lyric <{current.title}>: {selected.path}")
        await message_temp.edit(content=f"Mengambil lirik: {song_title}", embed=None)
        lyrics = await self.bot.genius.get_lyrics(selected.path)

        split_lyrics = lyrics.split("\n")
        # Split lyrics by line, merged together if it's still in 2000 char limit
        joined_lyrics = []
        temp_lyrics = []
        for line in split_lyrics:
            temp_join = "\n".join(temp_lyrics)
            if len(temp_join) >= 2000:
                joined_lyrics.append(temp_join)
                temp_lyrics = []
            temp_lyrics.append(line)
            temp_join = "\n".join(temp_lyrics)
            if len(temp_join) >= 2000:
                temp_lyrics.pop(-1)
                joined_lyrics.append("\n".join(temp_lyrics))
                temp_lyrics = []

        if temp_lyrics:
            joined_lyrics.append("\n".join(temp_lyrics))

        embed_sets: List[discord.Embed] = []
        for number, lyrics_part in enumerate(joined_lyrics, 1):
            embed = discord.Embed(colour=discord.Color.from_rgb(227, 150, 64))
            add_numbering = f" ({number}/{len(joined_lyrics)})"
            if len(joined_lyrics) < 2:
                add_numbering = ""
            embed.set_author(
                name=cutoff_text(f"{song_title}{add_numbering}", 250),
                url=f"https://genius.com{selected.path}",
                icon_url=self.bot.user.avatar,
            )
            embed.description = lyrics_part
            embed.set_footer(text="Lirik diambil dari Genius", icon_url=GENIUS_ICON)
            embed_sets.append(embed)

        try:
            await message_temp.delete()
        except (discord.HTTPException, discord.Forbidden, discord.NotFound):
            pass
        self.logger.info(f"GeniusLyric<{vc.guild}>: Sending lyric <{current.title}>: {selected.path}")
        paginator = DiscordPaginatorUI(ctx, embed_sets)
        await paginator.interact()

    def _generate_simple_queue_embed(
        self,
        dataset: List[TrackEntry],
        current: int,
        maximum: int,
        real_total: int,
        total_duration: float,
    ):
        embed = discord.Embed(colour=discord.Color.random())
        embed.set_author(name="🎶 Pemutar Musik", icon_url=self.bot.user.avatar)

        starting_track = ((current + 1) * 5) - 5
        total_durasi = TimeString.from_seconds(total_duration).to_string()

        description_fmt = []
        for n, track in enumerate(dataset, starting_track + 1):
            description_fmt.append(
                f"**{n}**. `{track.track.title}` [{format_duration(track.track.duration)}] (Diputar oleh: `{track.requester}`)"  # noqa: E501
            )

        embed.description = "\n".join(description_fmt)
        embed.set_footer(text=f"Tersisa {real_total} lagu ({current + 1}/{maximum}) | {total_durasi}")
        return embed

    @musik_player.group(name="queue", aliases=["q"])
    @is_in_voice()
    async def musik_player_queue(self, ctx: naoTimesContext):
        if not ctx.invoked_subcommand:
            if not ctx.empty_subcommand(3):
                return

            instance = self.bot.ntplayer.get(ctx.voice_client)
            if instance.queue.empty():
                return await ctx.send("Tidak ada lagu di daftar putar!")

            all_queued_tracks = [d for d in instance.queue._queue]
            total_duration = sum(track.track.duration for track in all_queued_tracks)

            # Split into chunks
            chunked_tracks = [all_queued_tracks[i : i + 5] for i in range(0, len(all_queued_tracks), 5)]

            partial_embed = partial(
                self._generate_simple_queue_embed,
                maximum=len(chunked_tracks),
                real_total=len(all_queued_tracks),
                total_duration=total_duration,
            )

            view = DiscordPaginatorUI(ctx, chunked_tracks)
            view.attach(partial_embed)
            await view.interact()

    @musik_player_queue.command(name="remove", aliases=["hapus"])
    @user_in_vc()
    async def musik_player_queue_remove(self, ctx: naoTimesContext, index: int):
        vc: wavelink.Player = ctx.voice_client
        instance = self.bot.ntplayer.get(vc)
        if instance.queue.qsize() < 1:
            return await ctx.send("Tidak ada lagu di daftar putar!")

        if index < 1:
            return await ctx.send("Posisi harus lebih dari satu!", reference=ctx.message)
        if index > instance.queue.qsize():
            return await ctx.send(
                "Posisi tidak boleh lebih dari jumlah lagu di daftar putar!", reference=ctx.message
            )

        index -= 1
        track = instance.queue._queue[index]
        success = False
        if track.requester == ctx.author:
            success = self.bot.ntplayer.delete_track(vc, index)
        elif instance.host and instance.host == ctx.author:
            success = self.bot.ntplayer.delete_track(vc, index)
        elif self._check_perms(ctx.author.guild_permissions):
            success = self.bot.ntplayer.delete_track(vc, index)
        else:
            return await ctx.send(
                f"Anda tidak memiliki hak untuk menghapus lagu `{track.track.title}` dari daftar putar!",
                reference=ctx.message,
            )

        if success:
            return await ctx.send(
                f"Lagu `{track.track.title}` berhasil dihapus dari daftar putar!", reference=ctx.message
            )
        await ctx.send("Tidak dapat menghapus lagu dari daftar putar!", reference=ctx.message)

    @musik_player_queue.command(name="clear", aliases=["bersihkan"])
    @user_in_vc()
    @check_requirements(is_god, is_host)
    async def musik_player_queue_clear(self, ctx: naoTimesContext):
        instance = self.bot.ntplayer.get(ctx.voice_client)
        if instance.queue.qsize() < 1:
            return await ctx.send("Tidak ada lagu di daftar putar!")

        if instance.repeat == TrackRepeat.single:
            return await ctx.send("Tidak dapat menghapus daftar putar jika mode repeat adalah single!")

        self.bot.ntplayer.clear(ctx.voice_client)
        await ctx.send("Daftar putar dibersihkan!", reference=ctx.message)


def setup(bot: naoTimesBot):
    bot.add_cog(MusikPlayerCommand(bot))
