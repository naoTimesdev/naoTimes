# -*- coding: utf-8 -*-

import asyncio
import logging
import random
import re
from functools import partial
from typing import Union

import discord
import discord.ext.commands as commands
import ujson

from nthelper.bot import naoTimesBot
from nthelper.utils import DiscordPaginator
from nthelper.vndbsocket import VNDBSockIOManager

vnlog = logging.getLogger("cogs.vndb")


def setup(bot):
    vnlog.debug("adding cogs...")
    bot.add_cog(VNDB(bot))


def bbcode_markdown(string: str) -> str:
    """Convert BBCode to Markdown"""
    if not string:
        return "-"
    regex_lists = {
        r"\[b\](.*)\[\\b\]": "**\\1**",
        r"\[i\](.*)\[\\i\]": "*\\1*",
        r"\[u\](.*)\[\\u\]": "__\\1__",
        r"\[s\](.*)\[\\s\]": "~~\\1~~",
        r"\[code\](.*)\[\\code\]": "`\\1`",
        r"\[quote\](.*)\[\\quote\]": "```\\1```",
        r"\[quote\=.+?\](.*)\[\\quote\]": "```\\1```",
        r"\[center\](.*)\[\\center\]": "\\1",
        r"\[color\=.+?\](.*)\[\\color\]": "\\1",
        r"\[img\](.*)\[\\img\]": "![\\1](\\1)",
        r"\[img=(.+?)\](.*)\[\\img\]": "![\\2](\\1)",
        r"\[url=(.+?)\]((?:.|\n)+?)\[\/url\]": "[\\2](\\1)",
        r"\[url\]((?:.|\n)+?)\[\/url\]": "[\\1](\\1)",
    }

    for pat, change in regex_lists.items():
        string = re.sub(pat, change, string, flags=re.MULTILINE | re.IGNORECASE)
    if len(string) > 1023:
        string = string[:1020] + "..."
    return string


async def fetch_vndb(search_string: str, VNconn: VNDBSockIOManager) -> Union[dict, str]:
    """Main searching function"""
    if not VNconn.loggedin:
        vnlog.info("Trying to authenticating connection...")
        try:
            await asyncio.wait_for(VNconn.async_login(), 15.0)
        except asyncio.TimeoutError:
            return "Koneksi timeout, tidak dapat terhubung dengan VNDB."
    if search_string.rstrip().strip().isdigit():
        m_ = "id"
        delim = "="
    else:
        m_ = "title"
        delim = "~"
    data = 'vn basic,relations,anime,details,tags,stats,screens ({m}{de}"{da}")'.format(  # noqa: E501
        m=m_, de=delim, da=search_string
    )

    vnlog.info(f"fetching: {search_string}")
    try:
        res = await asyncio.wait_for(VNconn.send_command_async("get", data), timeout=15.0)
    except asyncio.TimeoutError:
        return "Koneksi timeout, tidak dapat terhubung dengan VNDB."
    if isinstance(res, str) and res.startswith("results "):
        res = res.replace("results ", "")
        res = ujson.loads(res)

    duration_dataset = {
        1: "Sangat Pendek (< 2 Jam)",
        2: "Pendek (2 - 10 Jam)",
        3: "Menengah (10 - 30 Jam)",
        4: "Panjang (30 - 50 Jam)",
        5: "Sangat Panjang (> 50 Jam)",
        None: "Tidak diketahui",
    }

    platforms_dataset = {
        "win": "Windows",
        "ios": "iOS",
        "and": "Android",
        "psv": "PSVita",
        "swi": "Switch",
        "xb3": "XB360",
        "xbo": "XB1",
        "n3d": "3DS",
        "mac": "MacOS/OSX",
    }

    if "message" in res:
        vnlog.error(f"{search_string}:error occured: {res['message']}")
        return "Terdapat kesalahan ketika mencari."

    full_query_result = []
    total_data = res["num"]
    if total_data < 1:
        vnlog.warning(f"{search_string}: no results...")
        return "Tidak dapat menemukan sesuatu dengan judul/ID yang diberikan"

    vnlog.info(f"{search_string}: parsing results...")
    for d in res["items"]:
        title = d["title"]
        other_title = d["aliases"]
        vn_id = d["id"]

        durasi = d["length"]

        platforms_data = d["platforms"]
        plat: list = []
        if platforms_data:
            for p in platforms_data:
                if p in platforms_dataset:
                    plat.append(platforms_dataset[p])
                else:
                    plat.append(p.upper())
        else:
            plat.append("Tidak Diketahui")
        plat = ", ".join(plat)  # type: ignore

        rating = d["rating"]
        desc = bbcode_markdown(d["description"])
        img_ = d["image"]

        lang_ = []
        if d["languages"]:
            for la in d["languages"]:
                lang_.append(la.upper())
            lang_ = ", ".join(lang_)  # type: ignore
        else:
            lang_ = "Tidak diketahui"  # type: ignore

        if d["anime"]:
            anime_stat = "Ada"
        else:
            anime_stat = "Tidak"

        screens_ = []
        if d["screens"]:
            for s in d["screens"]:
                screens_.append(s["image"])

        relasi_ = []
        if d["relations"]:
            for r in d["relations"]:
                relasi_.append(r["title"] + " (" + str(r["id"]) + ")")
            relasi_ = "\n".join(relasi_)  # type: ignore
        else:
            relasi_ = "Tidak ada"  # type: ignore

        released = d["released"]

        dataset = {
            "title": title,
            "title_other": other_title,
            "released": released,
            "poster_img": img_,
            "synopsis": desc,
            "platforms": plat,
            "languages": lang_,
            "anime?": anime_stat,
            "duration": duration_dataset[durasi],
            "relations": relasi_,
            "link": "https://vndb.org/v{}".format(vn_id),
            "score": rating,
            "screenshot": screens_,
            "footer": "ID: {}".format(vn_id),
        }

        for k, v in dataset.items():
            if k == "screenshot":  # Skip screenshot checking
                continue
            elif k == "poster_img":
                if not v:
                    dataset[k] = "https://s.vndb.org/linkimg/vndb1.gif"
            else:
                if not v:
                    dataset[k] = "Tidak diketahui"

        full_query_result.append(dataset)
    return {"result": full_query_result, "data_total": total_data}


async def random_search(vndb_conn: VNDBSockIOManager):
    if not vndb_conn.loggedin:
        vnlog.info("Trying to authenticating connection...")
        try:
            await asyncio.wait_for(vndb_conn.async_login(), 15.0)
        except asyncio.TimeoutError:
            return "Koneksi timeout, tidak dapat terhubung dengan VNDB."
    vnlog.info("fetching database stats...")
    try:
        res = await asyncio.wait_for(vndb_conn.send_command_async("dbstats"), 15.0)
    except asyncio.TimeoutError:
        return "Koneksi timeout, tidak dapat terhubung dengan VNDB."
    if isinstance(res, str) and res.startswith("dbstats "):
        res = res.replace("dbstats ", "")
        res = ujson.loads(res)

    total_vn = res["vn"]
    rand = random.randint(1, total_vn)  # nosec
    vnlog.info(f"picked {rand}, fetching info...")
    result = await fetch_vndb(str(rand), vndb_conn)
    return result


class VNDB(commands.Cog):
    def __init__(self, bot: naoTimesBot):
        self.bot = bot
        self.conf = bot.botconf

        self.vnconn = bot.vndb_socket

    @staticmethod
    def _design_embed(data) -> discord.Embed:
        embed = discord.Embed(color=0x225588)

        embed.set_thumbnail(url=data["poster_img"])
        embed.set_author(
            name=data["title"], url=data["link"], icon_url="https://ihateani.me/o/vndbico.png",
        )
        embed.set_footer(text=data["footer"])

        embed.add_field(name="Nama Lain", value=data["title_other"], inline=True)
        embed.add_field(name="Durasi", value=data["duration"], inline=True)
        embed.add_field(name="Bahasa", value=data["languages"], inline=True)
        embed.add_field(name="Platform", value=data["platforms"], inline=True)
        embed.add_field(name="Rilis", value=data["released"], inline=True)
        embed.add_field(name="Skor", value=data["score"], inline=True)
        embed.add_field(name="Relasi (VNID)", value=data["relations"], inline=True)
        embed.add_field(name="Adaptasi Anime?", value=data["anime?"], inline=True)
        embed.add_field(name="Sinopsis", value=data["synopsis"], inline=False)
        return embed

    @staticmethod
    def _design_screenies(data, pos, real_data, total_screenshot) -> discord.Embed:
        embed = discord.Embed(color=0x225588, description="<{}>".format(data))
        embed.set_author(
            name=real_data["title"] + " ({}/{})".format(pos + 1, total_screenshot),
            url=real_data["link"],
            icon_url="https://ihateani.me/o/vndbico.png",
        )
        embed.set_image(url=data)
        return embed

    @commands.command(aliases=["visualnovel", "eroge", "vndb"])
    @commands.guild_only()
    @commands.bot_has_guild_permissions(
        manage_messages=True, embed_links=True, read_message_history=True, add_reactions=True,
    )
    async def vn(self, ctx, *, judul):
        if self.vnconn is None:
            return await ctx.send(
                "Perintah VNDB tidak bisa digunakan karena bot tidak diberikan informasi login untuk VNDB."
            )
        vnqres = await fetch_vndb(judul, self.vnconn)
        if isinstance(vnqres, str):
            return await ctx.send(vnqres)

        resdata = vnqres["result"]

        async def wrap_start_image(datasets, position, message):
            await message.clear_reactions()
            dataset = datasets[position]
            total_img = len(dataset["screenshot"])
            img_embed_gen = partial(self._design_screenies, total_screenshot=total_img, real_data=dataset)
            screen_gen = DiscordPaginator(self.bot, ctx)
            screen_gen.checker()
            screen_gen.set_generator(img_embed_gen, True)
            timeout = await screen_gen.start(dataset["screenshot"], 30.0, message)
            return None, message, timeout

        main_gen = DiscordPaginator(self.bot, ctx, extra_emotes=["📸"])
        main_gen.add_handler(lambda pos, data: len(data[pos]["screenshot"]) > 0, wrap_start_image)
        main_gen.set_generator(self._design_embed)
        await main_gen.start(resdata, 30.0)

    @commands.command(aliases=["randomvisualnovel", "randomeroge", "vnrandom"])
    @commands.bot_has_guild_permissions(
        manage_messages=True, embed_links=True, read_message_history=True, add_reactions=True,
    )
    async def randomvn(self, ctx):
        if self.vnconn is None:
            return await ctx.send(
                "Perintah VNDB tidak bisa digunakan karena bot tidak diberikan informasi login untuk VNDB."
            )
        vnqres = await random_search(self.vnconn)
        if isinstance(vnqres, str):
            return await ctx.send(vnqres)

        resdata = vnqres["result"]

        async def wrap_start_image(datasets, position, message):
            await message.clear_reactions()
            dataset = datasets[position]
            total_img = len(dataset["screenshot"])
            img_embed_gen = partial(self._design_screenies, total_screenshot=total_img, real_data=dataset)
            screen_gen = DiscordPaginator(self.bot, ctx)
            screen_gen.checker()
            screen_gen.set_generator(img_embed_gen, True)
            timeout = await screen_gen.start(dataset["screenshot"], 30.0, message)
            return None, message, timeout

        main_gen = DiscordPaginator(self.bot, ctx, extra_emotes=["📸"])
        main_gen.add_handler(lambda pos, data: len(data[pos]["screenshot"]) > 0, wrap_start_image)
        main_gen.set_generator(self._design_embed)
        await main_gen.start(resdata, 30.0)

    @vn.error
    @randomvn.error
    async def vndb_error(self, ctx, error):
        if isinstance(error, commands.BotMissingPermissions):
            perms = ["Manage Messages", "Embed Links", "Read Message History", "Add Reactions"]
            await ctx.send("Bot tidak memiliki salah satu dari perms ini:\n" + "\n".join(perms))
        elif isinstance(error, commands.NoPrivateMessage):
            await ctx.send("Perintah ini hanya bisa dijalankan di server.")
