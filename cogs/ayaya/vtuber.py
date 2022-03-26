import argparse
import logging
import re
from functools import partial
from typing import Callable, Dict, List, NamedTuple, Optional, Union

import arrow
import disnake
from disnake.ext import commands

from naotimes.bot import naoTimesBot
from naotimes.context import naoTimesContext
from naotimes.converters import Arguments, CommandArgParse
from naotimes.helpgenerator import HelpField
from naotimes.models import vtuber as vtmodel
from naotimes.paginator import DiscordPaginator
from naotimes.utils import bold, complex_walk, quote

VTUBER_QUERY_OBJECT = """
query VTuberLive($cursor:String,$platforms:[PlatformName],$chIds:[ID],$groups:[String]) {
    vtuber {
        live(cursor:$cursor,limit:100,platforms:$platforms,channel_id:$chIds,groups:$groups) {
            _total
            items {
                id
                title
                status
                channel {
                    id
                    en_name
                    room_id
                    name
                    image
                }
                timeData {
                    startTime
                }
                thumbnail
                viewers
                platform
                is_premiere
                is_member
                group
            }
            pageInfo {
                hasNextPage
                nextCursor
            }
        }
    }
}

query VTuberUpcoming($cursor:String,$platforms:[PlatformName],$chIds:[ID],$groups:[String]) {
    vtuber {
        upcoming(cursor:$cursor,limit:100,platforms:$platforms,channel_id:$chIds,groups:$groups) {
            _total
            items {
                id
                title
                status
                channel {
                    id
                    en_name
                    room_id
                    name
                    image
                }
                timeData {
                    scheduledStartTime
                    startTime
                }
                thumbnail
                viewers
                platform
                is_premiere
                is_member
                group
            }
            pageInfo {
                hasNextPage
                nextCursor
            }
        }
    }
}

query VTuberChannels($cursor:String,$platforms:[PlatformName],$chIds:[ID],$groups:[String]) {
    vtuber {
        channels(cursor:$cursor,limit:100,platforms:$platforms,id:$chIds,groups:$groups,sort_by:"name") {
            _total
            items {
                id
                en_name
                room_id
                name
                image
                group
                platform
                statistics {
                    subscriberCount
                    viewCount
                }
                publishedAt
            }
            pageInfo {
                hasNextPage
                nextCursor
            }
        }
    }
}

query VTuberGroups {
  vtuber {
    groups {
      items
    }
  }
}
"""

GROUPS_NAME_MAPPINGS = {
    "anagataid": "Anagata ID",
    "animare": "Animare",
    "axel-v": "AXEL-V",
    "cattleyarg": "Cattleya Regina Games",
    "dotlive": ".LIVE",
    "eilene": "Eilene",
    "entum": "ENTUM",
    "hanayori": "Hanayori",
    "hololive": "Hololive",
    "hololiveen": "Hololive English",
    "hololivecn": "Hololive China",
    "hololiveid": "Hololive Indonesia",
    "holostars": "Holostars",
    "honeystrap": "Honeystrap",
    "irisbg": "Iris Black Games",
    "kamitsubaki": "KAMITSUBAKI Studio",
    "kizunaai": "Kizuna Ai Co.",
    "lupinusvg": "Lupinus Video Games",
    "mahapanca": "MAHA5",
    "nijisanji": "NIJISANJI",
    "nijisanjiid": "NIJISANJI Indonesia",
    "nijisanjiin": "NIJISANJI India",
    "nijisanjikr": "NIJISANJI Korea",
    "nijisanjien": "NIJISANJI English",
    "noriopro": "Norio Production",
    "paryiproject": "Paryi Project",
    "solovtuber": "Solo/Indie",
    "sugarlyric": "SugarLyric",
    "tsunderia": "Tsunderia",
    "upd8": "upd8",
    "vapart": "VAPArt",
    "veemusic": "VEEMusic",
    "vgaming": "VGaming",
    "vic": "VIC",
    "virtuareal": "VirtuaReal",
    "vivid": "ViViD",
    "voms": "VOMS",
    "vspo": "VTuber eSports Project",
    "vshojo": "VShojo",
}

vt_platforms_args = ["-P", "--platform"]
vt_groups_args = ["-g", "--group"]
vt_chids_args = ["-c", "--channel-id"]
vt_platforms_kwargs = {
    "required": False,
    "dest": "platforms",
    "action": "append",
    "help": "Filter hasil ke platform tertentu, dapat diulang.\nEx: -P youtube -P twitch",
    "choices": ["youtube", "twitch", "twitcasting", "mildom"],
}
vt_groups_kwargs = {
    "required": False,
    "dest": "groups",
    "action": "append",
    "help": "Filter untuk organisasi atau grup tertentu, untuk mendapatkan "
    "listnya, dapat menggunakan perintah '!vtuber grup'."
    "Dapat diulang seperti --platform",
}
vt_chids_kwargs = {
    "required": False,
    "dest": "channels",
    "action": "append",
    "help": "Filter hanya untuk kanal tertentu, dapat diulang seperti --platform",
}

live_args = Arguments("vtuber live")
live_args.add_args(*vt_platforms_args, **vt_platforms_kwargs)
live_args.add_args(*vt_groups_args, **vt_groups_kwargs)
live_args.add_args(*vt_chids_args, **vt_chids_kwargs)

schedule_args = live_args.copy()
schedule_args.name = "vtuber jadwal"
channel_args = live_args.copy()
channel_args.name = "vtuber channel"

LiveConverter = CommandArgParse(live_args)
ScheduleConverter = CommandArgParse(schedule_args)
ChannelConverter = CommandArgParse(channel_args)


class VTuberConfig(NamedTuple):
    name: str
    color: int
    url: str
    channel: str
    logo: str

    def live(self, id: str):
        return self.url + id

    def kanal(self, id: str):
        return self.channel + id


class AyayaVTuber(commands.Cog):
    __COLOR_WEB_DATA = {
        "youtube": VTuberConfig(
            "YouTube",
            0xFF0000,
            "https://youtube.com/watch?v=",
            "https://youtube.com/channel/",
            "https://s.ytimg.com/yts/img/favicon_144-vfliLAfaB.png",
        ),
        "bilibili": VTuberConfig(
            "BiliBili",
            0x23ADE5,
            "https://live.bilibili.com/",
            "https://space.bilibili.com/",
            "https://logodix.com/logo/1224389.png",
        ),
        "twitch": VTuberConfig(
            "Twitch",
            0x9147FF,
            "https://www.twitch.tv/",
            "https://twitch.tv/",
            "https://p.n4o.xyz/i/twitchlogo.png",
        ),
        "twitcasting": VTuberConfig(
            "Twitcasting",
            0x280FC,
            "https://twitcasting.tv/",
            "https://twitcasting.tv/",
            "https://twitcasting.tv/img/icon192.png",
        ),
        "mildom": VTuberConfig(
            "Mildom",
            0x38CCE3,
            "https://www.mildom.com/",
            "https://www.mildom.com/profile/",
            "https://www.mildom.com/assets/logo.png",
        ),
    }
    DEFAULT_PLATFORMS = ["youtube", "twitch", "twitcasting", "mildom"]
    SubtituteEmote = [
        "1️⃣",
        "2️⃣",
        "3️⃣",
        "4️⃣",
        "5️⃣",
    ]
    NiceEmote = [
        str(disnake.PartialEmoji(name="vtBYT", id=843473930348920832)),
        str(disnake.PartialEmoji(name="vtBTTV", id=843474008984518687)),
        str(disnake.PartialEmoji(name="vtBTW", id=843473977484509184)),
        str(disnake.PartialEmoji(name="vtBMD", id=843474000159965226)),
        str(disnake.PartialEmoji(name="vtBB2", id=843474401310670848)),
    ]

    def __init__(self, bot: naoTimesBot):
        self.bot = bot
        self.logger = logging.getLogger("Ayaya.VTuber")

    @staticmethod
    def _group_by(dataset: List[dict], by: str) -> dict:
        grouped: Dict[str, List[dict]] = {}
        for data in dataset:
            key = complex_walk(data, by)
            if not isinstance(key, str):
                raise ValueError(f"The selected key is not a string, expected a string but got {key} instead")
            if key not in grouped:
                grouped[key] = []
            grouped[key].append(data)
        return grouped

    @commands.group("vtuber")
    @commands.guild_only()
    async def _ayaya_vtubermain(self, ctx: naoTimesContext):
        if ctx.invoked_subcommand is None:
            if not ctx.empty_subcommand(2):
                return await ctx.send("Tidak dapat menemukan bantuan perintah tersebut.")
            helpcmd = ctx.create_help(
                "vtuber",
                desc="Informasi stream VTuber dan sebagainya!\nSemua command menggunakan sistem `argparse`\n"
                "Silakan tambah `-h` setelah salah satu command untuk "
                f"melihat bantuan tambahan (ex: `{self.bot.prefixes(ctx)}vtuber live -h`)",
            )
            helpcmd.add_field(HelpField("vtuber", "Memunculkan bantuan perintah ini"))
            helpcmd.add_field(HelpField("vtuber live", "Melihat VTuber yang sedang live"))
            helpcmd.add_field(HelpField("vtuber jadwal", "Melihat jadwal stream VTuber"))
            helpcmd.add_field(HelpField("vtuber channel", "Melihat informasi sebuah channel"))
            helpcmd.add_field(HelpField("vtuber grup", "Melihat list grup atau organisasi yang terdaftar"))
            helpcmd.add_aliases()
            await ctx.send(embed=helpcmd.get())

    @staticmethod
    def _paginate_check(data: dict, base_path: str):
        if not data:
            return False, None, "cursor"
        has_next_page = complex_walk(data, base_path + ".pageInfo.hasNextPage")
        next_cursor = complex_walk(data, base_path + ".pageInfo.nextCursor")
        if next_cursor is None:
            has_next_page = False
        return bool(has_next_page), next_cursor, "cursor"

    async def _paginate_query(self, op: str, variables: dict, base_path: str):
        predicate = partial(self._paginate_check, base_path=base_path)
        full_data = []
        current_page = 1
        async for contents, page_info in self.bot.ihaapi.paginate(
            VTUBER_QUERY_OBJECT, predicate, variables, op
        ):
            self.logger.info(f"Reading result page no: {current_page}")
            the_data = complex_walk(contents.data, f"{base_path}.items")
            if isinstance(the_data, list):
                full_data.extend(the_data)
            if not page_info.hasMore:
                self.logger.info("no more page to paginate, breaking apart...")
                break
            current_page += 1
        return full_data

    def _check_bot_perms(self, ctx: naoTimesContext):
        the_guild: disnake.Guild = ctx.guild
        is_guild = the_guild is not None
        the_channel: disnake.TextChannel = ctx.channel
        bot_member = the_guild.get_member(self.bot.user.id)
        bbperms = the_channel.permissions_for(bot_member)

        is_valid_perm = True
        for perm in (
            bbperms.manage_messages,
            bbperms.embed_links,
            bbperms.read_message_history,
            bbperms.add_reactions,
        ):
            if not perm:
                is_valid_perm = False
                break
        has_emote_perm = bbperms.use_external_emojis
        return is_guild, is_valid_perm, has_emote_perm

    def _select_thumbnail(self, dataset: vtmodel._VTuberLiveItems):
        if dataset.platform == "youtube":
            return dataset.thumbnail
        elif dataset.platform == "twitch":
            if dataset.platform == "live":
                return dataset.thumbnail
            else:
                channel_id = dataset.channel.id
                return "https://ttvthumb.glitch.me/" + channel_id
        thumb = dataset.thumbnail
        if not thumb:
            return None
        return thumb

    def _generate_video_embed(
        self, dataset: Union[vtmodel._VTuberLiveItems, vtmodel._VTuberScheduleItems], pos: int, total: int
    ):
        platform_info = self.__COLOR_WEB_DATA.get(dataset.platform)
        title_fmt = platform_info.name
        video_id = dataset.id
        channel_id = dataset.channel.id
        if platform_info.name in ["Twitch", "Twitcasting", "Mildom"]:
            video_id = channel_id
        elif platform_info.name == "BiliBili":
            video_id = dataset.channel.room_id
        if dataset.is_premiere:
            title_fmt += " Premiere"
        else:
            title_fmt += " Stream"
        if dataset.is_member:
            title_fmt += " (Member-only)"
        title_fmt += f" [{pos + 1}/{total}]"
        channel_data = dataset.channel
        ch_name = channel_data.get("en_name", channel_data.get("name", "Tidak diketahui"))
        group_name = GROUPS_NAME_MAPPINGS.get(dataset.group, dataset.group.capitalize())
        group_text = f"{group_name} `(ID: {dataset.group})`"

        start_time = dataset.timeData.startTime
        start_time_fmt = f"<t:{start_time}:F>"
        url = platform_info.live(video_id)
        ch_url = platform_info.kanal(channel_id)
        joined_string = f"[**`Tonton`**]({url}) **\|\|** "  # noqa: W605
        joined_string += f"[**`Lihat Kanal`**]({ch_url})"
        description_data = []
        description_data.append(bold(dataset.title) + "\n")
        description_data.append(bold("Streamer") + f": `{ch_name}`")
        description_data.append(bold("Grup atau Organisasi") + f": {group_text}")
        description_data.append(bold("Mulai dari") + f": {start_time_fmt}\n")
        description_data.append(joined_string)
        embed = disnake.Embed(color=platform_info.color, timestamp=arrow.get(start_time).datetime)
        embed.set_author(name=title_fmt, url=url, icon_url=platform_info.logo)
        embed.set_thumbnail(url=dataset.channel.image)
        thumbnail = self._select_thumbnail(dataset)
        if thumbnail:
            embed.set_image(url=thumbnail)
        embed.description = "\n".join(description_data)
        embed.set_footer(
            text=f"ID: {video_id} | {platform_info.name} | Diprakasai dengan ihaAPI",
            icon_url="https://vtuber.ihateani.me/assets/favicon.png",
        )
        return embed

    @staticmethod
    def _create_stats_text(stats_data: vtmodel._VTuberChannelStatsItems):
        text_final = []
        key_names = {
            "subscriberCount": {"s": "Subscribers/Followers", "e": "Subs/Follow"},
            "viewCount": {"s": "Views", "e": "Views"},
            "videoCount": {"s": "Total Video", "e": "Video"},
            "level": {"s": "Level", "e": "Level"},
        }
        for key, value in stats_data.items():
            if isinstance(value, (int, float)):
                pre_suf = key_names.get(key, {"s": "Unknown"})
                name = pre_suf["s"]
                suf = pre_suf.get("e")
                text = f"- **{name}**: `{value:,d}"
                if suf:
                    text += f" {suf}"
                text += "`"
                text_final.append(text)
        return "\n".join(text_final)

    def _generate_channel_embed(self, dataset: vtmodel._VTuberChannelItems, pos: int, total: int):
        platform_info = self.__COLOR_WEB_DATA.get(dataset.platform)
        title_fmt = "Kanal " + platform_info.name
        title_fmt += f" [{pos + 1}/{total}]"
        group_name = GROUPS_NAME_MAPPINGS.get(dataset.group)
        ch_id = dataset.id
        if group_name is None:
            group_name = dataset.group.capitalize()
        group_txt = f"{group_name} `(ID: {dataset['group']})`"
        ch_name = dataset.get("en_name", dataset.get("name", "Tidak diketahui"))
        description = []
        description.append(bold(ch_name) + "\n")
        description.append(bold("Grup atau Organisasi") + f": {group_txt}")
        pub_at = complex_walk(dataset, "publishedAt")
        if pub_at:
            pub_at_dt: Optional[arrow.Arrow]
            try:
                pub_at_dt = arrow.get(pub_at)
            except arrow.ParserError:
                pub_at_dt = None
            if pub_at_dt is not None:
                timestamp = pub_at_dt.int_timestamp
                description.append(bold("Kanal dibuat pada") + f": <t:{timestamp}:F>")
        stats_text = self._create_stats_text(dataset.statistics)
        ch_url = platform_info.kanal(ch_id)
        description.append(bold("Statistik") + f":\n{stats_text}")
        description.append(f"[**`Lihat Kanal`**]({ch_url})")

        embed = disnake.Embed(color=platform_info.color)
        embed.set_author(
            name=title_fmt,
            url=ch_url,
            icon_url=platform_info.logo,
        )
        embed.description = "\n".join(description)
        embed.set_thumbnail(url=dataset.image)
        embed.set_footer(
            text=f"ID: {ch_id} | {platform_info.name} | Diprakasai oleh ihaAPI",
            icon_url="https://vtuber.ihateani.me/assets/favicon.png",
        )
        return embed

    async def _generator_lives(
        self,
        dataset: Dict[str, List[dict]],
        _,
        message: disnake.Message,
        emote: str,
        base_emotes: List[str],
        ctx: naoTimesContext,
        predicate: Callable[[List[dict], int, int], disnake.Embed],
    ):
        try:
            emote_pos = base_emotes.index(emote)
        except ValueError:
            return None, message

        all_keys = list(dataset.keys())
        proper_list = dataset.get(all_keys[emote_pos])
        if proper_list is None:
            return None, message
        paginate_gen = partial(predicate, total=len(proper_list))
        child_gen = DiscordPaginator(self.bot, ctx, proper_list)
        child_gen.set_generator(paginate_gen)
        child_gen.remove_at_trashed = False
        timeout = await child_gen.paginate(30.0, message)
        return None, message, timeout

    async def _parse_argument(self, parsed_args: argparse.Namespace):
        selected_platforms = []
        if isinstance(parsed_args.platforms, list):
            for platform in parsed_args.platforms:
                lowered = platform.lower()
                if lowered not in self.DEFAULT_PLATFORMS:
                    return None, None, None, f"Platform `{platform}` tidak ada di database."
                selected_platforms.append(lowered)

        selected_groups = []
        if isinstance(parsed_args.groups, list):
            for grup in parsed_args.groups:
                if isinstance(grup, str):
                    selected_groups.append(grup)

        selected_channels = []
        if isinstance(parsed_args.channels, list):
            for kanal in parsed_args.channels:
                if isinstance(kanal, str):
                    selected_channels.append(kanal)

        if len(selected_platforms) < 1:
            selected_platforms = self.DEFAULT_PLATFORMS
        if len(selected_groups) < 1:
            selected_groups = None
        if len(selected_channels) < 1:
            selected_channels = None
        return selected_platforms, selected_groups, selected_channels, None

    def _filter_videos(self, dataset: List[dict]):
        current_time = self.bot.now().timestamp()
        REGEX_FREECHAT = re.compile(r"(fr[e]{2}).*(chat)|(フリー?).*(チャッ?ト)", re.I)
        # Grace period of 24 hours in seconds
        grace_period = 60 * 60 * 24
        # Maximum of 6 months of schedule is allowed
        max_period = current_time + 60 * 60 * 24 * 30 * 6

        def _internal_check(data: dict):
            sched_start = data.get("timeData", {}).get("scheduledStartTime")
            if sched_start is not None:
                sched_start += grace_period
                if current_time > sched_start + grace_period:
                    return False
                if sched_start > max_period:
                    return False
            title = data["title"]
            match_title = re.findall(REGEX_FREECHAT, title)
            if len(match_title) > 0:
                return False
            return True

        return list(filter(_internal_check, dataset))

    @_ayaya_vtubermain.command("live", aliases=["lives"])
    async def _ayaya_vtuberlive(self, ctx: naoTimesContext, *, args: str = ""):
        is_guild, can_paginate, can_custom_emote = self._check_bot_perms(ctx)
        if not is_guild or not can_paginate:
            return await ctx.send("Hanya bisa dijalankan di sebuah Peladen")
        if not can_paginate:
            perms_need = ["Manage Messages", "Read Message History", "Add Reactions", "Embed Links"]
            err_msg = "Bot tidak dapat memberikan hasil karena kekurangan "
            err_msg += "salah satu permission berikut:\n"
            err_msg += "\n".join(perms_need)
            return await ctx.send(err_msg)
        parsed_args = await LiveConverter.convert(ctx, args)
        if isinstance(parsed_args, str):
            error_args = quote(parsed_args, True, "py")
            return await ctx.send(error_args)

        selected_platforms, selected_groups, selected_channels, err_msg = await self._parse_argument(
            parsed_args
        )
        if err_msg is not None:
            return await ctx.send(err_msg)

        self.logger.info("Querying ihaAPI lives data...")
        result = await self._paginate_query(
            "VTuberLive",
            variables={
                "platforms": selected_platforms,
                "groups": selected_groups,
                "chIds": selected_channels,
            },
            base_path="vtuber.live",
        )
        result: vtmodel.VTuberLiveItems = self._filter_videos(result)
        if len(result) < 1:
            return await ctx.send("Tidak ada VTuber yang terdaftar di database sedang live.")

        grouped_results: Dict[str, List[vtmodel.VTuberLiveItems]] = self._group_by(result, "platform")
        total_platforms = len(list(grouped_results.keys()))
        if total_platforms < 1:
            return await ctx.send("Tidak ada VTuber yang terdaftar di database sedang live.")

        base_emotes: List[Union[str, disnake.PartialEmoji]] = []
        if not can_custom_emote:
            base_emotes = self.SubtituteEmote[:total_platforms]
        for platform in list(grouped_results.keys()):
            if platform == "youtube":
                base_emotes.append(self.NiceEmote[0])
            elif platform == "twitch":
                base_emotes.append(self.NiceEmote[1])
            elif platform == "twitcasting":
                base_emotes.append(self.NiceEmote[2])
            elif platform == "mildom":
                base_emotes.append(self.NiceEmote[3])
            elif platform == "bilibili":
                base_emotes.append(self.NiceEmote[4])

        def _generate_base_embed(dataset: Dict[str, str]):
            embed = disnake.Embed(title="VTubers Lives", color=0x19212D)
            embed_value = []
            for pos, platform in enumerate(dataset.keys()):
                embed_value.append(f"{base_emotes[pos]} **{platform.capitalize()}**")
            embed.description = "Pilih platform yang ingin diliat:\n" + "\n".join(embed_value)
            return embed

        platform_gen = partial(
            self._generator_lives, predicate=self._generate_video_embed, base_emotes=base_emotes, ctx=ctx
        )
        main_gen = DiscordPaginator(self.bot, ctx, [grouped_results])
        main_gen.remove_at_trashed = False
        main_gen.set_generator(_generate_base_embed)
        for emote in base_emotes:
            main_gen.add_handler(emote, lambda x: True, platform_gen)
        await main_gen.paginate(30.0, None)

    @_ayaya_vtubermain.command("jadwal", aliases=["schedule", "schedules", "upcoming"])
    async def _ayaya_vtuberschedule(self, ctx: naoTimesContext, *, args: str = ""):
        is_guild, can_paginate, can_custom_emote = self._check_bot_perms(ctx)
        if not is_guild or not can_paginate:
            return await ctx.send("Hanya bisa dijalankan di sebuah Peladen")
        if not can_paginate:
            perms_need = ["Manage Messages", "Read Message History", "Add Reactions", "Embed Links"]
            err_msg = "Bot tidak dapat memberikan hasil karena kekurangan "
            err_msg += "salah satu permission berikut:\n"
            err_msg += "\n".join(perms_need)
            return await ctx.send(err_msg)
        parsed_args = await ScheduleConverter.convert(ctx, args)
        if isinstance(parsed_args, str):
            error_args = quote(parsed_args, True, "py")
            return await ctx.send(error_args)

        selected_platforms, selected_groups, selected_channels, err_msg = await self._parse_argument(
            parsed_args
        )
        if err_msg is not None:
            return await ctx.send(err_msg)

        self.logger.info("Querying ihaAPI lives data...")
        result = await self._paginate_query(
            "VTuberUpcoming",
            variables={
                "platforms": selected_platforms,
                "groups": selected_groups,
                "chIds": selected_channels,
            },
            base_path="vtuber.upcoming",
        )
        result = self._filter_videos(result)
        if len(result) < 1:
            return await ctx.send("Tidak ada jadwal terbaru untuk VTuber yang terdaftar.")

        grouped_results = self._group_by(result, "platform")
        total_platforms = len(list(grouped_results.keys()))
        if total_platforms < 1:
            return await ctx.send("Tidak ada jadwal terbaru untuk VTuber yang terdaftar.")

        base_emotes: List[Union[str, disnake.PartialEmoji]] = []
        if not can_custom_emote:
            base_emotes = self.SubtituteEmote[:total_platforms]
        for platform in list(grouped_results.keys()):
            if platform == "youtube":
                base_emotes.append(self.NiceEmote[0])
            elif platform == "twitch":
                base_emotes.append(self.NiceEmote[1])
            elif platform == "twitcasting":
                base_emotes.append(self.NiceEmote[2])
            elif platform == "mildom":
                base_emotes.append(self.NiceEmote[3])
            elif platform == "bilibili":
                base_emotes.append(self.NiceEmote[4])

        def _generate_base_embed(dataset: dict):
            embed = disnake.Embed(title="Jadwal Streams", color=0x19212D)
            embed_value = []
            for pos, platform in enumerate(dataset.keys()):
                embed_value.append(f"{base_emotes[pos]} **{platform.capitalize()}**")
            embed.description = "Pilih platform yang ingin diliat:\n" + "\n".join(embed_value)
            return embed

        platform_gen = partial(
            self._generator_lives, predicate=self._generate_video_embed, base_emotes=base_emotes, ctx=ctx
        )
        main_gen = DiscordPaginator(self.bot, ctx, [grouped_results])
        main_gen.remove_at_trashed = False
        main_gen.set_generator(_generate_base_embed)
        for emote in base_emotes:
            main_gen.add_handler(emote, lambda x: True, platform_gen)
        await main_gen.paginate(30.0, None)

    @_ayaya_vtubermain.command("channel", aliases=["channels", "kanal"])
    async def _ayaya_vtuberchannel(self, ctx: naoTimesContext, *, args: str = ""):
        is_guild, can_paginate, can_custom_emote = self._check_bot_perms(ctx)
        if not is_guild or not can_paginate:
            return await ctx.send("Hanya bisa dijalankan di sebuah Peladen")
        if not can_paginate:
            perms_need = ["Manage Messages", "Read Message History", "Add Reactions", "Embed Links"]
            err_msg = "Bot tidak dapat memberikan hasil karena kekurangan "
            err_msg += "salah satu permission berikut:\n"
            err_msg += "\n".join(perms_need)
            return await ctx.send(err_msg)
        parsed_args = await ChannelConverter.convert(ctx, args)
        if isinstance(parsed_args, str):
            error_args = quote(parsed_args, True, "py")
            return await ctx.send(error_args)

        selected_platforms, selected_groups, selected_channels, err_msg = await self._parse_argument(
            parsed_args
        )
        if err_msg is not None:
            return await ctx.send(err_msg)

        self.logger.info("Querying ihaAPI channels data...")
        result = await self._paginate_query(
            "VTuberChannels",
            variables={
                "platforms": selected_platforms,
                "groups": selected_groups,
                "chIds": selected_channels,
            },
            base_path="vtuber.channels",
        )
        if len(result) < 1:
            return await ctx.send("Tidak ada VTuber yang terdaftar.")

        grouped_results = self._group_by(result, "platform")
        total_platforms = len(list(grouped_results.keys()))
        if total_platforms < 1:
            return await ctx.send("Tidak ada VTuber yang terdaftar.")

        base_emotes: List[Union[str, disnake.PartialEmoji]] = []
        if not can_custom_emote:
            base_emotes = self.SubtituteEmote[:total_platforms]
        for platform in list(grouped_results.keys()):
            if platform == "youtube":
                base_emotes.append(self.NiceEmote[0])
            elif platform == "twitch":
                base_emotes.append(self.NiceEmote[1])
            elif platform == "twitcasting":
                base_emotes.append(self.NiceEmote[2])
            elif platform == "mildom":
                base_emotes.append(self.NiceEmote[3])
            elif platform == "bilibili":
                base_emotes.append(self.NiceEmote[4])

        def _generate_base_embed(dataset: dict):
            embed = disnake.Embed(title="Kanal VTuber", color=0x19212D)
            embed_value = []
            for pos, platform in enumerate(dataset.keys()):
                embed_value.append(f"{base_emotes[pos]} **{platform.capitalize()}**")
            embed.description = "Pilih platform yang ingin diliat:\n" + "\n".join(embed_value)
            return embed

        platform_gen = partial(
            self._generator_lives, predicate=self._generate_channel_embed, base_emotes=base_emotes, ctx=ctx
        )
        main_gen = DiscordPaginator(self.bot, ctx, [grouped_results])
        main_gen.remove_at_trashed = False
        main_gen.set_generator(_generate_base_embed)
        for emote in base_emotes:
            main_gen.add_handler(emote, lambda x: True, platform_gen)
        await main_gen.paginate(30.0, None)

    @_ayaya_vtubermain.command(
        "grup", aliases=["group", "groups", "org", "orgs", "orgz", "organization", "organizations"]
    )
    async def _ayaya_vtubergroup(self, ctx: naoTimesContext):
        result = await self.bot.ihaapi.query(VTUBER_QUERY_OBJECT, {}, "VTuberGroups")
        real_result = complex_walk(result.data, "vtuber.groups.items")
        if not real_result:
            return await ctx.send("Tidak ada VTuber yang terdaftar!")

        embed = disnake.Embed(title="VTuber Groups/Organizations", color=0x146B74)
        properly_named = []
        for res in real_result:
            group_name = GROUPS_NAME_MAPPINGS.get(res)
            if group_name is None:
                group_name = res.capitalize()
            group_txt = f"- **{group_name}** [ID: `{res}`]"
            properly_named.append(group_txt)
        embed.set_author(
            name="VTuber API",
            url="https://vtuber.ihateani.me/lives",
            icon_url="https://vtuber.ihateani.me/assets/favicon.png",
        )
        embed.set_thumbnail(url="https://vtuber.ihateani.me/assets/favicon.png")
        embed.description = "\n".join(properly_named)
        embed.add_field(
            name="Info",
            value="Gunakan bagian ID di command lain, contoh `Hololive Indonesia (ID: hololiveid)`\n"
            "Maka IDnya adalah `hololiveid` gunakan itu untuk parameter `-g` atau `--group`",
        )
        embed.set_footer(
            text="Diprakasai oleh ihaAPI",
            icon_url="https://vtuber.ihateani.me/assets/favicon.png",
        )
        await ctx.send(embed=embed)


def setup(bot: naoTimesBot):
    bot.add_cog(AyayaVTuber(bot))
