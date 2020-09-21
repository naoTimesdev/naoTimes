import functools
import glob
import logging
import os
import re
from datetime import datetime
from typing import List, Optional, Union

import aiohttp
import discord
import feedparser
from discord.ext import commands, tasks
from markdownify import markdownify as mdparse

from nthelper.bot import naoTimesBot
from nthelper.utils import HelpGenerator, read_files, send_timed_msg, sync_wrap, write_files

asyncfeed = sync_wrap(feedparser.parse)


async def confirmation_dialog(bot: naoTimesBot, ctx, message: str) -> bool:
    dis_msg = await ctx.send(message)
    to_react = ["✅", "❌"]
    for react in to_react:
        await dis_msg.add_reaction(react)

    def check_react(reaction, user):
        if reaction.message.id != dis_msg.id:
            return False
        if user != ctx.message.author:
            return False
        if str(reaction.emoji) not in to_react:
            return False
        return True

    dialog_tick = True
    while True:
        res, user = await bot.wait_for("reaction_add", check=check_react)
        if user != ctx.message.author:
            pass
        elif "✅" in str(res.emoji):
            await dis_msg.delete()
            break
        elif "❌" in str(res.emoji):
            dialog_tick = False
            await dis_msg.delete()
            break
    return dialog_tick


def filter_data(entries) -> dict:
    """Remove unnecessary tags that just gonna trashed the data"""
    remove_data = [
        "title_detail",
        "links",
        "authors",
        "author_detail",
        "content",
        "updated",
        "guidislink",
        "summary_detail",
        "comments",
        "href",
        "wfw_commentrss",
        "slash_comments",
        "media_content",
    ]

    for r in remove_data:
        try:
            del entries[r]
        except KeyError:
            pass

    if "tags" in entries:
        try:
            tags = []
            for t in entries["tags"]:
                tags.append(t["term"])
            entries["tags"] = tags
        except KeyError:
            entries["tags"] = []

    if "media_thumbnail" in entries:
        try:
            entries["media_thumbnail"] = entries["media_thumbnail"][0]["url"]
        except IndexError:
            entries["media_thumbnail"] = ""
        except KeyError:
            entries["media_thumbnail"] = ""

    if "summary" in entries:
        entries["summary"] = mdparse(entries["summary"])

    if "description" in entries:
        entries["description"] = mdparse(entries["description"])

    return entries


async def async_feedparse(url: str, **kwargs) -> Optional[feedparser.FeedParserDict]:
    async with aiohttp.ClientSession() as session:
        try:
            async with session.get(url) as r:
                r_data = await r.text()
        except aiohttp.ClientError:
            return None
    return await asyncfeed(r_data, **kwargs)


async def check_if_valid(url: str) -> bool:
    feed = await async_feedparse(url)

    if feed is None:
        return False

    if not feed.entries:
        return False
    return True


async def parse_message(message, entry_data):
    matches = re.findall(r"(?P<data>{[^{}]+})", message, re.MULTILINE | re.IGNORECASE)
    msg_fmt_data = [m.strip(r"{}") for m in matches]

    for i in msg_fmt_data:
        try:
            message = message.replace("{" + i + "}", entry_data[i])
        except KeyError:
            pass

    return message.replace("\\n", "\n")


def replace_tz(string):
    for i in range(-12, 13):
        string = string.replace("+0{}:00".format(i), "")
    return string


async def parse_embed(embed_data, entry_data):
    regex_embed = re.compile(r"(?P<data>{[^{}]+})", re.MULTILINE | re.IGNORECASE)

    filtered = {}
    for k, v in embed_data.items():
        if not v:
            continue
        if isinstance(v, bool):
            continue
        matches = re.findall(regex_embed, v)
        msg_fmt = [m.strip(r"{}") for m in matches]
        for i in msg_fmt:
            try:
                if isinstance(entry_data[i], list):
                    entry_data[i] = ", ".join(entry_data[i])
                v = v.replace("{" + i + "}", entry_data[i])
            except KeyError:
                pass
        filtered[k] = v

    if "color" in filtered:
        if filtered["color"].isdigit():
            filtered["color"] = int(v)
        else:
            filtered["color"] = 16777215

    filtered["type"] = "rich"
    if "thumbnail" in filtered:
        ll = {}
        ll["url"] = filtered["thumbnail"]
        filtered["thumbnail"] = ll
    if "image" in filtered:
        ll = {}
        ll["url"] = filtered["image"]
        filtered["image"] = ll

    if embed_data["timestamp"]:
        try:
            filtered["timestamp"] = replace_tz(entry_data["published_parsed"])
        except KeyError:
            filtered["timestamp"] = datetime.now().strftime("%Y-%m-%dT%H:%M")

    if "footer" in filtered:
        new_f = {}
        new_f["text"] = filtered["footer"]
        if "footer_img" in filtered:
            new_f["icon_url"] = filtered["footer_img"]
        del filtered["footer"]
        if "footer_img" in filtered:
            del filtered["footer_img"]
        filtered["footer"] = new_f

    return filtered


async def recursive_check_feed(url, rss_data):
    fetched_data = rss_data["fetchedURL"]
    last_etag = rss_data["lastEtag"]
    last_modified = rss_data["lastModified"]
    feed = await async_feedparse(url, etag=last_etag, modified=last_modified)
    if not feed:
        return None, feed.etag, feed.modified

    entries = feed.entries

    filtered_entry = []
    for n, entry in enumerate(entries):
        if entry["link"] in fetched_data:
            continue
        filtered_entry.append(filter_data(entries[n]))

    return filtered_entry, feed.etag, feed.modified


class FansubRSS(commands.Cog):
    def __init__(self, bot: naoTimesBot):
        self.bot = bot
        self.logger = logging.getLogger("cogs.fansubrss.FansubRSS")

        self.splitbase = lambda path: os.path.splitext(os.path.basename(path))  # noqa: E731
        self.default_msg = r":newspaper: | Rilisan Baru: **{title}**\n{link}"

        self._locked_server: List[str] = []

    async def read_rss(self, server_id: Union[str, int]) -> dict:
        full_path = os.path.join(self.bot.fcwd, "fansubrss_data", f"{server_id}.fsrss")
        if not os.path.isfile(full_path):
            return {}
        rss_metadata = await read_files(full_path)
        return rss_metadata

    def check_if_author(self, m, original_author):
        return m.author == original_author

    def base_check_react(self, reaction, user, ctx, message, emotes_set):
        if reaction.message.id != message.id:
            return False
        if user != ctx.message.author:
            return False
        if str(reaction.emoji) not in emotes_set:
            return False
        return True

    async def write_rss(self, server_id: Union[str, int], data: dict):
        full_path = os.path.join(self.bot.fcwd, "fansubrss_data", f"{server_id}.fsrss")
        await write_files(data, full_path)

    async def server_rss(self) -> list:
        full_path = os.path.join(self.bot.fcwd, "fansubrss_data", "*.fsrss")
        all_rss = [self.splitbase(path)[0] for path in glob.glob(full_path)]
        return all_rss

    @tasks.loop(minutes=5.0)
    async def servers_rss_checks(self):
        """
        The actual process that will check all RSS feeds.
        """
        pass

    @commands.group(aliases=["rss"])
    async def fansubrss(self, ctx):
        if ctx.invoked_subcommand is None:
            helpcmd = HelpGenerator(self.bot, "fansubrss", desc="Pemantau RSS Fansub.")
            await helpcmd.generate_field(
                "fansubrss", desc="Memunculkan bantuan perintah ini.",
            )
            await helpcmd.generate_field(
                "fansubrss aktifkan", desc="Mengaktifkan RSS announcer di channel tertentu.",
            )
            await helpcmd.generate_field(
                "fansubrss ubah", desc="Mengatur settingan RSS di server ini.",
            )
            await helpcmd.generate_field("fansubrss format", desc="Format bagaimana RSS akan dikirim.")
            await helpcmd.generate_field(
                "fansubrss terakhir",
                desc="Mengambil RSS terakhir dan mengirimnya ke channel di mana perintah itu dipakai.",
            )
            await helpcmd.generate_field("fansubrss format", desc="Format bagaimana RSS akan dikirim.")
            await helpcmd.generate_aliases(["rss"])
            await ctx.send(helpcmd.get())

    @fansubrss.command(name="aktifkan", aliases=["activate"])
    async def fansubrss_aktifkan(self, ctx, *, channel_id: int = 0):
        if channel_id == 0:
            channel_id = ctx.message.channel.id
        server_id = str(ctx.message.guild.id)

        saved_rss = await self.server_rss()
        if server_id in saved_rss:
            return await ctx.send(
                "FansubRSS sudah diaktifkan di server ini, silakan gunakan !fansubrss ubah untuk mengaturnya."
            )

        check_if_author = functools.partial(self.check_if_author, original_author=ctx.message.author.id)

        msg = await ctx.send("Mohon ketik/paste URL rss.")
        await_msg = await self.bot.wait_for("message", check=check_if_author)
        if await_msg.content == ("cancel"):
            return await ctx.send("Dibatalkan.")
        rss_url = await_msg.content
        if not (await check_if_valid(rss_url)):
            return await ctx.send("URL yang diberikan bukanlah link RSS yang valid.")

        res = await confirmation_dialog(self.bot, ctx, f"Apakah yakin ingin menggunakan link: <{rss_url}>?")
        if not res:
            return await ctx.send("Dibatalkan.")

        await msg.delete()
        await await_msg.delete()
        await ctx.send("Mengaktifkan RSS...")

        json_tables = {
            "channel": channel_id,
            "feedUrl": rss_url,
            "message": self.default_msg,
            "fetchedURL": [],
            "lastEtag": "",
            "lastModified": "",
            "embed": {},
        }

        await self.write_rss(server_id, json_tables)
        await ctx.send("FansubRSS berhasil diaktifkan, silakan atur formatting dengan !fansubrss format")

    @fansubrss.command(name="format")
    async def fansubrss_format(self, ctx):
        server_id = str(ctx.message.guild.id)
        self._locked_server.append(server_id)
        check_if_author = functools.partial(self.check_if_author, original_author=ctx.message.author.id)
        rss_metadata = await self.read_rss(server_id)
        self.logger.info(f"fetching {server_id} metadata...")
        if not rss_metadata:
            self.logger.error(f"{server_id}: cannot find metadata...")
            return await ctx.send("FansubRSS belum diaktifkan.")

        self.logger.info(f"{server_id}: fetching latest rss data for sample...")
        feed_data = await async_feedparse(rss_metadata["feedUrl"])
        if not feed_data:
            self.logger.error(f"{server_id}: failed to fetch data sample, cancelling...")
            return await ctx.send("Tidak dapat membuat koneksi dengan RSS feed, membatalkan...")
        entries_data = feed_data.entries
        sample_entry = filter_data(entries_data[0])

        async def generate_sample_data(entry_data: dict):
            embed = discord.Embed(
                title="Contoh data",
                description=r"Ketik `{nama_data}` untuk memakai data dari RSS, misalkan "
                r"ingin memakai judul dari RSS.\nMaka pakai `{title}`",
            )
            for nama_data, isi_data in entry_data.items():
                embed.add_field(name="`{" + str(nama_data) + "}`", value=str(isi_data))
            return embed

        async def generate_internal_embed(internal_data: dict):
            embed = discord.Embed(
                title="Format Data Embed", description=r"Ketik `{nama_data}` untuk mengubah isinya."
            )
            for key, value in internal_data.items():
                if key == "timestamp":
                    embed.add_field(
                        name="`timestamp`", value="Aktif" if value else "Tidak aktif", inline=False
                    )
                else:
                    embed.add_field(
                        name=f"`{key}`", value=value if value is not None else "Kosong.", inline=False
                    )
            return embed

        number_reactions = [
            "1️⃣",
            "2️⃣",
            "3️⃣",
            "4️⃣",
            "5️⃣",
            "6️⃣",
            "7️⃣",
            "8️⃣",
            "9️⃣",
            "0️⃣",
        ]
        valid_embed = [
            "title",
            "description",
            "url",
            "color",
            "thumbnail",
            "image",
            "footer",
            "footer_img",
        ]

        first_run = True
        cancelled = False
        emb_msg: discord.Message
        self.logger.info(f"{server_id}: starting data modifying...")
        while True:
            if first_run:
                embed = discord.Embed(title=f"FansubRSS: {server_id}")
                embed.add_field(name="1️⃣ Atur Pesan", value=f"`{rss_metadata['message']}`", inline=False)
                embed.add_field(
                    name="2️⃣ Atur Embed",
                    value="Embed aktif?: {}".format("Ya" if rss_metadata["embed"] else "Tidak"),
                    inline=False,
                )
                embed.add_field(name="✅ Simpan", value="Simpan perubahan.", inline=True)
                embed.add_field(name="❌ Batalkan", value="Batalkan perubahan.", inline=True)
                embed.set_footer(
                    text="Dibawakan oleh naoTimes™®", icon_url="https://p.n4o.xyz/i/nao250px.png",
                )
                first_run = False
                emb_msg = await ctx.send(embed=embed)
            else:
                embed = discord.Embed(title=f"FansubRSS: {server_id}")
                embed.add_field(name="1️⃣ Atur Pesan", value=f"`{rss_metadata['message']}`", inline=False)
                embed.add_field(
                    name="2️⃣ Atur Embed",
                    value="Embed aktif?: {}".format("Ya" if rss_metadata["embed"] else "Tidak"),
                    inline=False,
                )
                embed.add_field(name="✅ Simpan", value="Simpan perubahan.", inline=True)
                embed.add_field(name="❌ Batalkan", value="Batalkan perubahan.", inline=True)
                embed.set_footer(
                    text="Dibawakan oleh naoTimes™®", icon_url="https://p.n4o.xyz/i/nao250px.png",
                )
                await emb_msg.edit(embed=embed)

            react_first_part = number_reactions[0:2]
            react_first_part.extend(["✅", "❌"])

            first_check = functools.partial(
                self.base_check_react, ctx=ctx, message=emb_msg, emotes_set=react_first_part
            )

            for react in react_first_part:
                await emb_msg.add_reaction(react)

            res, user = await self.bot.wait_for("reaction_add", check=first_check.func)
            if user != ctx.message.author:
                pass
            elif "✅" in str(res.emoji):
                await emb_msg.clear_reactions()
                break
            elif "❌" in str(res.emoji):
                await emb_msg.clear_reactions()
                cancelled = True
                break
            elif react_first_part[0] in str(res.emoji):
                self.logger.info(f"{server_id}: changing message data...")
                await emb_msg.clear_reactions()
                smpl_embed = await generate_sample_data(sample_entry)
                sample_msg = await ctx.send(embed=smpl_embed)
                extra_msg = await ctx.send(
                    "Ketik pesan yang diinginkan!\n"
                    "(ketik *cancel* untuk membatalkannya proses ini, "
                    "*clear* untuk menghapus pesan yang ada, "
                    "*reset* untuk menormalkannya kembali)"
                )
                format_msg_wait = await self.bot.wait_for("message", check=check_if_author)
                format_msg_cntn = format_msg_wait.content
                if format_msg_cntn == ("cancel"):
                    pass
                elif format_msg_cntn == ("clear"):
                    rss_metadata["message"] = None
                elif format_msg_cntn == ("reset"):
                    rss_metadata["message"] = self.default_msg
                else:
                    await extra_msg.delete()
                    await sample_msg.delete()
                    await format_msg_wait.delete()
                    await send_timed_msg(ctx, f"Pesan berhasil diubah ke: `{rss_metadata['message']}`", 2)
            elif react_first_part[1] in str(res.emoji):
                self.logger.info(f"{server_id}: changing embed data...")
                await emb_msg.clear_reactions()
                new_embed_data = {
                    "title": None,
                    "description": None,
                    "url": None,
                    "thumbnail": None,
                    "image": None,
                    "footer": None,
                    "footer_img": None,
                    "color": None,
                    "timestamp": False,
                }
                if rss_metadata["embed"]:
                    for ek, ev in rss_metadata["embed"].items():
                        new_embed_data[ek] = ev
                cur_emb_data = await generate_internal_embed(new_embed_data)
                smpl_embed = await generate_sample_data(sample_entry)
                sample_msg = await ctx.send(embed=smpl_embed)
                cur_emb_msg = await ctx.send(embed=cur_emb_data)
                extra_msg_embed = await ctx.send(
                    "Ketik `nama_data` untuk mengubahnya (misal `title`)!\n"
                    "ketik *cancel* untuk membatalkannya proses ini\n"
                    "Ketik *clear* untuk menghapus embed yang ada\n"
                    "Ketik *done* jika sudah selesai."
                )
                cancelled_embed = False
                first_embed_change_run = True
                while True:
                    if first_embed_change_run:
                        first_embed_change_run = False
                    else:
                        cur_emb_data = await generate_internal_embed(new_embed_data)
                        await cur_emb_msg.edit(embed=cur_emb_data)
                    embed_input = await self.bot.wait_for("message", check=check_if_author)
                    embed_input_txt = embed_input.content
                    if embed_input_txt == ("cancel"):
                        cancelled_embed = True
                        await embed_input.delete()
                        break
                    elif embed_input_txt == ("reset"):
                        new_embed_data = {}
                        await embed_input.delete()
                        break
                    elif embed_input_txt == ("done"):
                        await embed_input.delete()
                        break
                    else:
                        if embed_input_txt in valid_embed:
                            self.logger.info(f"embed: changing {embed_input_txt}")
                            extra_clr_txt = (
                                "\n Bisa melihat angka warna di sini: <https://leovoel.github.io/embed-visualizer/>"  # noqa: E501
                                if "color" in embed_input_txt
                                else ""
                            )
                            msg_changed = await ctx.send(f"Mengubah: `{embed_input_txt}`{extra_clr_txt}")
                            embed_change_input = await self.bot.wait_for("message", check=check_if_author)
                            embed_change_input_txt = embed_change_input.content
                            if embed_change_input_txt == ("cancel"):
                                pass
                            else:
                                new_embed_data[embed_input_txt.strip()] = embed_change_input_txt
                                await msg_changed.delete()
                                await embed_change_input.delete()
                                await send_timed_msg(ctx, f"Berhasil mengubah data `{embed_input_txt}`", 2)
                        elif "timestamp" in embed_input_txt:
                            if not new_embed_data["timestamp"]:
                                new_embed_data["timestamp"] = True
                                await send_timed_msg(ctx, "Mengaktifkan timestamp...", 2)
                            else:
                                new_embed_data["timestamp"] = False
                                await send_timed_msg(ctx, "Menonaktifkan timestamp...", 2)
                        else:
                            await send_timed_msg(ctx, "Tipe data tidak diketahui.", 2)
                    await embed_input.delete()

                if not cancelled_embed:
                    rss_metadata["embed"] = new_embed_data

                await sample_msg.delete()
                await cur_emb_msg.delete()
                await extra_msg_embed.delete()
                await send_timed_msg(ctx, "Berhasil mengubah data embed.", 2)

        if cancelled:
            self._locked_server.remove(server_id)
            self.logger.warning(f"{server_id}: commiting data is cancelled...")
            return await ctx.send("Dibatalkan.")

        self.logger.info(f"{server_id}: commiting data...")
        await emb_msg.delete()
        msg_final = await ctx.send("Menyimpan data terbaru...")
        await self.write_rss(server_id, rss_metadata)
        self._locked_server.remove(server_id)
        await msg_final.edit(content="Formatting baru telah disimpan.")


def setup(bot):
    if True:
        # Skip
        return
    bot.add_cog(FansubRSS(bot))
