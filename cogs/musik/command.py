import asyncio
import logging
from collections.abc import Awaitable, Callable
from functools import partial
from typing import Any, Union

import discord
import wavelink
from discord import app_commands
from discord.ext import commands

from naotimes.bot import naoTimesBot
from naotimes.context import naoTimesContext
from naotimes.music.errors import (
    EnsureBotHasQueue,
    EnsureBotVoiceChannel,
    EnsureHaveRequirement,
    EnsureVoiceChannel,
    SpotifyNoTrackFound,
    SpotifyUnavailable,
    UnsupportedURLFormat,
    WavelinkNoNodes,
)
from naotimes.music.lyrics.client import LyricSource, naoTimesLyricsResult
from naotimes.music.player import MISSING, MissingValue, format_duration, naoTimesPlayer
from naotimes.music.queue import GuildMusicInstance, TrackEntry, TrackRepeat
from naotimes.paginator import DiscordPaginatorUI
from naotimes.timeparse import TimeString
from naotimes.utils import cutoff_text
from naotimes.views.multi_view import Selection

GENIUS_ICON = "https://assets.genius.com/images/apple-touch-icon.png"
MXM_ICON = "https://s.mxmcdn.net/site/images/mxm_icn_114.png"
NETEASE_ICON = "https://p.ihateani.me/kdrbldgu.png"

VocalChannel = Union[discord.VoiceChannel, discord.StageChannel]
Requirement = Callable[[discord.Member, wavelink.Player, GuildMusicInstance], str | None]
Translator = Callable[..., str]

REPEAT_KEYS = {
    TrackRepeat.disable: "repeat.mode_disable",
    TrackRepeat.single: "repeat.mode_single",
    TrackRepeat.all: "repeat.mode_all",
}

# Requirement callables return i18n keys; `_enforce` localises them for the user.


def _bot(inter: discord.Interaction) -> naoTimesBot:
    return inter.client  # type: ignore[return-value]


def _player_manager(bot: naoTimesBot) -> naoTimesPlayer:
    manager = bot.ntplayer
    if manager is None:
        raise RuntimeError("Music player is not initialized")
    return manager


async def _ctx(inter: discord.Interaction) -> naoTimesContext:
    return await _bot(inter).get_context(inter)


def _player(inter: discord.Interaction) -> wavelink.Player | None:
    vc = inter.guild.voice_client if inter.guild else None
    return vc if isinstance(vc, wavelink.Player) else None


async def _require_player(inter: discord.Interaction) -> wavelink.Player:
    if inter.guild is None:
        raise app_commands.NoPrivateMessage()
    player = _player(inter)
    if player is None:
        raise EnsureBotVoiceChannel(await _ctx(inter))
    return player


async def _require_member(inter: discord.Interaction) -> discord.Member:
    if not isinstance(inter.user, discord.Member):
        raise app_commands.NoPrivateMessage()
    return inter.user


async def _require_voice_member(inter: discord.Interaction) -> tuple[discord.Member, VocalChannel]:
    member = await _require_member(inter)
    voice_state = member.voice
    if voice_state is None or not isinstance(voice_state.channel, (discord.VoiceChannel, discord.StageChannel)):
        raise EnsureVoiceChannel(await _ctx(inter), False)
    return member, voice_state.channel


def _bot_avatar_url(bot: naoTimesBot) -> str | None:
    return bot.user.display_avatar.url if bot.user is not None else None


# ---- checks
def check_node_available(inter: discord.Interaction) -> bool:
    manager = _bot(inter).ntplayer
    if manager is None or not manager.tracked_nodes:
        raise WavelinkNoNodes

    nodes = wavelink.Pool.nodes
    if not any(
        identifier in manager.tracked_nodes and node.status is wavelink.NodeStatus.CONNECTED
        for identifier, node in nodes.items()
    ):
        raise WavelinkNoNodes
    return True


async def check_in_voice(inter: discord.Interaction) -> bool:
    if _player(inter) is None:
        raise EnsureBotVoiceChannel(await _ctx(inter))
    return True


async def check_user_in_vc(inter: discord.Interaction) -> bool:
    await _require_voice_member(inter)
    return True


async def check_has_queue(inter: discord.Interaction) -> bool:
    player = _player(inter)
    if player is None:
        raise EnsureBotVoiceChannel(await _ctx(inter))
    if _player_manager(_bot(inter)).get(player).queue.empty():
        raise EnsureBotHasQueue(await _ctx(inter))
    return True


def is_god(member: discord.Member, _p, _i) -> str | None:
    perms = member.guild_permissions
    if perms.administrator or perms.manage_guild or perms.manage_channels:
        return None
    return "requirement.god"


def is_host(member: discord.Member, _p, instance: GuildMusicInstance) -> str | None:
    if instance.host and member == instance.host:
        return None
    return "requirement.host"


async def _enforce(inter: discord.Interaction, *requirements: Requirement) -> None:
    vc = await _require_player(inter)
    instance = _player_manager(_bot(inter)).get(vc)
    member = await _require_member(inter)
    reasons = [req(member, vc, instance) for req in requirements]
    failed_reasons = [reason for reason in reasons if reason is not None]
    if failed_reasons and len(failed_reasons) == len(requirements):
        ctx = await _ctx(inter)
        raise EnsureHaveRequirement(ctx, *(ctx.t(reason) for reason in failed_reasons))


def check_requirements(*requirements: Requirement):
    async def predicate(inter: discord.Interaction) -> bool:
        await _enforce(inter, *requirements)
        return True

    return app_commands.check(predicate)


def clean_escapes(argument: str) -> str:
    if argument.startswith("<") and argument.endswith(">"):
        return argument[1:-1]
    return argument


def can_manage(permission: discord.Permissions) -> bool:
    return permission.administrator or permission.manage_guild or permission.manage_channels


class MusikPlayerCommand(commands.Cog):
    musik = app_commands.Group(
        name="musik",
        description=app_commands.locale_str("Fitur musik naoTimes", key="musik.group.musik"),
        guild_only=True,
    )
    queue = app_commands.Group(
        name="queue",
        description=app_commands.locale_str("Sistem daftar putar", key="musik.group.queue"),
        parent=musik,
    )

    def __init__(self, bot: naoTimesBot):
        self.bot = bot
        self.logger = logging.getLogger("MusicP.Main")

    async def _run_player_action(
        self,
        inter: discord.Interaction,
        action: Callable[[], Awaitable[Any]],
        action_name: str,
        success_message: str | discord.Embed,
    ) -> bool:
        ctx = await _ctx(inter)
        await inter.response.defer()
        try:
            await asyncio.wait_for(action(), timeout=20.0)
        except TimeoutError:
            self.logger.warning("Player action '%s' timed out in guild %s", action_name, inter.guild_id)
            await inter.followup.send(ctx.t("error.node_timeout"), ephemeral=True)
            return False
        except Exception as exc:
            self.logger.error("Player action '%s' failed in guild %s", action_name, inter.guild_id, exc_info=exc)
            await inter.followup.send(ctx.t("error.action_failed"), ephemeral=True)
            return False

        if isinstance(success_message, discord.Embed):
            await inter.followup.send(embed=success_message)
        else:
            await inter.followup.send(success_message)
        return True

    @property
    def player_manager(self) -> naoTimesPlayer:
        return _player_manager(self.bot)

    @musik.command(
        name="admin",
        description=app_commands.locale_str(
            "Lihat peladen dengan pemutar musik aktif (owner)", key="musik.admin.description"
        ),
    )
    @app_commands.default_permissions(administrator=True)
    async def musik_admin_active(self, inter: discord.Interaction):
        ctx = await _ctx(inter)
        if not await self.bot.is_owner(inter.user):
            return await inter.response.send_message(ctx.t("admin.owner_only"), ephemeral=True)
        active_players = list(self.player_manager.actives.keys())

        guild_named: list[str] = [ctx.t("admin.header")]
        for n, player in enumerate(active_players, 1):
            guild = self.bot.get_guild(player)
            if guild is None:
                guild_named.append(ctx.t("admin.entry_unknown", n=n, id=player))
            else:
                guild_named.append(ctx.t("admin.entry", n=n, name=guild.name, id=player))

        await inter.response.send_message("\n".join(guild_named), ephemeral=True)

    async def _create_player_instance(
        self, inter: discord.Interaction, channel: VocalChannel, author: discord.Member
    ) -> wavelink.Player | None:
        ctx = await _ctx(inter)
        player: wavelink.Player | None = None
        try:
            player = await channel.connect(cls=wavelink.Player, self_deaf=True)
            self.player_manager.create(player)
            self.player_manager.change_dj(player, author)
            self.player_manager.set_channel(player, channel)
            self.bot.loop.create_task(
                self.player_manager.play_next(player),
                name=f"naotimes-track-end-{channel.guild.id}_init",
            )
        except Exception as exc:
            self.logger.error("Failed to create music player in guild %s", channel.guild.id, exc_info=exc)
            if player is None:
                pending_player = channel.guild.voice_client
                if (
                    isinstance(pending_player, wavelink.Player)
                    and pending_player.channel == channel
                    and not pending_player.connected
                ):
                    player = pending_player
            if player is not None:
                self.player_manager.delete(player)
                try:
                    await player.disconnect()
                except Exception as cleanup_error:
                    self.logger.warning("Failed to clean up voice connection", exc_info=cleanup_error)
            await inter.followup.send(
                ctx.t("error.connect_failed", channel=channel.mention),
                ephemeral=True,
            )
            return None
        return player

    async def select_track(
        self, ctx: naoTimesContext, all_tracks: list[wavelink.Playable]
    ) -> wavelink.Playable | MissingValue | None:
        max_tracks = all_tracks[:7]
        messages = [ctx.t("select.prompt")]
        for ix, track in enumerate(max_tracks, 1):
            messages.append(
                ctx.t("select.entry", n=ix, title=track.title, duration=format_duration(track.length / 1000))
            )
        selections = [Selection(str(ix), f"ntplayer-{t.identifier}", t.title) for ix, t in enumerate(max_tracks, 1)]

        selected = await ctx.select_single_button("\n".join(messages), selections, timeout=30.0)
        if selected is None:
            return MISSING
        if selected is False:
            return None
        found = [t for t in all_tracks if f"ntplayer-{t.identifier}" == selected.name]
        return found[0] if found else MISSING

    # ---- commands
    @musik.command(
        name="join",
        description=app_commands.locale_str("Buat bot gabung ke VC", key="musik.join.description"),
    )
    @app_commands.describe(
        kanal=app_commands.locale_str("Kanal suara tujuan (default: VC kamu)", key="musik.join.option")
    )
    @app_commands.check(check_node_available)
    async def musik_join(
        self,
        inter: discord.Interaction,
        kanal: discord.VoiceChannel | discord.StageChannel | None = None,
    ):
        guild = inter.guild
        if guild is None:
            raise app_commands.NoPrivateMessage()
        author = await _require_member(inter)
        ctx = await _ctx(inter)
        if guild.voice_client:
            return await inter.response.send_message(
                ctx.t("join.already_connected", channel=guild.voice_client.channel),
                ephemeral=True,
            )
        target = kanal
        if target is None:
            _, target = await _require_voice_member(inter)
        if target is None:
            return await inter.response.send_message(ctx.t("join.no_voice"), ephemeral=True)
        await inter.response.defer()
        player = await self._create_player_instance(inter, target, author)
        if player is None:
            return
        await inter.followup.send(ctx.t("join.success", channel=target.mention))

    @musik.command(
        name="play",
        description=app_commands.locale_str("Putar musik dari URL atau kueri pencarian", key="musik.play.description"),
    )
    @app_commands.describe(
        query=app_commands.locale_str(
            "URL atau kueri pencarian (YouTube, SoundCloud, Spotify, dll)", key="musik.play.option"
        )
    )
    @app_commands.check(check_node_available)
    @app_commands.check(check_user_in_vc)
    async def musik_play(self, inter: discord.Interaction, query: str):
        await inter.response.defer()
        ctx = await _ctx(inter)
        author, user_channel = await _require_voice_member(inter)
        vc = _player(inter)
        if vc is None:
            vc = await self._create_player_instance(inter, user_channel, author)
            if vc is None:
                return

        if user_channel != vc.channel:
            return await inter.followup.send(ctx.t("play.join_first", channel=vc.channel.mention))

        query = clean_escapes(query)
        self.logger.info(f"PlayerVoice: <{inter.guild_id}> Searching for {query}...")
        should_pick = not query.startswith("http")
        try:
            results = await asyncio.wait_for(self.player_manager.search_track(query, vc.node), timeout=30.0)
        except TimeoutError:
            self.logger.warning(f"PlayerVoice: <{inter.guild_id}> Searching for {query} timed out")
            return await inter.followup.send(ctx.t("play.search_timeout"), ephemeral=True)
        except UnsupportedURLFormat as se:
            return await inter.followup.send(ctx.t("play.unsupported_url", url=se.url, reason=se.reason))
        except SpotifyUnavailable:
            return await inter.followup.send(ctx.t("play.spotify_disabled"))
        except SpotifyNoTrackFound:
            return await inter.followup.send(ctx.t("play.spotify_no_track"))
        except Exception:
            self.logger.exception(f"PlayerVoice: <{inter.guild_id}> Searching for {query} failed")
            return await inter.followup.send(ctx.t("play.search_error"))

        if not results:
            return await inter.followup.send(ctx.t("play.not_found"))

        if not results:
            return await inter.followup.send(ctx.t("play.not_found"))

        if len(results) > 1 and should_pick:
            picked = await self.select_track(ctx, results)
            if isinstance(picked, MissingValue):
                return await inter.followup.send(ctx.t("play.none_selected"))
            if picked is None:
                return await inter.followup.send(ctx.t("play.cancelled"))
            results = [picked]

        channel = inter.channel
        if not isinstance(channel, discord.TextChannel):
            return await inter.followup.send(ctx.t("play.text_channel_only"))
        entries = [TrackEntry(track, author, channel) for track in results]
        await self.player_manager.enqueue(vc, entries)
        if len(entries) == 1:
            instance = self.player_manager.get(vc)
            return await inter.followup.send(
                ctx.t("play.added_one", title=entries[0].track.title, position=instance.queue.qsize())
            )
        await inter.followup.send(ctx.t("play.added_many", count=len(entries)))

    @musik.command(
        name="nowplaying",
        description=app_commands.locale_str("Lihat lagu yang sedang diputar", key="musik.nowplaying.description"),
    )
    @app_commands.check(check_in_voice)
    async def musik_nowplaying(self, inter: discord.Interaction):
        vc = await _require_player(inter)
        ctx = await _ctx(inter)
        instance = self.player_manager.get(vc)
        if instance.current is None:
            return await inter.response.send_message(ctx.t("error.no_track_playing"), ephemeral=True)
        embed = self.player_manager.generate_track_embed(instance.current, vc.position)
        await inter.response.send_message(embed=embed)

    @musik.command(
        name="stop",
        description=app_commands.locale_str("Hentikan lagu dan hapus daftar putar", key="musik.stop.description"),
    )
    @app_commands.check(check_in_voice)
    @check_requirements(is_god, is_host)
    async def musik_stop(self, inter: discord.Interaction):
        ctx = await _ctx(inter)
        vc = await _require_player(inter)
        self.player_manager.clear(vc)
        await self._run_player_action(inter, partial(vc.skip, force=True), "stop", ctx.t("stop.success"))

    @musik.command(
        name="leave",
        description=app_commands.locale_str("Keluar dari VC dan hapus daftar putar", key="musik.leave.description"),
    )
    @app_commands.check(check_in_voice)
    @check_requirements(is_god, is_host)
    async def musik_leave(self, inter: discord.Interaction):
        ctx = await _ctx(inter)
        vc = await _require_player(inter)
        if await self._run_player_action(inter, vc.disconnect, "leave", ctx.t("leave.success")):
            self.player_manager.delete(vc)

    @musik.command(
        name="skip",
        description=app_commands.locale_str("Lewati lagu yang sedang diputar", key="musik.skip.description"),
    )
    @app_commands.check(check_in_voice)
    @app_commands.check(check_user_in_vc)
    async def musik_skip(self, inter: discord.Interaction):
        ctx = await _ctx(inter)
        author, user_channel = await _require_voice_member(inter)
        vc = await _require_player(inter)
        instance = self.player_manager.get(vc)
        send = inter.response.send_message

        if instance.current is None:
            return await send(ctx.t("error.no_track_playing"), ephemeral=True)
        if instance.queue.qsize() < 1:
            return await send(ctx.t("skip.no_next"), ephemeral=True)
        if instance.host and instance.host == author:
            return await self._run_player_action(inter, partial(vc.skip, force=True), "skip", ctx.t("skip.dj"))
        if can_manage(author.guild_permissions):
            return await self._run_player_action(inter, partial(vc.skip, force=True), "skip", ctx.t("skip.admin"))
        if instance.current.requester == author:
            return await self._run_player_action(inter, partial(vc.skip, force=True), "skip", ctx.t("skip.requester"))
        if user_channel != vc.channel:
            return await send(ctx.t("skip.join_first", channel=vc.channel.mention), ephemeral=True)
        if author.id in instance.skip_votes:
            return await send(ctx.t("skip.already_voted"), ephemeral=True)

        self.player_manager.add_vote(vc, author)
        current_vote = len(instance.skip_votes)
        required = self.player_manager.get_requirements(vc)
        if required <= current_vote:
            return await self._run_player_action(
                inter,
                partial(vc.skip, force=True),
                "skip",
                ctx.t("skip.voted", current=current_vote, required=required),
            )
        else:
            await send(ctx.t("skip.vote_needed", required=required, current=current_vote))

    @staticmethod
    def _vol_emote(volume: int) -> str:
        if volume < 1:
            return "🔇"
        if volume < 25:
            return "🔈"
        if volume < 70:
            return "🔉"
        return "🔊"

    @musik.command(
        name="volume",
        description=app_commands.locale_str("Lihat atau atur volume", key="musik.volume.description"),
    )
    @app_commands.describe(
        volume=app_commands.locale_str(
            "Angka 1-100, kosongkan untuk melihat volume sekarang", key="musik.volume.option"
        )
    )
    @app_commands.check(check_in_voice)
    async def musik_volume(self, inter: discord.Interaction, volume: app_commands.Range[int, 1, 100] | None = None):
        vc = await _require_player(inter)
        ctx = await _ctx(inter)
        embed = discord.Embed(colour=discord.Color.from_rgb(98, 66, 225))
        if volume is None:
            vol = int(vc.volume)
            embed.description = ctx.t("volume.current", emote=self._vol_emote(vol), volume=vol)
            return await inter.response.send_message(embed=embed)

        await _enforce(inter, is_god, is_host)
        embed.description = ctx.t("volume.set", emote=self._vol_emote(volume), volume=volume)
        await self._run_player_action(inter, partial(vc.set_volume, volume), "volume", embed)

    @staticmethod
    def _loop_emote(mode: TrackRepeat) -> str:
        return {TrackRepeat.all: "🔁", TrackRepeat.single: "🔂"}.get(mode, "🚫")

    @musik.command(
        name="repeat",
        description=app_commands.locale_str("Atur mode pengulangan", key="musik.repeat.description"),
    )
    @app_commands.describe(
        mode=app_commands.locale_str(
            "Mode pengulangan, kosongkan untuk melihat mode sekarang", key="musik.repeat.option"
        )
    )
    @app_commands.choices(
        mode=[
            app_commands.Choice(name=app_commands.locale_str("Mati", key="musik.repeat.choice_off"), value="off"),
            app_commands.Choice(
                name=app_commands.locale_str("Satu lagu", key="musik.repeat.choice_single"), value="single"
            ),
            app_commands.Choice(name=app_commands.locale_str("Semua lagu", key="musik.repeat.choice_all"), value="all"),
        ]
    )
    @app_commands.check(check_in_voice)
    async def musik_repeat(self, inter: discord.Interaction, mode: app_commands.Choice[str] | None = None):
        vc = await _require_player(inter)
        ctx = await _ctx(inter)
        instance = self.player_manager.get(vc)
        embed = discord.Embed(colour=discord.Color.from_rgb(98, 66, 225))
        if mode is None:
            embed.description = f"{self._loop_emote(instance.repeat)} {ctx.t(REPEAT_KEYS[instance.repeat])}"
            return await inter.response.send_message(embed=embed)

        await _enforce(inter, is_god, is_host)
        mode_change = {"off": TrackRepeat.disable, "single": TrackRepeat.single, "all": TrackRepeat.all}[mode.value]
        change_res = self.player_manager.change_repeat_mode(vc, mode_change)
        if change_res is None:
            return await inter.response.send_message(ctx.t("repeat.already"), ephemeral=True)

        if mode_change == TrackRepeat.single and change_res.current is not None:
            change_res.queue.clear()
            change_res.queue.put_nowait(change_res.current)
        elif mode_change == TrackRepeat.all and change_res.current is not None:
            change_res.queue.put_nowait(change_res.current)

        embed.description = f"{self._loop_emote(mode_change)} {ctx.t(REPEAT_KEYS[change_res.repeat])}"
        await inter.response.send_message(embed=embed)

    @musik.command(
        name="info",
        description=app_commands.locale_str("Informasi pemutar musik peladen ini", key="musik.info.description"),
    )
    @app_commands.check(check_in_voice)
    async def musik_info(self, inter: discord.Interaction):
        vc = await _require_player(inter)
        ctx = await _ctx(inter)
        instance = self.player_manager.get(vc)
        host_name = instance.host.mention if instance.host else ctx.t("info.no_host")
        volume = int(vc.volume)

        embed = discord.Embed(colour=discord.Color.from_rgb(227, 150, 64))
        embed.set_author(name=ctx.t("player.author"), icon_url=_bot_avatar_url(self.bot))
        guild = inter.guild
        if guild is None:
            raise app_commands.NoPrivateMessage()
        embed.description = "\n".join([
            ctx.t("info.guild", guild=guild.name),
            ctx.t("info.host", host=host_name),
            ctx.t("info.active", active=ctx.t("info.active_yes") if vc.playing else ctx.t("info.active_no")),
            ctx.t("info.volume", emote=self._vol_emote(volume), volume=volume),
            ctx.t("info.repeat", repeat=ctx.t(REPEAT_KEYS[instance.repeat])),
            ctx.t("info.queue_count", count=instance.queue.qsize()),
            ctx.t("info.node", node=vc.node.identifier),
        ])
        await inter.response.send_message(embed=embed)

    @musik.command(
        name="delegasi",
        description=app_commands.locale_str("Ubah host/DJ utama ke member lain", key="musik.delegasi.description"),
    )
    @app_commands.describe(member=app_commands.locale_str("Member yang menjadi DJ baru", key="musik.delegasi.option"))
    @app_commands.check(check_in_voice)
    @app_commands.check(check_user_in_vc)
    @check_requirements(is_god, is_host)
    async def musik_delegasi(self, inter: discord.Interaction, member: discord.Member):
        ctx = await _ctx(inter)
        if member.bot:
            return await inter.response.send_message(ctx.t("delegasi.is_bot"), ephemeral=True)
        self.player_manager.change_dj(await _require_player(inter), member)
        await inter.response.send_message(ctx.t("delegasi.success", member=member.mention))

    @musik.command(
        name="jeda",
        description=app_commands.locale_str("Jeda lagu", key="musik.jeda.description"),
    )
    @app_commands.check(check_in_voice)
    @app_commands.check(check_user_in_vc)
    @check_requirements(is_god, is_host)
    async def musik_pause(self, inter: discord.Interaction):
        ctx = await _ctx(inter)
        vc = await _require_player(inter)
        if vc.paused:
            return await inter.response.send_message(ctx.t("jeda.already_paused"), ephemeral=True)
        if not vc.playing:
            return await inter.response.send_message(ctx.t("jeda.no_track"), ephemeral=True)
        await self._run_player_action(inter, partial(vc.pause, True), "pause", ctx.t("jeda.success"))

    @musik.command(
        name="lanjut",
        description=app_commands.locale_str("Lanjutkan lagu yang dijeda", key="musik.lanjut.description"),
    )
    @app_commands.check(check_in_voice)
    @app_commands.check(check_user_in_vc)
    @check_requirements(is_god, is_host)
    async def musik_resume(self, inter: discord.Interaction):
        ctx = await _ctx(inter)
        vc = await _require_player(inter)
        if not vc.paused:
            return await inter.response.send_message(ctx.t("lanjut.not_paused"), ephemeral=True)
        await self._run_player_action(inter, partial(vc.pause, False), "resume", ctx.t("lanjut.success"))

    @musik.command(
        name="lirik",
        description=app_commands.locale_str("Cari lirik lagu yang sedang diputar", key="musik.lirik.description"),
    )
    @app_commands.describe(
        kueri=app_commands.locale_str("Kueri pencarian lirik (default: judul lagu)", key="musik.lirik.option")
    )
    @app_commands.check(check_in_voice)
    async def musik_lyric(self, inter: discord.Interaction, kueri: str | None = None):
        ctx = await _ctx(inter)
        vc = await _require_player(inter)
        instance = self.player_manager.get(vc)
        if not instance.current:
            return await inter.response.send_message(ctx.t("lirik.no_track"), ephemeral=True)
        if self.bot.ntlyrics is None:
            return await inter.response.send_message(ctx.t("lirik.disabled"), ephemeral=True)

        await inter.response.defer()
        current = instance.current.track
        message_temp = await inter.followup.send(ctx.t("lirik.searching", title=current.title), wait=True)
        try:
            matching, error = await asyncio.wait_for(self.bot.ntlyrics.find_lyrics(current, kueri), timeout=30.0)
        except TimeoutError:
            self.logger.warning("Lyrics search timed out for %s", current.title)
            return await message_temp.edit(content=ctx.t("lirik.search_timeout"), embed=None)
        except Exception as exc:
            self.logger.error("Lyrics search failed for %s", current.title, exc_info=exc)
            return await message_temp.edit(content=ctx.t("lirik.search_error"), embed=None)
        if not matching:
            return await message_temp.edit(content=error.to_string())

        selected: naoTimesLyricsResult | None = None
        if len(matching) == 1:
            selected = matching[0]
        else:
            embed = discord.Embed(colour=discord.Color.from_rgb(227, 150, 64))
            embed.set_author(name=ctx.t("lirik.author"), icon_url=_bot_avatar_url(self.bot))
            embed.description = "\n".join(f"**{n}**. `{m.title}`" for n, m in enumerate(matching, 1))
            await message_temp.edit(content=None, embed=embed)
            ctx = await _ctx(inter)
            selections = [Selection(str(n), f"lyric-{n}", m.title) for n, m in enumerate(matching[:10], 1)]
            picked = await ctx.select_single_button(ctx.t("lirik.select_prompt"), selections, timeout=60.0)
            if picked:
                picked_name = picked.name
                if picked_name is not None:
                    _, _, index = picked_name.partition("-")
                    if index.isdecimal():
                        selected = matching[int(index) - 1]

        if selected is None:
            return await message_temp.edit(content=ctx.t("lirik.cancelled"), embed=None)

        song_title = selected.title
        await message_temp.edit(content=ctx.t("lirik.fetching", title=song_title), embed=None)
        try:
            lyrics = await asyncio.wait_for(self.bot.ntlyrics.lookup_lyrics(selected.lyrics), timeout=30.0)
        except TimeoutError:
            self.logger.warning("Lyrics retrieval timed out for %s", song_title)
            return await message_temp.edit(content=ctx.t("lirik.fetch_timeout"), embed=None)
        except Exception as exc:
            self.logger.error("Lyrics retrieval failed for %s", song_title, exc_info=exc)
            return await message_temp.edit(content=ctx.t("lirik.fetch_error"), embed=None)
        split_lyrics = lyrics.split("\n") if isinstance(lyrics, str) else lyrics

        joined: list[str] = []
        buffer: list[str] = []
        for line in split_lyrics:
            buffer.append(line)
            if len("\n".join(buffer)) >= 2000:
                buffer.pop()
                joined.append("\n".join(buffer))
                buffer = [line]
        if buffer:
            joined.append("\n".join(buffer))

        icon, source = {
            LyricSource.GENIUS: (GENIUS_ICON, "Genius"),
            LyricSource.NETEASE: (NETEASE_ICON, "NetEase"),
        }.get(selected.source, (MXM_ICON, "Musixmatch"))
        embeds: list[discord.Embed] = []
        for number, part in enumerate(joined, 1):
            embed = discord.Embed(colour=discord.Color.from_rgb(227, 150, 64), description=part)
            numbering = f" ({number}/{len(joined)})" if len(joined) > 1 else ""
            embed.set_author(name=cutoff_text(f"{song_title}{numbering}", 250), icon_url=_bot_avatar_url(self.bot))
            embed.set_footer(text=ctx.t("lirik.footer", source=source), icon_url=icon)
            embeds.append(embed)

        try:
            await message_temp.delete()
        except (discord.HTTPException, discord.Forbidden, discord.NotFound):
            pass
        paginator = DiscordPaginatorUI(await _ctx(inter), embeds)
        await paginator.interact()

    # ---- queue
    def _generate_simple_queue_embed(
        self,
        dataset: list[TrackEntry],
        current: int,
        maximum: int,
        real_total: int,
        total_duration: float,
        tr: Translator,
    ):
        embed = discord.Embed(colour=discord.Colour.random())
        embed.set_author(name=tr("player.author"), icon_url=_bot_avatar_url(self.bot))
        start = ((current + 1) * 5) - 5
        total_durasi = TimeString.from_seconds(total_duration).to_string()
        embed.description = "\n".join(
            tr(
                "queue.list.entry",
                n=n,
                title=t.track.title,
                duration=format_duration(t.track.length / 1000),
                requester=t.requester,
            )
            for n, t in enumerate(dataset, start + 1)
        )
        embed.set_footer(
            text=tr(
                "queue.list.footer",
                total=real_total,
                current=current + 1,
                maximum=maximum,
                duration=total_durasi,
            )
        )
        return embed

    @queue.command(
        name="list",
        description=app_commands.locale_str("Lihat daftar putar", key="musik.queue.list.description"),
    )
    @app_commands.check(check_in_voice)
    async def queue_list(self, inter: discord.Interaction):
        instance = self.player_manager.get(await _require_player(inter))
        ctx = await _ctx(inter)
        if instance.queue.empty():
            return await inter.response.send_message(ctx.t("queue.list.empty"), ephemeral=True)

        tracks = list(instance.queue._queue)
        total_duration = sum(t.track.length for t in tracks) / 1000
        chunks = [tracks[i : i + 5] for i in range(0, len(tracks), 5)]
        embed_fn = partial(
            self._generate_simple_queue_embed,
            maximum=len(chunks),
            real_total=len(tracks),
            total_duration=total_duration,
            tr=ctx.t,
        )
        view = DiscordPaginatorUI(await _ctx(inter), chunks)
        view.attach(embed_fn)
        await view.interact()

    @queue.command(
        name="remove",
        description=app_commands.locale_str("Hapus lagu dari daftar putar", key="musik.queue.remove.description"),
    )
    @app_commands.describe(
        posisi=app_commands.locale_str("Posisi lagu (lihat di /musik queue list)", key="musik.queue.remove.option")
    )
    @app_commands.check(check_user_in_vc)
    @app_commands.check(check_has_queue)
    async def queue_remove(self, inter: discord.Interaction, posisi: app_commands.Range[int, 1]):
        ctx = await _ctx(inter)
        vc = await _require_player(inter)
        author = await _require_member(inter)
        instance = self.player_manager.get(vc)
        if posisi > instance.queue.qsize():
            return await inter.response.send_message(ctx.t("queue.position_too_high"), ephemeral=True)
        index = posisi - 1
        track = instance.queue._queue[index]
        allowed = (
            track.requester == author
            or (instance.host and instance.host == author)
            or can_manage(author.guild_permissions)
        )
        if not allowed:
            return await inter.response.send_message(
                ctx.t("queue.remove.no_permission", title=track.track.title),
                ephemeral=True,
            )
        if self.player_manager.delete_track(vc, index):
            return await inter.response.send_message(ctx.t("queue.remove.success", title=track.track.title))
        await inter.response.send_message(ctx.t("queue.remove.failed"), ephemeral=True)

    @queue.command(
        name="clear",
        description=app_commands.locale_str("Bersihkan daftar putar", key="musik.queue.clear.description"),
    )
    @app_commands.check(check_user_in_vc)
    @app_commands.check(check_has_queue)
    @check_requirements(is_god, is_host)
    async def queue_clear(self, inter: discord.Interaction):
        ctx = await _ctx(inter)
        vc = await _require_player(inter)
        if self.player_manager.get(vc).repeat == TrackRepeat.single:
            return await inter.response.send_message(ctx.t("queue.clear.repeat_single"), ephemeral=True)
        self.player_manager.clear(vc)
        await inter.response.send_message(ctx.t("queue.clear.success"))

    @queue.command(
        name="move",
        description=app_commands.locale_str(
            "Pindahkan posisi lagu di daftar putar", key="musik.queue.move.description"
        ),
    )
    @app_commands.describe(
        dari=app_commands.locale_str("Posisi awal", key="musik.queue.move.option_from"),
        ke=app_commands.locale_str("Posisi tujuan", key="musik.queue.move.option_to"),
    )
    @app_commands.check(check_user_in_vc)
    @app_commands.check(check_has_queue)
    @check_requirements(is_god, is_host)
    async def queue_move(
        self, inter: discord.Interaction, dari: app_commands.Range[int, 1], ke: app_commands.Range[int, 1]
    ):
        ctx = await _ctx(inter)
        vc = await _require_player(inter)
        instance = self.player_manager.get(vc)
        size = instance.queue.qsize()
        if dari > size or ke > size:
            return await inter.response.send_message(ctx.t("queue.position_too_high"), ephemeral=True)
        if instance.repeat != TrackRepeat.disable:
            return await inter.response.send_message(ctx.t("queue.move.repeat_active"), ephemeral=True)
        instance.freeze()
        try:
            qcopy = instance.queue._queue.copy()
            qcopy.rotate(-(dari - 1))
            track = qcopy.popleft()
            qcopy.rotate(dari - 1)
            qcopy.insert(ke - 1, track)
            instance.queue._queue = qcopy
            self.player_manager.set(vc, instance)
        except Exception as e:
            self.logger.error("An error occured while trying to move track from queue!", exc_info=e)
            return await inter.response.send_message(ctx.t("queue.move.error"), ephemeral=True)
        finally:
            instance.unfreeze()
        await inter.response.send_message(ctx.t("queue.move.success"))


async def setup(bot: naoTimesBot):
    if bot.ntplayer is None:
        bot.logger.warning("Music is not configured; not loading the music command cog")
        return
    await bot.add_cog(MusikPlayerCommand(bot))
