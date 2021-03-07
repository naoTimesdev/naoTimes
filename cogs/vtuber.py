import functools as ft
import logging
from datetime import datetime, timezone, timedelta
from typing import Dict, List

import discord
from aiographql.client import GraphQLClient, GraphQLRequest
from discord.ext import commands
from nthelper.bot import naoTimesBot
from nthelper.cmd_args import Arguments, CommandArgParse
from nthelper.utils import DiscordPaginator, HelpGenerator

VTUBER_QUERY_OBJECT = """
query VTuberLive($cursor:String,$platforms:[PlatformName],$chIds:[ID],$groups:[String]) {
    vtuber {
        live(cursor:$cursor,limit:75,platforms:$platforms,channel_id:$chIds,groups:$groups) {
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
        upcoming(cursor:$cursor,limit:75,platforms:$platforms,channel_id:$chIds,groups:$groups) {
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
        channels(cursor:$cursor,limit:75,platforms:$platforms,id:$chIds,groups:$groups,sort_by:"name") {
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
vt_platforms_kwargs = {
    "required": False,
    "dest": "platforms",
    "action": "append",
    "help": "Filter hasil ke platform tertentu, dapat diulang.\nEx: -P youtube -P twitch",
    "choices": ["youtube", "twitch", "twitcasting", "mildom"],
}
vt_groups_args = ["-g", "--group"]
vt_groups_kwargs = {
    "required": False,
    "dest": "groups",
    "action": "append",
    "help": "Filter untuk organisasi atau grup tertentu, untuk mendapatkan "
    "listnya, dapat menggunakan perintah '!vtuber grup'."
    "Dapat diulang seperti --platform",
}
vt_chids_args = ["-c", "--channel-id"]
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
schedule_args = Arguments("vtuber jadwal")
schedule_args.add_args(*vt_platforms_args, **vt_platforms_kwargs)
schedule_args.add_args(*vt_groups_args, **vt_groups_kwargs)
schedule_args.add_args(*vt_chids_args, **vt_chids_kwargs)
channel_args = Arguments("vtuber channel")
channel_args.add_args(*vt_platforms_args, **vt_platforms_kwargs)
channel_args.add_args(*vt_groups_args, **vt_groups_kwargs)
channel_args.add_args(*vt_chids_args, **vt_chids_kwargs)
live_converter = CommandArgParse(live_args)
schedule_converter = CommandArgParse(schedule_args)
channel_converter = CommandArgParse(channel_args)


def traverse(data: dict, nots: str) -> dict:
    for n in nots.split("."):
        if n.isdigit():
            n = int(n, 10)
        data = data[n]
    return data


class VTuberAPI(commands.Cog):

    __COLOR_WEB_DATA = {
        "youtube": {
            "t": "YouTube",
            "c": 0xFF0000,
            "b": "https://youtube.com/watch?v=",
            "cb": "https://youtube.com/channel/",
            "fi": "https://s.ytimg.com/yts/img/favicon_144-vfliLAfaB.png",
        },
        "bilibili": {
            "t": "Bilibili",
            "c": 0x23ADE5,
            "b": "https://live.bilibili.com/",
            "cb": "https://space.bilibili.com/",
            "fi": "https://logodix.com/logo/1224389.png",
        },
        "twitch": {
            "t": "Twitch",
            "c": 0x9147FF,
            "b": "https://www.twitch.tv/",
            "cb": "https://twitch.tv/",
            "fi": "https://p.n4o.xyz/i/twitchlogo.png",
        },
        "twitcasting": {
            "t": "Twitcasting",
            "c": 0x280FC,
            "b": "https://twitcasting.tv/",
            "cb": "https://twitcasting.tv/",
            "fi": "https://twitcasting.tv/img/icon192.png",
        },
        "mildom": {
            "t": "Mildom",
            "c": 0x38CCE3,
            "b": "https://www.mildom.com/",
            "cb": "https://www.mildom.com/profile/",
            "fi": "https://www.mildom.com/assets/logo.png",
        },
    }

    __WIB_TZ = timezone(timedelta(hours=7))

    def __init__(self, bot: naoTimesBot):
        self.bot = bot
        self.logger = logging.getLogger("cogs.vtuber.VTuberAPI")

        self.client = GraphQLClient(endpoint="https://api.ihateani.me/v2/graphql")
        self.request = GraphQLRequest(query=VTUBER_QUERY_OBJECT)
        self.query: GraphQLClient.query = ft.partial(self.client.query, request=self.request)

    @staticmethod
    def is_msg_empty(msg: str, thr: int = 3) -> bool:
        split_msg: List[str] = msg.split(" ")
        split_msg = [m for m in split_msg if m != ""]
        if len(split_msg) < thr:
            return True
        return False

    @staticmethod
    def _group_by(dataset: List[dict], by: str) -> dict:
        grouped: Dict[str, List[dict]] = {}
        for data in dataset:
            key = traverse(data, by)
            if not isinstance(key, str):
                raise ValueError(
                    f"The selected key is not a string, expected string type but got {type(key).__name__}"
                )
            if key not in grouped:
                grouped[key] = []
            grouped[key].append(data)
        return grouped

    @commands.group("vtuber")
    @commands.guild_only()
    @commands.bot_has_guild_permissions(
        manage_messages=True, embed_links=True, read_message_history=True, add_reactions=True,
    )
    async def vtuber_main(self, ctx: commands.Context):
        msg = ctx.message.content
        if ctx.invoked_subcommand is None:
            if not self.is_msg_empty(msg, 2):
                return await ctx.send("Tidak dapat menemukan bantuan perintah tersebut.")
            helpcmd = HelpGenerator(
                self.bot,
                "vtuber",
                desc="Informasi stream VTuber dan sebagainya!\nSemua command menggunakan sistem `argparse`\n"
                "Silakan tambah `-h` setelah salah satu command untuk "
                f"melihat bantuan tambahan (ex: `{self.bot.prefix}vtuber live -h`)",
            )
            await helpcmd.generate_field("vtuber", desc="Memunculkan perintah ini")
            await helpcmd.generate_field("vtuber live", desc="Melihat VTuber yang sedang live")
            await helpcmd.generate_field("vtuber jadwal", desc="Melihat jadwal stream VTuber")
            await helpcmd.generate_field("vtuber channel", desc="Melihat informasi sebuah channel")
            await helpcmd.generate_field(
                "vtuber grup", desc="Melihat list grup atau organisasi yang terdaftar"
            )
            await helpcmd.generate_aliases()
            await ctx.send(embed=helpcmd.get())

    async def _paginate_query(self, op: str, variables: dict, data_path: str):
        cursor = None
        is_error = is_incomplete = False
        full_data = []
        while True:
            variables["cursor"] = cursor
            result = await self.client.query(request=self.request, operation=op, variables=variables)
            if result.errors:
                if full_data:
                    is_incomplete = True
                is_error = True
                break
            main_data = traverse(result.data, data_path)
            full_data.extend(main_data["items"])
            if not main_data["pageInfo"]["hasNextPage"]:
                break
            cursor: str = main_data["pageInfo"]["nextCursor"]
            if cursor is None:
                break
            if len(cursor.replace(" ", "")) < 1:
                break
        return full_data, is_error, is_incomplete

    async def _generate_video_embed(self, dataset: dict, pos: int, total: int):
        platform_info = self.__COLOR_WEB_DATA.get(dataset["platform"])
        title_fmt = platform_info["t"]
        video_id = dataset["id"]
        ch_id = dataset["channel"]["id"]
        if dataset["platform"] in ["twitcasting", "twitch", "mildom"]:
            video_id = dataset["channel"]["id"]
        elif dataset["platform"] == "bilibili":
            video_id = dataset["room_id"]
        if dataset["is_premiere"]:
            title_fmt += " Premiere"
        else:
            title_fmt += " Stream"
        if dataset["is_member"]:
            title_fmt += " (Member-Only)"
        title_fmt += f" [{pos + 1}/{total}]"
        ch_data = dataset["channel"]
        ch_name = ch_data.get("en_name", ch_data.get("name", "Tidak diketahui"))
        group_name = GROUPS_NAME_MAPPINGS.get(dataset["group"])
        if group_name is None:
            group_name = dataset["group"].capitalize()
        group_txt = f"{group_name} `(ID: {dataset['group']})`"
        parsed_utc_start = datetime.fromtimestamp(dataset["timeData"]["startTime"], tz=timezone.utc)
        start_time_fmt = parsed_utc_start.astimezone(tz=self.__WIB_TZ).strftime("%a, %d %b %Y %H:%M:%S WIB")
        description_data = ""
        description_data += f"**{dataset['title']}**\n\n"
        description_data += f"**Streamer**: `{ch_name}`\n"
        description_data += f"**Grup atau Organisasi**: {group_txt}\n"
        description_data += f"**Mulai dari**: `{start_time_fmt}`\n\n"
        description_data += f"[**`Tonton`**]({platform_info['b']}{video_id}) **\|\|** [**`Lihat Kanal`**]({platform_info['cb']}{ch_id})"  # noqa: W605,E501
        embed = discord.Embed(color=platform_info["c"], timestamp=parsed_utc_start)
        embed.set_author(name=title_fmt, url=f"{platform_info['b']}{video_id}", icon_url=platform_info["fi"])
        embed.set_thumbnail(url=dataset["channel"]["image"])
        embed.set_image(url=dataset["thumbnail"])
        embed.description = description_data
        embed.set_footer(
            text=f"ID: {video_id} | {platform_info['t']} | Diprakasai oleh ihaAPI",
            icon_url="https://vtuber.ihateani.me/assets/favicon.png",
        )
        return embed

    @staticmethod
    def _create_stats_text(stats_data: dict):
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

    async def _generate_channel_embed(self, dataset: dict, pos: int, total: int):
        platform_info = self.__COLOR_WEB_DATA.get(dataset["platform"])
        title_fmt = "Kanal " + platform_info["t"]
        title_fmt += f" [{pos + 1}/{total}]"
        group_name = GROUPS_NAME_MAPPINGS.get(dataset["group"])
        ch_id = dataset["id"]
        if group_name is None:
            group_name = dataset["group"].capitalize()
        group_txt = f"{group_name} `(ID: {dataset['group']})`"
        ch_name = dataset.get("en_name", dataset.get("name", "Tidak diketahui"))
        descriptions = ""
        descriptions += f"**{ch_name}**\n\n"
        descriptions += f"**Grup atau Organisasi**: {group_txt}\n"
        if dataset["publishedAt"]:
            try:
                pub_at_dt = datetime.strptime(dataset["publishedAt"], "%Y-%m-%dT%H:%M:%S.%fZ").replace(
                    tzinfo=timezone.utc
                )
            except Exception:
                try:
                    pub_at_dt = datetime.strptime(dataset["publishedAt"], "%Y-%m-%dT%H:%M:%SZ").replace(
                        tzinfo=timezone.utc
                    )
                except Exception:
                    pub_at_dt = None
            if pub_at_dt is not None:
                pub_at = pub_at_dt.astimezone(tz=self.__WIB_TZ).strftime("%a, %d %b %Y %H:%M:%S WIB")
                descriptions += f"**Kanal dibuat pada**: `{pub_at}`\n"
        stats_text = self._create_stats_text(dataset["statistics"])
        descriptions += "\n**Statistik**:\n"
        descriptions += stats_text + "\n"
        descriptions += f"\n[**`Lihat Kanal`**]({platform_info['cb']}{ch_id})"  # noqa: W605,E501

        embed = discord.Embed(color=platform_info["c"])
        embed.set_author(name=title_fmt, url=f"{platform_info['cb']}{ch_id}", icon_url=platform_info["fi"])
        embed.description = descriptions
        embed.set_thumbnail(url=dataset["image"])
        embed.set_footer(
            text=f"ID: {ch_id} | {platform_info['t']} | Diprakasai oleh ihaAPI",
            icon_url="https://vtuber.ihateani.me/assets/favicon.png",
        )
        return embed

    @vtuber_main.command(name="live", aliases=["lives"])
    async def vtuber_live(self, ctx: commands.Context, *, args=""):
        print(args)
        args = await live_converter.convert(ctx, args)
        if isinstance(args, str):
            args = f"```py\n{args}\n```"
            return await ctx.send(args)

        DEFAULT_PLATFORMS = ["youtube", "twitch", "twitcasting", "mildom"]

        selected_platforms = []
        if isinstance(args.platforms, list):
            for platform in args.platforms:
                if platform.lower() not in DEFAULT_PLATFORMS:
                    return await ctx.send(f"Platform `{platform}` tidak ada di database.")
                selected_platforms.append(platform.lower())

        groups_data = []
        if isinstance(args.groups, list):
            for grup in args.groups:
                if isinstance(grup, str):
                    groups_data.append(grup)

        channels_data = []
        if isinstance(args.channels, list):
            for kanal in args.channels:
                if isinstance(kanal, str):
                    channels_data.append(kanal)

        if len(selected_platforms) < 1:
            selected_platforms = DEFAULT_PLATFORMS

        if len(groups_data) < 1:
            groups_data = None

        if len(channels_data) < 1:
            channels_data = None

        result, is_error, is_incomplete = await self._paginate_query(
            op="VTuberLive",
            variables={"platforms": selected_platforms, "groups": groups_data, "chIds": channels_data},
            data_path="vtuber.live",
        )
        if is_error and not is_incomplete:
            return await ctx.send("Terjadi kesalahan ketika mencoba menghubungi server.")
        if not is_error and len(result) < 1:
            return await ctx.send("Tidak ada VTuber yang terdaftar di database sedang live.")

        grouped_results = self._group_by(result, "platform")
        total_platforms = len(list(grouped_results.keys()))
        if total_platforms < 1:
            return await ctx.send("Tidak ada VTuber yang terdaftar di database sedang live.")

        emote_list = [
            "1️⃣",
            "2️⃣",
            "3️⃣",
            "4️⃣",
            "5️⃣",
        ]

        async def generate_main(_data):
            embed = discord.Embed(title="VTubers Lives", color=0x19212D)
            val = ""
            for n, data in enumerate(grouped_results.keys()):
                val += "{em} **{fmt}**\n".format(em=emote_list[n], fmt=data.capitalize())
            embed.add_field(name="List Platform", value=val)
            return embed

        async def platform_paginator(datasets, _p, message: discord.Message, emote: str):
            try:
                emote_pos = emote_list.index(emote)
            except ValueError:
                return None, message
            platforms_data = datasets[0][list(datasets[0].keys())[emote_pos]]
            await message.clear_reactions()
            vid_gen_fun = ft.partial(self._generate_video_embed, total=len(platforms_data))
            plat_gen = DiscordPaginator(self.bot, ctx)
            plat_gen.checker()
            plat_gen.set_generator(vid_gen_fun, True)
            timeout = await plat_gen.start(platforms_data, 30.0, message)
            return None, message, timeout

        main_gen = DiscordPaginator(self.bot, ctx, emote_list[:total_platforms], True)
        main_gen.checker()
        main_gen.set_generator(generate_main)
        for n, _ in enumerate(list(grouped_results.keys())):
            main_gen.set_handler(n, lambda x, y: True, platform_paginator)
        await main_gen.start([grouped_results], 30.0, None, True)

    @vtuber_main.command(name="jadwal", aliases=["schedule", "schedules", "upcoming"])
    async def vtuber_schedules(self, ctx: commands.Context, *, args=""):
        args = await schedule_converter.convert(ctx, args)
        if isinstance(args, str):
            args = f"```py\n{args}\n```"
            return await ctx.send(args)

        DEFAULT_PLATFORMS = ["youtube", "twitch"]

        selected_platforms = []
        if isinstance(args.platforms, list):
            for platform in args.platforms:
                if platform.lower() not in DEFAULT_PLATFORMS:
                    return await ctx.send(
                        f"Platform `{platform}` tidak bisa digunakan di command ini "
                        "(Hanya bisa `twitch` dan `youtube`)."
                    )
                selected_platforms.append(platform.lower())

        groups_data = []
        if isinstance(args.groups, list):
            for grup in args.groups:
                if isinstance(grup, str):
                    groups_data.append(grup)

        channels_data = []
        if isinstance(args.channels, list):
            for kanal in args.channels:
                if isinstance(kanal, str):
                    channels_data.append(kanal)

        if len(selected_platforms) < 1:
            selected_platforms = DEFAULT_PLATFORMS

        if len(groups_data) < 1:
            groups_data = None

        if len(channels_data) < 1:
            channels_data = None

        result, is_error, is_incomplete = await self._paginate_query(
            op="VTuberUpcoming",
            variables={"platforms": selected_platforms, "groups": groups_data, "chIds": channels_data},
            data_path="vtuber.upcoming",
        )
        if is_error and not is_incomplete:
            return await ctx.send("Terjadi kesalahan ketika mencoba menghubungi server.")
        if not is_error and len(result) < 1:
            return await ctx.send("Tidak ada jadwal terbaru untuk VTuber yang terdaftar.")

        grouped_results = self._group_by(result, "platform")
        total_platforms = len(list(grouped_results.keys()))
        if total_platforms < 1:
            return await ctx.send("Tidak ada jadwal terbaru untuk VTuber yang terdaftar.")

        emote_list = [
            "1️⃣",
            "2️⃣",
            "3️⃣",
            "4️⃣",
            "5️⃣",
        ]

        async def generate_main(_data):
            embed = discord.Embed(title="Jadwal Streams", color=0x19212D)
            val = ""
            for n, data in enumerate(grouped_results.keys()):
                val += "{em} **{fmt}**\n".format(em=emote_list[n], fmt=data.capitalize())
            embed.add_field(name="List Platform", value=val)
            return embed

        async def platform_paginator(datasets, _p, message: discord.Message, emote: str):
            try:
                emote_pos = emote_list.index(emote)
            except ValueError:
                return None, message
            platforms_data = datasets[0][list(datasets[0].keys())[emote_pos]]
            await message.clear_reactions()
            vid_gen_fun = ft.partial(self._generate_video_embed, total=len(platforms_data))
            plat_gen = DiscordPaginator(self.bot, ctx)
            plat_gen.checker()
            plat_gen.set_generator(vid_gen_fun, True)
            timeout = await plat_gen.start(platforms_data, 30.0, message)
            return None, message, timeout

        main_gen = DiscordPaginator(self.bot, ctx, emote_list[:total_platforms], True)
        main_gen.checker()
        main_gen.set_generator(generate_main)
        for n, _ in enumerate(list(grouped_results.keys())):
            main_gen.set_handler(n, lambda x, y: True, platform_paginator)
        await main_gen.start([grouped_results], 30.0, None, True)

    @vtuber_main.command(name="channel", aliases=["channels", "kanal"])
    async def vtuber_channel(self, ctx: commands.Context, *, args=""):
        args = await channel_converter.convert(ctx, args)
        if isinstance(args, str):
            args = f"```py\n{args}\n```"
            return await ctx.send(args)

        DEFAULT_PLATFORMS = ["youtube", "twitch", "twitcasting", "mildom"]

        selected_platforms = []
        if isinstance(args.platforms, list):
            for platform in args.platforms:
                if platform.lower() not in DEFAULT_PLATFORMS:
                    return await ctx.send(f"Platform `{platform}` tidak ada di database.")
                selected_platforms.append(platform.lower())

        groups_data = []
        if isinstance(args.groups, list):
            for grup in args.groups:
                if isinstance(grup, str):
                    groups_data.append(grup)

        channels_data = []
        if isinstance(args.channels, list):
            for kanal in args.channels:
                if isinstance(kanal, str):
                    channels_data.append(kanal)

        if len(selected_platforms) < 1:
            selected_platforms = DEFAULT_PLATFORMS

        if len(groups_data) < 1:
            groups_data = None

        if len(channels_data) < 1:
            channels_data = None

        result, is_error, is_incomplete = await self._paginate_query(
            op="VTuberChannels",
            variables={"platforms": selected_platforms, "groups": groups_data, "chIds": channels_data},
            data_path="vtuber.channels",
        )
        if is_error and not is_incomplete:
            return await ctx.send("Terjadi kesalahan ketika mencoba menghubungi server.")
        if not is_error and len(result) < 1:
            return await ctx.send("Tidak ada VTuber yang terdaftar di database sedang live.")

        grouped_results = self._group_by(result, "platform")
        total_platforms = len(list(grouped_results.keys()))
        if total_platforms < 1:
            return await ctx.send("Tidak ada VTuber yang terdaftar di database sedang live.")

        emote_list = [
            "1️⃣",
            "2️⃣",
            "3️⃣",
            "4️⃣",
            "5️⃣",
        ]

        async def generate_main(_data):
            embed = discord.Embed(title="Kanal VTubers", color=0x19212D)
            val = ""
            for n, data in enumerate(grouped_results.keys()):
                val += "{em} **{fmt}**\n".format(em=emote_list[n], fmt=data.capitalize())
            embed.add_field(name="List Platform", value=val)
            return embed

        async def platform_paginator(datasets, _p, message: discord.Message, emote: str):
            try:
                emote_pos = emote_list.index(emote)
            except ValueError:
                return None, message
            platforms_data = datasets[0][list(datasets[0].keys())[emote_pos]]
            await message.clear_reactions()
            vid_gen_fun = ft.partial(self._generate_channel_embed, total=len(platforms_data))
            plat_gen = DiscordPaginator(self.bot, ctx)
            plat_gen.checker()
            plat_gen.set_generator(vid_gen_fun, True)
            timeout = await plat_gen.start(platforms_data, 30.0, message)
            return None, message, timeout

        main_gen = DiscordPaginator(self.bot, ctx, emote_list[:total_platforms], True)
        main_gen.checker()
        main_gen.set_generator(generate_main)
        for n, _ in enumerate(list(grouped_results.keys())):
            main_gen.set_handler(n, lambda x, y: True, platform_paginator)
        await main_gen.start([grouped_results], 30.0, None, True)

    @vtuber_main.command(
        name="grup", aliases=["group", "groups", "org", "orgs", "orgz", "organization", "organizations"]
    )
    async def vtuber_group(self, ctx: commands.Context):
        result = await self.client.query(request=self.request, operation="VTuberGroups")
        real_result = result.data["vtuber"]["groups"]["items"]
        embed = discord.Embed(title="VTuber Groups/Organizations", color=0x146B74)
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
            text="Diprakasai oleh ihaAPI", icon_url="https://vtuber.ihateani.me/assets/favicon.png",
        )
        await ctx.send(embed=embed)

    @vtuber_main.error
    async def vtbapi_error(self, ctx, error):
        if isinstance(error, commands.BotMissingPermissions):
            perms = ["Manage Messages", "Embed Links", "Read Message History", "Add Reactions"]
            await ctx.send("Bot tidak memiliki salah satu dari perms ini:\n" + "\n".join(perms))
        elif isinstance(error, commands.NoPrivateMessage):
            await ctx.send("Perintah ini hanya bisa dijalankan di server.")


def setup(bot: naoTimesBot):
    bot.add_cog(VTuberAPI(bot))
