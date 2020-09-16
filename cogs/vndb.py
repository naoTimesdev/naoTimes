# -*- coding: utf-8 -*-

import asyncio
import logging
import random
import re
import socket
import ssl
from typing import Union

import discord
import discord.ext.commands as commands

import ujson

vnlog = logging.getLogger("cogs.vndb")


def setup(bot):
    vnlog.debug("adding cogs...")
    bot.add_cog(VNDB(bot))


class VNDBSocket:
    """
    VNDB Socket Manager but it's asynchronous
    Base code shamelessly stolen from:
    https://github.com/ccubed/PyMoe/blob/master/Pymoe/VNDB/connection.py
    """

    def __init__(
        self, username=None, password=None, loop=None,
    ):
        self.clientvars = {
            "protocol": 1,
            "clientver": 2.0,
            "client": "naoTimes",
        }
        self.loggedin = False
        self.data_buffer = bytes(1024)
        self.sslcontext = ssl.SSLContext(ssl.PROTOCOL_TLSv1_2)
        self.sslcontext.verify_mode = ssl.CERT_REQUIRED
        self.sslcontext.check_hostname = True
        self.sslcontext.load_default_certs()
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sslwrap = self.sslcontext.wrap_socket(self.socket, server_hostname="api.vndb.org")
        self.sslwrap.connect(("api.vndb.org", 19535))
        # self.sslwrap.setblocking(False)
        self.loop: asyncio.AbstractEventLoop = loop
        if self.loop is None:
            self.loop = asyncio.get_event_loop()
        # self.login(username, password)

    def close(self):
        """
        Close the socket connection.
        """
        self.sslwrap.close()

    async def async_login(self, username, password):
        vars_ = self.clientvars
        if username and password:
            vars_["username"] = username
            vars_["password"] = password
            ret = await self.send_command_async("login", ujson.dumps(vars_))
            if not isinstance(ret, str):  # should just be 'Ok'
                if self.loggedin:
                    self.loggedin = False
            self.loggedin = True

    async def send_command_async(self, command, args=None):
        """
        Send a command to VNDB and then get the result.
        :param command: What command are we sending
        :param args: What are the json args for this command
        :return: Servers Response
        :rtype: Dictionary (See D11 docs on VNDB)
        """
        if args:
            if isinstance(args, str):
                final_command = command + " " + args + "\x04"
            else:
                # We just let ujson propogate the error here
                # if it can't parse the arguments
                final_command = command + " " + ujson.dumps(args) + "\x04"
        else:
            final_command = command + "\x04"
        await self.loop.sock_sendall(self.sslwrap, final_command.encode("utf-8"))
        return await self._recv_data_async()

    async def _recv_data_async(self):
        """
        Receieves data until we reach the \x04 and then returns it.
        :return: The data received
        """
        temp = ""
        while True:
            self.data_buffer = await self.loop.sock_recv(self.sslwrap, 1024)
            if "\x04" in self.data_buffer.decode("utf-8", "ignore"):
                temp += self.data_buffer.decode("utf-8", "ignore")
                break
            else:
                temp += self.data_buffer.decode("utf-8", "ignore")
                self.data_buffer = bytes(1024)
        temp = temp.replace("\x04", "")
        if "ok" in temp.lower():  # because login
            return temp
        else:
            return ujson.loads(temp.split(" ", 1)[1])


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


async def fetch_vndb(
    search_string: str, VNconn: Union[VNDBSocket, None] = None, bot_config: dict = {},
) -> Union[dict, str]:
    """Main searching function"""
    if not VNconn:
        vndb_login = bot_config["vndb"]
        if not vndb_login["username"] and not vndb_login["password"]:
            vnlog.warn("please provide login info if you want to use VNDB.")
            return "Perintah VNDB tidak bisa digunakan karena bot tidak diberikan informasi login untuk VNDB\nCek `config.json` untuk memastikannya."  # noqa: E501
        VNconn = VNDBSocket(vndb_login["username"], vndb_login["password"])
    if not VNconn.loggedin:
        await VNconn.async_login(vndb_login["username"], vndb_login["password"])
        if not VNconn.loggedin:  # Still no.
            vnlog.warn("failed to sign-in to VNDB.")
            return "Tidak dapat login dengan username dan password yang diberikan di `config.json` kontak owner bot untuk membenarkannya."  # noqa: E501
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
    res = await VNconn.send_command_async("get", data)
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
        vnlog.warn(f"{search_string}: no results...")
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
            for l in d["languages"]:
                lang_.append(l.upper())
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
    VNconn.close()
    return {"result": full_query_result, "data_total": total_data}


async def random_search(bot_config: dict):
    vndb_login = bot_config["vndb"]
    if not vndb_login["username"] and not vndb_login["password"]:
        vnlog.warn("please provide login info if you want to use VNDB.")
        return "Perintah VNDB tidak bisa digunakan karena bot tidak diberikan informasi login untuk VNDB\nCek `config.json` untuk memastikannya."  # noqa: E501
    VNconn = VNDBSocket(vndb_login["username"], vndb_login["password"])
    if not VNconn.loggedin:
        await VNconn.async_login(vndb_login["username"], vndb_login["password"])
        if not VNconn.loggedin:  # Still no.
            vnlog.warn("failed to sign-in to VNDB.")
            return "Tidak dapat login dengan username dan password yang diberikan di `config.json` kontak owner bot untuk membenarkannya."  # noqa: E501
    vnlog.info(f"fetching database stats...")
    res = await VNconn.send_command_async("dbstats")
    if isinstance(res, str) and res.startswith("dbstats "):
        res = res.replace("dbstats ", "")
        res = ujson.loads(res)

    total_vn = res["vn"]
    rand = random.randint(1, total_vn)
    vnlog.info(f"picked {rand}, fetching info...")
    result = await fetch_vndb(str(rand), VNconn)
    return result


class VNDB(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.conf = bot.botconf

    @commands.command(aliases=["visualnovel", "eroge", "vndb"])
    @commands.guild_only()
    async def vn(self, ctx, *, judul):
        vnqres = await fetch_vndb(judul, bot_config=self.conf)
        if isinstance(vnqres, str):
            return await ctx.send(vnqres)

        max_page = vnqres["data_total"]
        resdata = vnqres["result"]

        first_run = True
        screen_table = False
        num = 1
        num_ = 1
        while True:
            if first_run:
                data = resdata[num - 1]
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

                first_run = False
                msg = await ctx.send(embed=embed)

            reactmoji = []
            num__ = len(data["screenshot"])

            if screen_table:
                if num__ == 1 and num_ == 1:
                    pass
                elif num_ == 1:
                    reactmoji.append("⏩")
                elif num_ == num__:
                    reactmoji.append("⏪")
                elif num_ > 1 and num_ < num__:
                    reactmoji.extend(["⏪", "⏩"])
                reactmoji.append("✅")
            else:
                if max_page == 1 and num == 1:
                    pass
                elif num == 1:
                    reactmoji.append("⏩")
                elif num == max_page:
                    reactmoji.append("⏪")
                elif num > 1 and num < max_page:
                    reactmoji.extend(["⏪", "⏩"])
                if data["screenshot"]:
                    reactmoji.append("📸")

            for react in reactmoji:
                await msg.add_reaction(react)

            def check_react(reaction, user):
                if reaction.message.id != msg.id:
                    return False
                if user != ctx.message.author:
                    return False
                if str(reaction.emoji) not in reactmoji:
                    return False
                return True

            try:
                res, user = await self.bot.wait_for("reaction_add", timeout=30, check=check_react)
            except asyncio.TimeoutError:
                return await msg.clear_reactions()
            if user != ctx.message.author:
                pass
            elif "⏪" in str(res.emoji):
                if not screen_table:
                    num = num - 1
                data = resdata[num - 1]
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

                if screen_table:
                    # Reset embed
                    num_ = num_ - 1
                    data_ss = data["screenshot"][num_ - 1]
                    embed = discord.Embed(color=0x225588, description="<{}>".format(data_ss))
                    embed.set_author(
                        name=data["title"] + " ({}/{})".format(num_, num__),
                        url=data["link"],
                        icon_url="https://ihateani.me/o/vndbico.png",
                    )
                    embed.set_image(url=data_ss)

                await msg.clear_reactions()
                await msg.edit(embed=embed)
            elif "⏩" in str(res.emoji):
                if not screen_table:
                    num = num + 1
                data = resdata[num - 1]
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

                if screen_table:
                    # Reset embed
                    num_ = num_ + 1
                    data_ss = data["screenshot"][num_ - 1]
                    embed = discord.Embed(color=0x225588, description="<{}>".format(data_ss))
                    embed.set_author(
                        name=data["title"] + " ({}/{})".format(num_, num__),
                        url=data["link"],
                        icon_url="https://ihateani.me/o/vndbico.png",
                    )
                    embed.set_image(url=data_ss)

                await msg.clear_reactions()
                await msg.edit(embed=embed)
            elif "✅" in str(res.emoji):
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

                screen_table = False
                await msg.clear_reactions()
                await msg.edit(embed=embed)
            elif "📸" in str(res.emoji):
                data_ss = data["screenshot"][num_ - 1]
                embed = discord.Embed(color=0x225588, description="<{}>".format(data_ss))
                embed.set_author(
                    name=data["title"] + " ({}/{})".format(num_, num__),
                    url=data["link"],
                    icon_url="https://ihateani.me/o/vndbico.png",
                )
                embed.set_image(url=data_ss)

                screen_table = True
                await msg.clear_reactions()
                await msg.edit(embed=embed)

    @commands.command(aliases=["randomvisualnovel", "randomeroge", "vnrandom"])
    async def randomvn(self, ctx):
        vnqres = await random_search(self.conf)
        if isinstance(vnqres, str):
            return await ctx.send(vnqres)

        max_page = vnqres["data_total"]
        resdata = vnqres["result"]

        first_run = True
        screen_table = False
        num = 1
        num_ = 1
        while True:
            if first_run:
                data = resdata[num - 1]
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

                first_run = False
                msg = await ctx.send(embed=embed)

            reactmoji = []
            num__ = len(data["screenshot"])

            if screen_table:
                if num__ == 1 and num_ == 1:
                    pass
                elif num_ == 1:
                    reactmoji.append("⏩")
                elif num_ == num__:
                    reactmoji.append("⏪")
                elif num_ > 1 and num_ < num__:
                    reactmoji.extend(["⏪", "⏩"])
                reactmoji.append("✅")
            else:
                if max_page == 1 and num == 1:
                    pass
                elif num == 1:
                    reactmoji.append("⏩")
                elif num == max_page:
                    reactmoji.append("⏪")
                elif num > 1 and num < max_page:
                    reactmoji.extend(["⏪", "⏩"])
                if data["screenshot"]:
                    reactmoji.append("📸")

            for react in reactmoji:
                await msg.add_reaction(react)

            def check_react(reaction, user):
                if reaction.message.id != msg.id:
                    return False
                if user != ctx.message.author:
                    return False
                if str(reaction.emoji) not in reactmoji:
                    return False
                return True

            try:
                res, user = await self.bot.wait_for("reaction_add", timeout=30, check=check_react)
            except asyncio.TimeoutError:
                return await msg.clear_reactions()
            if user != ctx.message.author:
                pass
            elif "⏪" in str(res.emoji):
                if not screen_table:
                    num = num - 1
                data = resdata[num - 1]
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

                if screen_table:
                    # Reset embed
                    num_ = num_ - 1
                    data_ss = data["screenshot"][num_ - 1]
                    embed = discord.Embed(color=0x225588, description="<{}>".format(data_ss))
                    embed.set_author(
                        name=data["title"] + " ({}/{})".format(num_, num__),
                        url=data["link"],
                        icon_url="https://ihateani.me/o/vndbico.png",
                    )
                    embed.set_image(url=data_ss)

                await msg.clear_reactions()
                await msg.edit(embed=embed)
            elif "⏩" in str(res.emoji):
                if not screen_table:
                    num = num + 1
                data = resdata[num - 1]
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

                if screen_table:
                    # Reset embed
                    num_ = num_ + 1
                    data_ss = data["screenshot"][num_ - 1]
                    embed = discord.Embed(color=0x225588, description="<{}>".format(data_ss))
                    embed.set_author(
                        name=data["title"] + " ({}/{})".format(num_, num__),
                        url=data["link"],
                        icon_url="https://ihateani.me/o/vndbico.png",
                    )
                    embed.set_image(url=data_ss)

                await msg.clear_reactions()
                await msg.edit(embed=embed)
            elif "✅" in str(res.emoji):
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

                screen_table = False
                await msg.clear_reactions()
                await msg.edit(embed=embed)
            elif "📸" in str(res.emoji):
                data_ss = data["screenshot"][num_ - 1]
                embed = discord.Embed(color=0x225588, description="<{}>".format(data_ss))
                embed.set_author(
                    name=data["title"] + " ({}/{})".format(num_, num__),
                    url=data["link"],
                    icon_url="https://ihateani.me/o/vndbico.png",
                )
                embed.set_image(url=data_ss)

                screen_table = True
                await msg.clear_reactions()
                await msg.edit(embed=embed)
