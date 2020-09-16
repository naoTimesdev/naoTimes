# -*- coding: utf-8 -*-

import asyncio
import logging
import time
from copy import deepcopy
from functools import partial
from random import choice
from string import ascii_lowercase, digits

import discord
from discord.ext import commands

from nthelper import HelpGenerator, get_current_time, send_timed_msg
from nthelper.fsdb import FansubDBBridge
from nthelper.showtimes_helper import ShowtimesQueue, ShowtimesQueueData, naoTimesDB

from .base import ShowtimesBase, fetch_anilist

add_eps_instruct = """Jumlah yang dimaksud adalah jumlah yang ingin ditambahkan dari jumlah episode sekarang
Misal ketik `4` dan total jumlah episode sekarang adalah `12`
Maka total akan berubah menjadi `16` `(13, 14, 15, 16)`"""  # noqa: E501

del_eps_instruct = """Ranged number, bisa satu digit untuk 1 episode saja atau range dari episode x sampai y
Contoh: `4` untuk episode 4 saja || `4-6` untuk episode 4 sampai 6"""  # noqa: E501


class ShowtimesAlias(commands.Cog, ShowtimesBase):
    def __init__(self, bot):
        super(ShowtimesAlias, self).__init__()
        self.bot = bot
        self.ntdb: naoTimesDB = bot.ntdb
        self.cog_name = "Showtimes Alias"
        self.showqueue: ShowtimesQueue = bot.showqueue
        self.srv_fetch = partial(self.fetch_showtimes, cwd=bot.fcwd)
        self.srv_dumps = partial(self.dumps_showtimes, cwd=bot.fcwd)
        self.logger = logging.getLogger("cogs.showtimes_module.admin.ShowtimesAlias")

    def __str__(self):
        return "Showtimes Alias"

    @commands.group()
    @commands.guild_only()
    async def alias(self, ctx):
        """
        Initiate alias creation for certain anime
        """
        if not ctx.invoked_subcommand:
            server_message = str(ctx.message.guild.id)
            self.logger.info(f"requested at {server_message}")
            srv_data = await self.showqueue.fetch_database(server_message)

            if srv_data is None:
                return
            self.logger.info(f"{server_message}: data found.")

            if str(ctx.message.author.id) not in srv_data["serverowner"]:
                self.logger.warning(f"{server_message}: not the server admin")
                return await ctx.send("Hanya admin yang bisa menambah alias")

            srv_anilist, _ = await self.collect_anime_with_alias(srv_data["anime"], srv_data["alias"])

            if len(srv_anilist) < 1:
                self.logger.warning(f"{server_message}: no registered data on database.")
                return await ctx.send("Tidak ada anime yang terdaftar di database")

            self.logger.info(f"{server_message}: generating initial data...")
            embed = discord.Embed(title="Alias", color=0x56ACF3)
            embed.add_field(name="Memulai Proses!", value="Mempersiapkan...", inline=False)
            embed.set_footer(
                text="Dibawakan oleh naoTimes™®", icon_url="https://p.n4o.xyz/i/nao250px.png",
            )
            emb_msg = await ctx.send(embed=embed)
            msg_author = ctx.message.author
            json_tables = {"alias_anime": "", "target_anime": ""}

            def check_if_author(m):
                return m.author == msg_author

            async def process_anime(table, emb_msg, anime_list):
                self.logger.info(f"{server_message}: processing anime...")
                embed = discord.Embed(title="Alias", color=0x96DF6A)
                embed.add_field(
                    name="Judul/Garapan Anime",
                    value="Ketik judul animenya (yang asli), bisa disingkat",
                    inline=False,
                )
                embed.set_footer(
                    text="Dibawakan oleh naoTimes™®", icon_url="https://p.n4o.xyz/i/nao250px.png",
                )
                await emb_msg.edit(embed=embed)

                await_msg = await self.bot.wait_for("message", check=check_if_author)
                matches = self.get_close_matches(await_msg.content, anime_list)
                await await_msg.delete()
                if not matches:
                    await ctx.send("Tidak dapat menemukan judul tersebut di database")
                    return False, False
                elif len(matches) > 1:
                    matches = await self.choose_anime(bot=self.bot, ctx=ctx, matches=matches)
                    if not matches:
                        return await ctx.send("**Dibatalkan!**")

                embed = discord.Embed(title="Alias", color=0x96DF6A)
                embed.add_field(
                    name="Apakah benar?", value="Judul: **{}**".format(matches[0]), inline=False,
                )
                embed.set_footer(
                    text="Dibawakan oleh naoTimes™®", icon_url="https://p.n4o.xyz/i/nao250px.png",
                )
                await emb_msg.delete()
                emb_msg = await ctx.send(embed=embed)

                to_react = ["✅", "❌"]
                for reaction in to_react:
                    await emb_msg.add_reaction(reaction)

                def check_react(reaction, user):
                    if reaction.message.id != emb_msg.id:
                        return False
                    if user != ctx.message.author:
                        return False
                    if str(reaction.emoji) not in to_react:
                        return False
                    return True

                res, user = await self.bot.wait_for("reaction_add", check=check_react)
                if user != msg_author:
                    pass
                elif "✅" in str(res.emoji):
                    table["target_anime"] = matches[0]
                    await emb_msg.clear_reactions()
                elif "❌" in str(res.emoji):
                    await ctx.send("**Dibatalkan!**")
                    await emb_msg.clear_reactions()
                    return False, False

                return table, emb_msg

            async def process_alias(table, emb_msg):
                self.logger.info(f"{server_message}: processing alias...")
                embed = discord.Embed(title="Alias", color=0x96DF6A)
                embed.add_field(
                    name="Alias", value="Ketik alias yang diinginkan", inline=False,
                )
                embed.set_footer(
                    text="Dibawakan oleh naoTimes™®", icon_url="https://p.n4o.xyz/i/nao250px.png",
                )
                await emb_msg.edit(embed=embed)

                await_msg = await self.bot.wait_for("message", check=check_if_author)
                table["alias_anime"] = await_msg.content
                await await_msg.delete()

                return table, emb_msg

            json_tables, emb_msg = await process_anime(json_tables, emb_msg, srv_anilist)

            if not json_tables:
                self.logger.warning(f"{server_message}: cancelling process...")
                return

            json_tables, emb_msg = await process_alias(json_tables, emb_msg)
            self.logger.info(f"{server_message}: final checking...")
            first_time = True
            cancel_toggled = False
            while True:
                embed = discord.Embed(
                    title="Alias", description="Periksa data!\nReact jika ingin diubah.", color=0xE7E363,
                )
                embed.add_field(
                    name="1⃣ Anime/Garapan", value="{}".format(json_tables["target_anime"]), inline=False,
                )
                embed.add_field(
                    name="2⃣ Alias", value="{}".format(json_tables["alias_anime"]), inline=False,
                )
                embed.add_field(
                    name="Lain-Lain", value="✅ Tambahkan!\n❌ Batalkan!", inline=False,
                )
                embed.set_footer(
                    text="Dibawakan oleh naoTimes™®", icon_url="https://p.n4o.xyz/i/nao250px.png",
                )
                if first_time:
                    await emb_msg.delete()
                    emb_msg = await ctx.send(embed=embed)
                    first_time = False
                else:
                    await emb_msg.edit(embed=embed)

                to_react = ["1⃣", "2⃣", "✅", "❌"]
                for reaction in to_react:
                    await emb_msg.add_reaction(reaction)

                def check_react(reaction, user):
                    if reaction.message.id != emb_msg.id:
                        return False
                    if user != ctx.message.author:
                        return False
                    if str(reaction.emoji) not in to_react:
                        return False
                    return True

                res, user = await self.bot.wait_for("reaction_add", check=check_react)
                if user != ctx.message.author:
                    pass
                if to_react[0] in str(res.emoji):
                    await emb_msg.clear_reactions()
                    json_tables, emb_msg = await process_anime(json_tables, emb_msg, srv_anilist)
                elif to_react[1] in str(res.emoji):
                    await emb_msg.clear_reactions()
                    json_tables, emb_msg = await process_alias(json_tables, emb_msg)
                elif "✅" in str(res.emoji):
                    await emb_msg.clear_reactions()
                    break
                elif "❌" in str(res.emoji):
                    self.logger.warning(f"{server_message}: cancelled!")
                    cancel_toggled = True
                    await emb_msg.clear_reactions()
                    break

            if cancel_toggled:
                self.logger.warning(f"{server_message}: cancelling process...")
                return await ctx.send("**Dibatalkan!**")

            # Everything are done and now processing data
            self.logger.info(f"{server_message}: saving data...")
            embed = discord.Embed(title="Alias", color=0x56ACF3)
            embed.add_field(name="Memproses!", value="Membuat data...", inline=True)
            embed.set_footer(
                text="Dibawakan oleh naoTimes™®", icon_url="https://p.n4o.xyz/i/nao250px.png",
            )
            await emb_msg.edit(embed=embed)

            if json_tables["alias_anime"] in srv_data["alias"]:
                embed = discord.Embed(title="Alias", color=0xE24545)
                embed.add_field(
                    name="Dibatalkan!",
                    value="Alias **{}** sudah terdaftar untuk **{}**".format(
                        json_tables["alias_anime"], srv_data["alias"][json_tables["alias_anime"]],
                    ),
                    inline=True,
                )
                embed.set_footer(
                    text="Dibawakan oleh naoTimes™®", icon_url="https://p.n4o.xyz/i/nao250px.png",
                )
                await emb_msg.delete()
                return await ctx.send(embed=embed)

            srv_data["alias"][json_tables["alias_anime"]] = json_tables["target_anime"]

            embed = discord.Embed(title="Alias", color=0x56ACF3)
            embed.add_field(name="Memproses!", value="Mengirim data...", inline=True)
            embed.set_footer(
                text="Dibawakan oleh naoTimes™®", icon_url="https://p.n4o.xyz/i/nao250px.png",
            )
            await emb_msg.edit(embed=embed)

            self.logger.info(f"{server_message}: storing data...")
            await self.showqueue.add_job(ShowtimesQueueData(srv_data, server_message))
            embed = discord.Embed(title="Alias", color=0x96DF6A)
            embed.add_field(
                name="Sukses!",
                value="Alias **{} ({})** telah ditambahkan ke database\nDatabase utama akan diupdate sebentar lagi".format(  # noqa: E501
                    json_tables["alias_anime"], json_tables["target_anime"]
                ),
                inline=True,
            )
            embed.set_footer(
                text="Dibawakan oleh naoTimes™®", icon_url="https://p.n4o.xyz/i/nao250px.png",
            )
            await ctx.send(embed=embed)
            await emb_msg.delete()

            self.logger.info(f"{server_message}: updating database...")
            success, msg = await self.ntdb.update_data_server(server_message, srv_data)

            if not success:
                self.logger.error(f"{server_message}: failed to update, reason: {msg}")
                if server_message not in self.bot.showtimes_resync:
                    self.bot.showtimes_resync.append(server_message)

            await ctx.send(
                "Berhasil menambahkan alias **{} ({})** ke dalam database utama naoTimes".format(  # noqa: E501
                    json_tables["alias_anime"], json_tables["target_anime"]
                )
            )

    @alias.command(name="list")
    async def alias_list(self, ctx, *, judul):
        server_message = str(ctx.message.guild.id)
        self.logger.info(f"requested at {server_message}")
        srv_data = await self.showqueue.fetch_database(server_message)

        if srv_data is None:
            return
        self.logger.info(f"{server_message}: data found.")

        if not srv_data["alias"]:
            return await ctx.send("Tidak ada alias yang terdaftar.")

        srv_anilist, _ = await self.collect_anime_with_alias(srv_data["anime"], srv_data["alias"])

        if not judul:
            return await self.send_all_projects(ctx, srv_anilist, server_message)

        self.logger.info(f"{server_message}: getting close matches...")
        matches = self.get_close_matches(judul, srv_anilist)
        if not matches:
            self.logger.warning(f"{server_message}: no matches.")
            return await ctx.send("Tidak dapat menemukan judul tersebut di database")
        elif len(matches) > 1:
            self.logger.info(f"{server_message}: multiple matches!")
            matches = await self.choose_anime(bot=self.bot, ctx=ctx, matches=matches)
            if not matches:
                return await ctx.send("**Dibatalkan!**")

        self.logger.info(f"{server_message}: matched {matches[0]}")
        srv_anilist_alias = []
        for k, v in srv_data["alias"].items():
            if v in matches:
                srv_anilist_alias.append(k)

        text_value = ""
        if not srv_anilist_alias:
            text_value += "Tidak ada"

        if not text_value:
            text_value += self.make_numbered_alias(srv_anilist_alias)

        self.logger.info(f"{server_message}: sending alias!")
        embed = discord.Embed(title="Alias list", color=0x47E0A7)
        embed.add_field(name=matches[0], value=text_value, inline=False)
        embed.set_footer(
            text="Dibawakan oleh naoTimes™®", icon_url="https://p.n4o.xyz/i/nao250px.png",
        )
        await ctx.send(embed=embed)

    @alias.command(name="hapus", aliases=["remove"])
    async def alias_hapus(self, ctx, *, judul):
        server_message = str(ctx.message.guild.id)
        self.logger.info(f"requested at {server_message}")
        srv_data = await self.showqueue.fetch_database(server_message)

        if srv_data is None:
            return
        self.logger.info(f"{server_message}: data found.")

        if str(ctx.message.author.id) not in srv_data["serverowner"]:
            self.logger.warning(f"{server_message}: not the server admin")
            return await ctx.send("Hanya admin yang bisa menghapus alias")

        if not srv_data["alias"]:
            return await ctx.send("Tidak ada alias yang terdaftar.")

        srv_anilist, _ = await self.collect_anime_with_alias(srv_data["anime"], srv_data["alias"])

        if not judul:
            return await self.send_all_projects(ctx, srv_anilist, server_message)

        matches = self.get_close_matches(judul, srv_anilist)
        if not matches:
            self.logger.warning(f"{server_message}: no matches.")
            return await ctx.send("Tidak dapat menemukan judul tersebut di database")
        elif len(matches) > 1:
            self.logger.info(f"{server_message}: multiple matches!")
            matches = await self.choose_anime(bot=self.bot, ctx=ctx, matches=matches)
            if not matches:
                return await ctx.send("**Dibatalkan!**")

        self.logger.info(f"{server_message}: matched {matches[0]}")
        srv_anilist_alias = []
        for k, v in srv_data["alias"].items():
            if v in matches:
                srv_anilist_alias.append(k)

        if not srv_anilist_alias:
            self.logger.info(f"{matches[0]}: no registered alias.")
            return await ctx.send("Tidak ada alias yang terdaftar untuk judul **{}**".format(matches[0]))

        alias_chunked = [srv_anilist_alias[i : i + 5] for i in range(0, len(srv_anilist_alias), 5)]

        first_run = True
        n = 1
        max_n = len(alias_chunked)
        while True:
            if first_run:
                self.logger.info(f"{server_message}: sending results...")
                n = 1
                first_run = False
                embed = discord.Embed(title="Alias list", color=0x47E0A7)
                embed.add_field(
                    name="{}".format(matches[0]),
                    value=self.make_numbered_alias(alias_chunked[n - 1]),
                    inline=False,
                )
                embed.add_field(
                    name="*Informasi*",
                    value="1⃣-5⃣ Hapus `x` alias\n⏪ Sebelumnya" "\n⏩ Selanjutnya\n❌ Batalkan",
                )
                embed.set_footer(
                    text="Dibawakan oleh naoTimes™®", icon_url="https://p.n4o.xyz/i/nao250px.png",
                )
                emb_msg = await ctx.send(embed=embed)

            react_ext = []
            to_react = ["1⃣", "2⃣", "3⃣", "4⃣", "5⃣"]  # 5 per page
            if max_n == 1 and n == 1:
                pass
            elif n == 1:
                react_ext.append("⏩")
            elif n == max_n:
                react_ext.append("⏪")
            elif n > 1 and n < max_n:
                react_ext.extend(["⏪", "⏩"])

            react_ext.append("❌")
            to_react = to_react[0 : len(alias_chunked[n - 1])]
            to_react.extend(react_ext)

            for react in to_react:
                await emb_msg.add_reaction(react)

            def check_react(reaction, user):
                if reaction.message.id != emb_msg.id:
                    return False
                if user != ctx.message.author:
                    return False
                if str(reaction.emoji) not in to_react:
                    return False
                return True

            try:
                res, user = await self.bot.wait_for("reaction_add", check=check_react, timeout=30.0)
            except asyncio.TimeoutError:
                return await emb_msg.clear_reactions()
            if user != ctx.message.author:
                pass
            elif "⏪" in str(res.emoji):
                n = n - 1
                await emb_msg.clear_reactions()
                embed = discord.Embed(title="Alias list", color=0x47E0A7)
                embed.add_field(
                    name="{}".format(matches[0]),
                    value=self.make_numbered_alias(alias_chunked[n - 1]),
                    inline=False,
                )
                embed.add_field(
                    name="*Informasi*",
                    value="1⃣-5⃣ Hapus `x` alias\n⏪ Sebelumnya" "\n⏩ Selanjutnya\n❌ Batalkan",
                )
                embed.set_footer(
                    text="Dibawakan oleh naoTimes™®", icon_url="https://p.n4o.xyz/i/nao250px.png",
                )
                await emb_msg.edit(embed=embed)
            elif "⏩" in str(res.emoji):
                n = n + 1
                await emb_msg.clear_reactions()
                embed = discord.Embed(title="Alias list", color=0x47E0A7)
                embed.add_field(
                    name="{}".format(matches[0]),
                    value=self.make_numbered_alias(alias_chunked[n - 1]),
                    inline=False,
                )
                embed.add_field(
                    name="*Informasi*",
                    value="1⃣-5⃣ Hapus `x` alias\n⏪ Sebelumnya" "\n⏩ Selanjutnya\n❌ Batalkan",
                )
                embed.set_footer(
                    text="Dibawakan oleh naoTimes™®", icon_url="https://p.n4o.xyz/i/nao250px.png",
                )
                await emb_msg.edit(embed=embed)
            elif "❌" in str(res.emoji):
                self.logger.warning(f"{server_message}: cancelling...")
                await emb_msg.clear_reactions()
                return await ctx.send("**Dibatalkan!**")
            else:
                self.logger.info(f"{server_message}: updating alias list!")
                await emb_msg.clear_reactions()
                await emb_msg.delete()
                index_del = to_react.index(str(res.emoji))
                n_del = alias_chunked[n - 1][index_del]
                del srv_data["alias"][n_del]

                await self.showqueue.add_job(ShowtimesQueueData(srv_data, server_message))
                await ctx.send("Alias **{} ({})** telah dihapus dari database".format(n_del, matches[0]))

                self.logger.info(f"{server_message}: updating database...")
                success, msg = await self.ntdb.update_data_server(server_message, srv_data)

                if not success:
                    self.logger.error(f"{server_message}: failed to update, reason: {msg}")
                    if server_message not in self.bot.showtimes_resync:
                        self.bot.showtimes_resync.append(server_message)

                await emb_msg.delete()


class ShowtimesKolaborasi(commands.Cog, ShowtimesBase):
    def __init__(self, bot):
        super(ShowtimesKolaborasi, self).__init__()
        self.bot = bot
        self.ntdb: naoTimesDB = bot.ntdb
        self.fsdb: FansubDBBridge = bot.fsdb
        self.cog_name = "Showtimes Kolaborasi"
        self.showqueue: ShowtimesQueue = bot.showqueue
        self.srv_fetch = partial(self.fetch_showtimes, cwd=bot.fcwd)
        self.srv_dumps = partial(self.dumps_showtimes, cwd=bot.fcwd)
        self.srv_lists = partial(self.fetch_servers, cwd=bot.fcwd)
        self.logger = logging.getLogger("cogs.showtimes_module.admin.ShowtimesKolaborasi")

    def __str__(self):
        return "Showtimes Kolaborasi"

    @commands.group(aliases=["joint", "join", "koleb"])
    @commands.guild_only()
    async def kolaborasi(self, ctx):
        if not ctx.invoked_subcommand:
            helpcmd = HelpGenerator(self.bot, "kolaborasi", f"Versi {self.bot.semver}")
            await helpcmd.generate_field(
                "kolaborasi", desc="Memunculkan bantuan perintah", use_fullquote=True,
            )
            await helpcmd.generate_field(
                "kolaborasi dengan",
                desc="Memulai proses kolaborasi garapan dengan fansub lain.",
                opts=[{"name": "server id kolaborasi", "type": "r"}, {"name": "judul", "type": "r"}],
                use_fullquote=True,
            )
            await helpcmd.generate_field(
                "kolaborasi konfirmasi",
                desc="Konfirmasi proses kolaborasi garapan.",
                opts=[{"name": "kode unik", "type": "r"}],
                use_fullquote=True,
            )
            await helpcmd.generate_field(
                "kolaborasi putus",
                desc="Memutuskan hubungan kolaborasi suatu garapan.",
                opts=[{"name": "judul", "type": "r"}],
                use_fullquote=True,
            )
            await helpcmd.generate_field(
                "kolaborasi batalkan",
                desc="Membatalkan proses kolaborasi.",
                opts=[{"name": "server id kolaborasi", "type": "r"}, {"name": "kode unik", "type": "r"}],
                use_fullquote=True,
            )
            await helpcmd.generate_aliases(["joint", "join", "koleb"])
            await ctx.send(embed=helpcmd.get())

    @kolaborasi.command(name="dengan", aliases=["with"])
    async def kolaborasi_dengan(self, ctx, server_id, *, judul):
        server_message = str(ctx.message.guild.id)
        self.logger.info(f"requested at {server_message}")
        srv_data = await self.showqueue.fetch_database(server_message)

        if srv_data is None:
            return
        self.logger.info(f"{server_message}: data found.")

        if str(ctx.message.author.id) not in srv_data["serverowner"]:
            self.logger.warning(f"{server_message}: not the server admin")
            return await ctx.send("Hanya admin yang bisa memulai kolaborasi")

        target_server = await self.showqueue.fetch_database(server_id)
        if target_server is None:
            self.logger.warning(f"{server_id}: can't find the server.")
            return await ctx.send("Tidak dapat menemukan server tersebut di database")

        srv_anilist, srv_anilist_alias = await self.collect_anime_with_alias(
            srv_data["anime"], srv_data["alias"]
        )

        if not judul:
            return await self.send_all_projects(ctx, srv_anilist, server_message)

        self.logger.info(f"{server_message}: getting close matches...")
        matches = await self.find_any_matches(judul, srv_anilist, srv_anilist_alias, srv_data["alias"])
        if not matches:
            self.logger.warning(f"{server_message}: no matches.")
            return await ctx.send("Tidak dapat menemukan judul tersebut di database")
        elif len(matches) > 1:
            self.logger.info(f"{server_message}: multiple matches!")
            matches = await self.choose_anime(bot=self.bot, ctx=ctx, matches=matches)
            if not matches:
                return await ctx.send("**Dibatalkan!**")

        self.logger.info(f"{server_message}: matched {matches[0]}")

        if "kolaborasi" in srv_data["anime"][matches[0]]:
            if server_id in srv_data["anime"][matches[0]]["kolaborasi"]:
                self.logger.info(f"{matches[0]}: already on collab.")
                return await ctx.send("Server tersebut sudah diajak kolaborasi.")

        randomize_confirm = "".join(choice(ascii_lowercase + digits) for i in range(16))

        cancel_toggled = False
        first_time = True
        while True:
            try:
                server_identd = self.bot.get_guild(int(server_id))
                server_ident = server_identd.name
            except Exception:
                server_ident = server_id
            embed = discord.Embed(
                title="Kolaborasi", description="Periksa data!\nReact jika ingin diubah.", color=0xE7E363,
            )
            embed.add_field(name="Anime/Garapan", value=matches[0], inline=False)
            embed.add_field(name="Server", value=server_ident, inline=False)
            embed.add_field(
                name="Lain-Lain", value="✅ Tambahkan!\n❌ Batalkan!", inline=False,
            )
            embed.set_footer(
                text="Dibawakan oleh naoTimes™®", icon_url="https://p.n4o.xyz/i/nao250px.png",
            )
            if first_time:
                emb_msg = await ctx.send(embed=embed)
                first_time = False
            else:
                await emb_msg.edit(embed=embed)

            to_react = ["✅", "❌"]
            for react in to_react:
                await emb_msg.add_reaction(react)

            def check_react(reaction, user):
                if reaction.message.id != emb_msg.id:
                    return False
                if user != ctx.message.author:
                    return False
                if str(reaction.emoji) not in to_react:
                    return False
                return True

            res, user = await self.bot.wait_for("reaction_add", check=check_react)
            if user != ctx.message.author:
                pass
            elif "✅" in str(res.emoji):
                await emb_msg.clear_reactions()
                break
            elif "❌" in str(res.emoji):
                self.logger.warning(f"{matches[0]}: cancelling...")
                cancel_toggled = True
                await emb_msg.clear_reactions()
                await emb_msg.delete()
                break

        if cancel_toggled:
            return await ctx.send("**Dibatalkan!**")

        table_data = {}
        table_data["anime"] = matches[0]
        table_data["server"] = server_message

        if "konfirmasi" not in target_server:
            target_server["konfirmasi"] = {}
        target_server["konfirmasi"][randomize_confirm] = table_data

        embed = discord.Embed(title="Kolaborasi", color=0x56ACF3)
        embed.add_field(name="Memproses!", value="Mengirim data...", inline=True)
        embed.set_footer(
            text="Dibawakan oleh naoTimes™®", icon_url="https://p.n4o.xyz/i/nao250px.png",
        )
        await emb_msg.edit(embed=embed)

        self.logger.info(f"{server_message}-{server_id}: storing data...")
        await self.showqueue.add_job(ShowtimesQueueData(target_server, server_id))
        # await self.showqueue.add_job(ShowtimesQueueData(srv_data, server_message))  # noqa: E501
        embed = discord.Embed(title="Kolaborasi", color=0x96DF6A)
        embed.add_field(
            name="Sukses!",
            value="Berikan kode berikut `{}` kepada fansub/server lain.\nDatabase utama akan diupdate sebentar lagi".format(  # noqa: E501
                randomize_confirm
            ),
            inline=True,
        )
        embed.set_footer(
            text="Dibawakan oleh naoTimes™®", icon_url="https://p.n4o.xyz/i/nao250px.png",
        )
        await emb_msg.delete()
        await ctx.send(embed=embed)

        self.logger.info(f"{server_id}: updating database...")
        success, msg = await self.ntdb.kolaborasi_dengan(server_id, randomize_confirm, table_data)

        if not success:
            self.logger.error(f"{server_id}: failed to update, reason: {msg}")
            if server_message not in self.bot.showtimes_resync:
                self.bot.showtimes_resync.append(server_message)

        await ctx.send(
            "Berikan kode berikut `{rand}` kepada fansub/server lain.\nKonfirmasi di server lain dengan `!kolaborasi konfirmasi {rand}`".format(  # noqa: E501
                rand=randomize_confirm
            )
        )

    @kolaborasi.command(name="konfirmasi", aliases=["confirm"])
    async def kolaborasi_konfirmasi(self, ctx, konfirm_id):
        server_message = str(ctx.message.guild.id)
        self.logger.info(f"requested at {server_message}")
        srv_data = await self.showqueue.fetch_database(server_message)

        if srv_data is None:
            return
        self.logger.info(f"{server_message}: data found.")

        if str(ctx.message.author.id) not in srv_data["serverowner"]:
            self.logger.warning(f"{server_message}: not the server admin")
            return await ctx.send("Hanya admin yang bisa konfirmasi kolaborasi.")

        if "konfirmasi" not in srv_data:
            self.logger.warning(f"{server_message}: nothing to confirm.")
            return await ctx.send("Tidak ada kolaborasi yang harus dikonfirmasi.")
        if konfirm_id not in srv_data["konfirmasi"]:
            self.logger.warning(f"{konfirm_id}: can't find that confirm id.")
            return await ctx.send("Tidak dapat menemukan kode kolaborasi yang diberikan.")

        klb_data = srv_data["konfirmasi"][konfirm_id]

        try:
            server_identd = self.bot.get_guild(int(klb_data["server"]))
            server_ident = server_identd.name
        except Exception:
            server_ident = klb_data["server"]

        embed = discord.Embed(title="Konfirmasi Kolaborasi", color=0xE7E363)
        embed.add_field(name="Anime/Garapan", value=klb_data["anime"], inline=False)
        embed.add_field(name="Server", value=server_ident, inline=False)
        embed.add_field(name="Lain-Lain", value="✅ Konfirmasi!\n❌ Batalkan!", inline=False)
        embed.set_footer(
            text="Dibawakan oleh naoTimes™®", icon_url="https://p.n4o.xyz/i/nao250px.png",
        )
        emb_msg = await ctx.send(embed=embed)

        to_react = ["✅", "❌"]
        for react in to_react:
            await emb_msg.add_reaction(react)

        def check_react(reaction, user):
            if reaction.message.id != emb_msg.id:
                return False
            if user != ctx.message.author:
                return False
            if str(reaction.emoji) not in to_react:
                return False
            return True

        res, user = await self.bot.wait_for("reaction_add", check=check_react)
        if user != ctx.message.author:
            pass
        if "✅" in str(res.emoji):
            await emb_msg.clear_reactions()
        elif "❌" in str(res.emoji):
            self.logger.warning(f"{server_message}: cancelling...")
            await emb_msg.clear_reactions()
            return await ctx.send("**Dibatalkan!**")

        ani_srv_role = ""
        if klb_data["anime"] in srv_data["anime"]:
            self.logger.warning(f"{server_message}: existing data, changing with source server")
            ani_srv_role += srv_data["anime"][klb_data["anime"]]["role_id"]
            del srv_data["anime"][klb_data["anime"]]

        if not ani_srv_role:
            self.logger.info(f"{server_message}: creating roles...")
            c_role = await ctx.message.guild.create_role(
                name=klb_data["anime"], colour=discord.Colour(0xDF2705), mentionable=True,
            )
            ani_srv_role = str(c_role.id)

        srv_source = klb_data["server"]
        source_srv_data = await self.showqueue.fetch_database(srv_source)

        other_anime_data = source_srv_data["anime"][klb_data["anime"]]
        copied_data = deepcopy(other_anime_data)
        srv_data["anime"][klb_data["anime"]] = copied_data
        srv_data["anime"][klb_data["anime"]]["role_id"] = ani_srv_role

        join_srv = [klb_data["server"], server_message]
        if "kolaborasi" in srv_data["anime"][klb_data["anime"]]:
            join_srv.extend(srv_data["anime"][klb_data["anime"]]["kolaborasi"])
        join_srv = list(dict.fromkeys(join_srv))
        if "kolaborasi" in other_anime_data:
            join_srv.extend(other_anime_data["kolaborasi"])
        join_srv = list(dict.fromkeys(join_srv))
        other_anime_data["kolaborasi"] = join_srv

        srv_data["anime"][klb_data["anime"]]["kolaborasi"] = join_srv
        del srv_data["konfirmasi"][konfirm_id]

        embed = discord.Embed(title="Kolaborasi", color=0x56ACF3)
        embed.add_field(name="Memproses!", value="Mengirim data...", inline=True)
        embed.set_footer(
            text="Dibawakan oleh naoTimes™®", icon_url="https://p.n4o.xyz/i/nao250px.png",
        )
        await emb_msg.edit(embed=embed)

        self.logger.info(f"{server_message}-{srv_source}: storing data...")
        await self.showqueue.add_job(ShowtimesQueueData(source_srv_data, srv_source))
        await self.showqueue.add_job(ShowtimesQueueData(srv_data, server_message))
        embed = discord.Embed(title="Kolaborasi", color=0x96DF6A)
        embed.add_field(
            name="Sukses!",
            value="Berhasil konfirmasi dengan server **{}**.\nDatabase utama akan diupdate sebentar lagi".format(  # noqa: E501
                klb_data["server"]
            ),
            inline=True,
        )
        embed.set_footer(
            text="Dibawakan oleh naoTimes™®", icon_url="https://p.n4o.xyz/i/nao250px.png",
        )
        await emb_msg.delete()
        await ctx.send(embed=embed)

        self.logger.info(f"{server_message}: updating database...")
        success, msg = await self.ntdb.kolaborasi_konfirmasi(
            klb_data["server"], server_message, source_srv_data, srv_data,
        )

        if not success:
            self.logger.error(f"{server_message}: failed to update, reason: {msg}")
            if server_message not in self.bot.showtimes_resync:
                self.bot.showtimes_resync.append(server_message)

        await ctx.send(
            "Berhasil menambahkan kolaborasi dengan **{}** ke dalam database utama naoTimes\nBerikan role berikut agar bisa menggunakan perintah staff <@&{}>".format(  # noqa: E501
                klb_data["server"], ani_srv_role
            )
        )

    @kolaborasi.command(name="batalkan")
    async def kolaborasi_batalkan(self, ctx, server_id, konfirm_id):
        server_message = str(ctx.message.guild.id)
        self.logger.info(f"requested at {server_message}")
        srv_data = await self.showqueue.fetch_database(server_message)

        if srv_data is None:
            return
        self.logger.info(f"{server_message}: data found.")

        if str(ctx.message.author.id) not in srv_data["serverowner"]:
            self.logger.warning(f"{server_message}: not the server admin")
            return await ctx.send("Hanya admin yang bisa membatalkan kolaborasi")

        other_srv_data = await self.showqueue.fetch_database(server_id)
        if other_srv_data is None:
            self.logger.warning(f"{server_message}: can't find target server.")
            return await ctx.send("Tidak dapat menemukan server tersebut di database")

        if "konfirmasi" not in other_srv_data:
            self.logger.warning(f"{server_message}: nothing to confirm.")
            return await ctx.send("Tidak ada kolaborasi yang harus dikonfirmasi.")
        if konfirm_id not in other_srv_data["konfirmasi"]:
            self.logger.warning(f"{server_message}: can't find that confirm id.")
            return await ctx.send("Tidak dapat menemukan kode kolaborasi yang diberikan.")

        del other_srv_data["konfirmasi"][konfirm_id]

        self.logger.info(f"{server_message}-{server_id}: storing data...")
        await self.showqueue.add_job(ShowtimesQueueData(other_srv_data, server_id))
        embed = discord.Embed(title="Kolaborasi", color=0x96DF6A)
        embed.add_field(
            name="Sukses!",
            value="Berhasil membatalkan kode konfirmasi **{}**.\nDatabase utama akan diupdate sebentar lagi".format(  # noqa: E501
                konfirm_id
            ),
            inline=True,
        )
        embed.set_footer(
            text="Dibawakan oleh naoTimes™®", icon_url="https://p.n4o.xyz/i/nao250px.png",
        )
        await ctx.send(embed=embed)

        self.logger.info(f"{server_id}: updating database...")
        success, msg = await self.ntdb.kolaborasi_batalkan(server_id, konfirm_id)

        if not success:
            self.logger.error(f"{server_id}: failed to update, reason: {msg}")
            if server_message not in self.bot.showtimes_resync:
                self.bot.showtimes_resync.append(server_message)

        await ctx.send(
            "Berhasil membatalkan kode konfirmasi **{}** dari database utama naoTimes".format(  # noqa: E501
                konfirm_id
            )
        )

    @kolaborasi.command()
    async def putus(self, ctx, *, judul):
        server_message = str(ctx.message.guild.id)
        self.logger.info(f"requested at {server_message}")
        srv_data = await self.showqueue.fetch_database(server_message)

        if srv_data is None:
            return
        self.logger.info(f"{server_message}: data found.")

        if str(ctx.message.author.id) not in srv_data["serverowner"]:
            return await ctx.send("Hanya admin yang bisa memputuskan kolaborasi")

        srv_anilist, srv_anilist_alias = await self.collect_anime_with_alias(
            srv_data["anime"], srv_data["alias"]
        )

        if not judul:
            return await self.send_all_projects(ctx, srv_anilist, server_message)

        self.logger.info(f"{server_message}: getting close matches...")
        matches = await self.find_any_matches(judul, srv_anilist, srv_anilist_alias, srv_data["alias"])
        if not matches:
            self.logger.warning(f"{server_message}: no matches.")
            return await ctx.send("Tidak dapat menemukan judul tersebut di database")
        elif len(matches) > 1:
            self.logger.info(f"{server_message}: multiple matches!")
            matches = await self.choose_anime(bot=self.bot, ctx=ctx, matches=matches)
            if not matches:
                return await ctx.send("**Dibatalkan!**")

        self.logger.info(f"{server_message}: matched {matches[0]}")
        program_info = srv_data["anime"][matches[0]]

        if "kolaborasi" not in program_info:
            self.logger.warning(f"{server_message}: no registered collaboration on this title.")
            return await ctx.send("Tidak ada kolaborasi sama sekali pada judul ini.")

        self.logger.warning(f"{matches[0]}: start removing server from other server...")
        for osrv in program_info["kolaborasi"]:
            if osrv == server_message:
                continue
            osrv_data = await self.showqueue.fetch_database(osrv)
            klosrv = deepcopy(osrv_data["anime"][matches[0]]["kolaborasi"])
            klosrv.remove(server_message)

            remove_all = False
            if len(klosrv) == 1:
                if klosrv[0] == osrv:
                    remove_all = True

            if remove_all:
                del osrv_data["anime"][matches[0]]["kolaborasi"]
            else:
                osrv_data["anime"][matches[0]]["kolaborasi"] = klosrv
            await self.showqueue.add_job(ShowtimesQueueData(osrv_data, osrv))
            self.logger.info(f"{osrv}: updating database...")
            res2, msg2 = await self.ntdb.update_data_server(osrv, osrv_data)
            if not res2:
                if osrv not in self.bot.showtimes_resync:
                    self.bot.showtimes_resync.append(osrv)
                self.logger.error(f"{osrv}: failed to update, reason: {msg2}")

        self.logger.info(f"{server_message}: storing data...")
        del srv_data["anime"][matches[0]]["kolaborasi"]
        await self.showqueue.add_job(ShowtimesQueueData(srv_data, server_message))
        embed = discord.Embed(title="Kolaborasi", color=0x96DF6A)
        embed.add_field(
            name="Sukses!",
            value="Berhasil memputuskan kolaborasi **{}**.\nDatabase utama akan diupdate sebentar lagi".format(  # noqa: E501
                matches[0]
            ),
            inline=True,
        )
        embed.set_footer(
            text="Dibawakan oleh naoTimes™®", icon_url="https://p.n4o.xyz/i/nao250px.png",
        )
        await ctx.send(embed=embed)

        self.logger.info(f"{server_message}: updating database...")
        success, msg = await self.ntdb.kolaborasi_putuskan(server_message, matches[0])

        if not success:
            self.logger.error(f"{server_message}: failed to update, reason: {msg}")
            if server_message not in self.bot.showtimes_resync:
                self.bot.showtimes_resync.append(server_message)

        await ctx.send(
            "Berhasil memputuskan kolaborasi **{}** dari database utama naoTimes".format(  # noqa: E501
                matches[0]
            )
        )


class ShowtimesData(commands.Cog, ShowtimesBase):
    def __init__(self, bot):
        super(ShowtimesData, self).__init__()
        self.bot = bot
        self.ntdb: naoTimesDB = bot.ntdb
        self.showqueue: ShowtimesQueue = bot.showqueue
        self.srv_fetch = partial(self.fetch_showtimes, cwd=bot.fcwd)
        self.srv_dumps = partial(self.dumps_showtimes, cwd=bot.fcwd)
        self.logger = logging.getLogger("cogs.showtimes_module.admin.ShowtimesData")
        self.fsdb_conn: FansubDBBridge = bot.fsdb

    def __str__(self):
        return "Showtimes Data"

    async def split_search_id(self, dataset: list, needed_id: str, matching_id: int):
        def to_int(x):
            if isinstance(x, str):
                x = int(x)
            return x

        mid_num = len(dataset) // 2
        mid_data = dataset[mid_num]
        match_data = to_int(mid_data[needed_id])
        if match_data == matching_id:
            return mid_data
        elif mid_num > matching_id:
            for data in dataset[:mid_num]:
                if to_int(data[needed_id]) == matching_id:
                    return data
        elif mid_num < matching_id:
            for data in dataset[mid_num:]:
                if to_int(data[needed_id]) == matching_id:
                    return data
        return None

    @commands.command()
    @commands.guild_only()
    async def ubahdata(self, ctx, *, judul):
        server_message = str(ctx.message.guild.id)
        self.logger.info(f"requested at {server_message}")
        srv_data = await self.showqueue.fetch_database(server_message)

        if srv_data is None:
            return
        self.logger.info(f"{server_message}: data found.")

        if str(ctx.message.author.id) not in srv_data["serverowner"]:
            self.logger.warning(f"{server_message}: not the server admin")
            return await ctx.send("Hanya admin yang bisa mengubah data garapan.")

        srv_anilist, srv_anilist_alias = await self.collect_anime_with_alias(
            srv_data["anime"], srv_data["alias"]
        )
        if not judul:
            return await self.send_all_projects(ctx, srv_anilist, server_message)

        self.logger.info(f"{server_message}: getting close matches...")
        matches = await self.find_any_matches(judul, srv_anilist, srv_anilist_alias, srv_data["alias"])
        if not matches:
            self.logger.warning(f"{server_message}: no matches.")
            return await ctx.send("Tidak dapat menemukan judul tersebut di database")
        elif len(matches) > 1:
            self.logger.info(f"{server_message}: multiple matches!")
            matches = await self.choose_anime(bot=self.bot, ctx=ctx, matches=matches)
            if not matches:
                return await ctx.send("**Dibatalkan!**")

        self.logger.info(f"{server_message}: matched {matches[0]}")
        program_info = srv_data["anime"][matches[0]]

        koleb_list = []
        if "kolaborasi" in program_info:
            koleb_data = program_info["kolaborasi"]
            if koleb_data:
                for ko_data in koleb_data:
                    if server_message == ko_data:
                        continue
                    koleb_list.append(ko_data)

        def check_if_author(m):
            return m.author == ctx.message.author

        async def get_user_name(user_id):
            try:
                user_data = self.bot.get_user(int(user_id))
                return "{}#{}".format(user_data.name, user_data.discriminator)
            except Exception:
                return "[Rahasia]"

        async def internal_change_staff(role, staff_list, emb_msg):
            better_names = {
                "TL": "Translator",
                "TLC": "TLCer",
                "ENC": "Encoder",
                "ED": "Editor",
                "TM": "Timer",
                "TS": "Typesetter",
                "QC": "Quality Checker",
            }
            self.logger.info(f"{matches[0]}: changing {role}")
            embed = discord.Embed(title="Mengubah Staff", color=0xEB79B9)
            embed.add_field(
                name="{} ID".format(better_names[role]),
                value="Ketik ID {} atau mention orangnya".format(better_names[role]),
                inline=False,
            )
            embed.set_footer(
                text="Dibawakan oleh naoTimes™®", icon_url="https://p.n4o.xyz/i/nao250px.png",
            )
            await emb_msg.edit(embed=embed)

            while True:
                await_msg = await self.bot.wait_for("message", check=check_if_author)
                mentions = await_msg.mentions
                if not mentions:
                    if await_msg.content.isdigit():
                        staff_list[role] = await_msg.content
                        await await_msg.delete()
                        break
                else:
                    staff_list[role] = str(mentions[0].id)
                    await await_msg.delete()
                    break
            return staff_list, emb_msg

        async def ubah_staff(emb_msg):
            first_run = True
            self.logger.info(f"{matches[0]}: processing staff.")
            while True:
                if first_run:
                    staff_list = deepcopy(srv_data["anime"][matches[0]]["staff_assignment"])
                    staff_list_key = list(staff_list.keys())
                    first_run = False

                staff_list_name = {}
                for k, v in staff_list.items():
                    usr_ = await get_user_name(v)
                    staff_list_name[k] = usr_

                embed = discord.Embed(
                    title="Mengubah Staff", description="Anime: {}".format(matches[0]), color=0xEBA279,
                )
                embed.add_field(name="1⃣ TLor", value=staff_list_name["TL"], inline=False)
                embed.add_field(name="2⃣ TLCer", value=staff_list_name["TLC"], inline=False)
                embed.add_field(
                    name="3⃣ Encoder", value=staff_list_name["ENC"], inline=False,
                )
                embed.add_field(name="4⃣ Editor", value=staff_list_name["ED"], inline=True)
                embed.add_field(name="5⃣ Timer", value=staff_list_name["TM"], inline=True)
                embed.add_field(
                    name="6⃣ Typeseter", value=staff_list_name["TS"], inline=True,
                )
                embed.add_field(name="7⃣ QCer", value=staff_list_name["QC"], inline=True)
                embed.add_field(name="Lain-Lain", value="✅ Selesai!", inline=False)
                embed.set_footer(
                    text="Dibawakan oleh naoTimes™®", icon_url="https://p.n4o.xyz/i/nao250px.png",
                )
                await emb_msg.edit(embed=embed)

                reactmoji = ["1⃣", "2⃣", "3⃣", "4⃣", "5⃣", "6⃣", "7⃣", "✅"]

                for react in reactmoji:
                    await emb_msg.add_reaction(react)

                def check_react(reaction, user):
                    if reaction.message.id != emb_msg.id:
                        return False
                    if user != ctx.message.author:
                        return False
                    if str(reaction.emoji) not in reactmoji:
                        return False
                    return True

                res, user = await self.bot.wait_for("reaction_add", check=check_react)
                if user != ctx.message.author:
                    pass
                elif "✅" in str(res.emoji):
                    await emb_msg.clear_reactions()
                    break
                else:
                    await emb_msg.clear_reactions()
                    reaction_pos = reactmoji.index(str(res.emoji))
                    staff_list, emb_msg = await internal_change_staff(
                        staff_list_key[reaction_pos], staff_list, emb_msg
                    )

            self.logger.info(f"{matches[0]}: setting new staff.")
            srv_data["anime"][matches[0]]["staff_assignment"] = staff_list
            if koleb_list:
                for other_srv in koleb_list:
                    osrv_data = await self.showqueue.fetch_database(other_srv)
                    if osrv_data is None:
                        continue
                    osrv_data["anime"][matches[0]]["staff_assignment"] = staff_list
                    await self.showqueue.add_job(ShowtimesQueueData(osrv_data, other_srv))

            return emb_msg

        async def ubah_role(emb_msg):
            self.logger.info(f"{matches[0]}: processing role.")
            embed = discord.Embed(title="Mengubah Role", color=0xEBA279)
            embed.add_field(
                name="Role ID",
                value="Ketik ID Role atau mention rolenya\n" "Atau ketik `auto` untuk membuatnya otomatis",
                inline=False,
            )
            embed.set_footer(
                text="Dibawakan oleh naoTimes™®", icon_url="https://p.n4o.xyz/i/nao250px.png",
            )
            await emb_msg.edit(embed=embed)

            while True:
                await_msg = await self.bot.wait_for("message", check=check_if_author)
                mentions = await_msg.role_mentions

                if not mentions:
                    if await_msg.content.isdigit():
                        srv_data["anime"][matches[0]]["role_id"] = await_msg.content
                        await await_msg.delete()
                        break
                    elif await_msg.content.startswith("auto"):
                        c_role = await ctx.message.guild.create_role(
                            name=matches[0], colour=discord.Colour(0xDF2705), mentionable=True,
                        )
                        srv_data["anime"][matches[0]]["role_id"] = str(c_role.id)
                        await await_msg.delete()
                        break
                else:
                    srv_data["anime"][matches[0]]["role_id"] = str(mentions[0].id)
                    await await_msg.delete()
                    break

            self.logger.info(f"{matches[0]}: setting role...")
            role_ids = srv_data["anime"][matches[0]]["role_id"]
            await send_timed_msg(ctx, f"Berhasil menambah role ID ke {role_ids}", 2)

            return emb_msg

        async def tambah_episode(emb_msg):
            self.logger.info(f"{matches[0]}: adding new episode...")
            status_list = program_info["status"]
            max_episode = list(status_list.keys())[-1]
            anilist_data = await fetch_anilist(program_info["anilist_id"], 1, max_episode, True)
            time_data = anilist_data["time_data"]

            embed = discord.Embed(
                title="Menambah Episode",
                description="Jumlah Episode Sekarang: {}".format(max_episode),
                color=0xEBA279,
            )
            embed.add_field(
                name="Masukan jumlah episode yang diinginkan.", value=add_eps_instruct, inline=False,
            )
            embed.set_footer(
                text="Dibawakan oleh naoTimes™®", icon_url="https://p.n4o.xyz/i/nao250px.png",
            )
            await emb_msg.edit(embed=embed)

            jumlah_tambahan = None
            while True:
                await_msg = await self.bot.wait_for("message", check=check_if_author)

                if await_msg.content.isdigit():
                    jumlah_tambahan = int(await_msg.content)
                    await await_msg.delete()
                    break

            osrv_dumped = {}
            if koleb_list:
                for osrv in koleb_list:
                    osrv_data = await self.showqueue.fetch_database(osrv)
                    if osrv_data is None:
                        continue
                    osrv_dumped[osrv] = osrv_data

            self.logger.info(f"{matches[0]}: adding a total of {jumlah_tambahan}...")
            for x in range(
                int(max_episode) + 1, int(max_episode) + jumlah_tambahan + 1
            ):  # range(int(c), int(c)+int(x))
                st_data = {}
                staff_status = {}

                staff_status["TL"] = "x"
                staff_status["TLC"] = "x"
                staff_status["ENC"] = "x"
                staff_status["ED"] = "x"
                staff_status["TM"] = "x"
                staff_status["TS"] = "x"
                staff_status["QC"] = "x"

                st_data["status"] = "not_released"
                try:
                    st_data["airing_time"] = time_data[x - 1]
                except IndexError:
                    pass
                st_data["staff_status"] = staff_status
                if osrv_dumped:
                    for osrv, osrv_data in osrv_dumped.items():
                        osrv_data["anime"][matches[0]]["status"][str(x)] = st_data
                        osrv_dumped[osrv] = osrv_data
                srv_data["anime"][matches[0]]["status"][str(x)] = st_data

            if osrv_dumped:
                for osrv, osrv_data in osrv_dumped.items():
                    osrv_data["anime"][matches[0]]["last_update"] = str(int(round(time.time())))
                    await self.showqueue.add_job(ShowtimesQueueData(osrv_data, osrv))
            srv_data["anime"][matches[0]]["last_update"] = str(int(round(time.time())))

            await send_timed_msg(ctx, f"Berhasil menambah {jumlah_tambahan} episode baru", 2)

            return emb_msg

        async def hapus_episode(emb_msg):
            self.logger.info(f"{matches[0]}: removing an episodes...")
            status_list = program_info["status"]
            max_episode = list(status_list.keys())[-1]

            embed = discord.Embed(
                title="Menghapus Episode",
                description="Jumlah Episode Sekarang: {}".format(max_episode),
                color=0xEBA279,
            )
            embed.add_field(
                name="Masukan range episode yang ingin dihapus.", value=del_eps_instruct, inline=False,
            )
            embed.set_footer(
                text="Dibawakan oleh naoTimes™®", icon_url="https://p.n4o.xyz/i/nao250px.png",
            )
            await emb_msg.edit(embed=embed)

            jumlah_tambahan = None
            while True:
                await_msg = await self.bot.wait_for("message", check=check_if_author)

                jumlah_tambahan = await_msg.content
                embed = discord.Embed(title="Menghapus Episode", color=0xEBA279)
                embed.add_field(
                    name="Apakah Yakin?", value="Range episode: **{}**".format(jumlah_tambahan), inline=False,
                )
                embed.set_footer(
                    text="Dibawakan oleh naoTimes™®", icon_url="https://p.n4o.xyz/i/nao250px.png",
                )
                await emb_msg.edit(embed=embed)

                reactmoji = ["✅", "❌"]

                for react in reactmoji:
                    await emb_msg.add_reaction(react)

                def check_react(reaction, user):
                    if reaction.message.id != emb_msg.id:
                        return False
                    if user != ctx.message.author:
                        return False
                    if str(reaction.emoji) not in reactmoji:
                        return False
                    return True

                res, user = await self.bot.wait_for("reaction_add", check=check_react)
                if user != ctx.message.author:
                    pass
                elif "✅" in str(res.emoji):
                    await await_msg.delete()
                    await emb_msg.clear_reactions()
                    break
                elif "❌" in str(res.emoji):
                    await await_msg.delete()
                    embed = discord.Embed(
                        title="Menghapus Episode",
                        description="Jumlah Episode Sekarang: {}".format(max_episode),
                        color=0xEBA279,
                    )
                    embed.add_field(
                        name="Masukan range episode yang ingin dihapus.",
                        value=del_eps_instruct,
                        inline=False,
                    )
                    embed.set_footer(
                        text="Dibawakan oleh naoTimes™®", icon_url="https://p.n4o.xyz/i/nao250px.png",
                    )
                    await emb_msg.edit(embed=embed)
                await emb_msg.clear_reactions()

            total_episode = jumlah_tambahan.split("-")
            if len(total_episode) < 2:
                current = int(total_episode[0])
                total = int(total_episode[0])
            else:
                current = int(total_episode[0])
                total = int(total_episode[1])

            if koleb_list:
                for osrv in koleb_list:
                    osrv_data = await self.showqueue.fetch_database(osrv)
                    if osrv_data is None:
                        continue
                    for x in range(current, total + 1):  # range(int(c), int(c)+int(x))
                        del osrv_data["anime"][matches[0]]["status"][str(x)]
                    osrv_data["anime"][matches[0]]["last_update"] = str(int(round(time.time())))
                    await self.showqueue.add_job(ShowtimesQueueData(osrv_data, osrv))

            self.logger.info(f"{matches[0]}: removing a total of {total} episodes...")
            for x in range(current, total + 1):  # range(int(c), int(c)+int(x))
                del srv_data["anime"][matches[0]]["status"][str(x)]
            srv_data["anime"][matches[0]]["last_update"] = str(int(round(time.time())))

            await send_timed_msg(ctx, f"Berhasil menghapus episode {current} ke {total}", 2)

            return emb_msg

        async def hapus_utang_tanya(emb_msg):
            delete_ = False
            self.logger.info(f"{matches[0]}: preparing to nuke project...")
            while True:
                embed = discord.Embed(
                    title="Menghapus Utang", description="Anime: {}".format(matches[0]), color=0xCC1C20,
                )
                embed.add_field(
                    name="Peringatan!",
                    value="Utang akan dihapus selama-lamanya dan tidak bisa "
                    "dikembalikan!\nLanjutkan proses?",
                    inline=False,
                )
                embed.set_footer(
                    text="Dibawakan oleh naoTimes™®", icon_url="https://p.n4o.xyz/i/nao250px.png",
                )
                await emb_msg.edit(embed=embed)

                reactmoji = ["✅", "❌"]

                for react in reactmoji:
                    await emb_msg.add_reaction(react)

                def check_react(reaction, user):
                    if reaction.message.id != emb_msg.id:
                        return False
                    if user != ctx.message.author:
                        return False
                    if str(reaction.emoji) not in reactmoji:
                        return False
                    return True

                res, user = await self.bot.wait_for("reaction_add", check=check_react)
                if user != ctx.message.author:
                    pass
                elif "✅" in str(res.emoji):
                    await emb_msg.clear_reactions()
                    delete_ = True
                    break
                elif "❌" in str(res.emoji):
                    await emb_msg.clear_reactions()
                    break
                await emb_msg.clear_reactions()
            return emb_msg, delete_

        first_run = True
        exit_command = False
        hapus_utang = False
        while True:
            guild_roles = ctx.message.guild.roles
            total_episodes = len(srv_data["anime"][matches[0]]["status"])
            role_id = srv_data["anime"][matches[0]]["role_id"]
            embed = discord.Embed(
                title="Mengubah Data", description="Anime: {}".format(matches[0]), color=0xE7E363,
            )
            embed.add_field(
                name="1⃣ Ubah Staff", value="Ubah staff yang mengerjakan anime ini.", inline=False,
            )
            embed.add_field(
                name="2⃣ Ubah Role",
                value="Ubah role discord yang digunakan:\n"
                "Role sekarang: {}".format(self.get_role_name(role_id, guild_roles)),
                inline=False,
            )
            embed.add_field(
                name="3⃣ Tambah Episode",
                value="Tambah jumlah episode\n" "Total Episode sekarang: {}".format(total_episodes),
                inline=False,
            )
            embed.add_field(
                name="4⃣ Hapus Episode", value="Hapus episode tertentu.", inline=False,
            )
            embed.add_field(
                name="5⃣ Drop Garapan",
                value="Menghapus garapan ini dari daftar utang " "untuk selama-lamanya...",
                inline=False,
            )
            embed.add_field(name="Lain-Lain", value="✅ Selesai!\n❌ Batalkan!", inline=False)
            embed.set_footer(
                text="Dibawakan oleh naoTimes™®", icon_url="https://p.n4o.xyz/i/nao250px.png",
            )
            if first_run:
                emb_msg = await ctx.send(embed=embed)
                first_run = False
            else:
                await emb_msg.edit(embed=embed)

            reactmoji = ["1⃣", "2⃣", "3⃣", "4⃣", "5⃣", "✅", "❌"]

            for react in reactmoji:
                await emb_msg.add_reaction(react)

            def check_react(reaction, user):
                if reaction.message.id != emb_msg.id:
                    return False
                if user != ctx.message.author:
                    return False
                if str(reaction.emoji) not in reactmoji:
                    return False
                return True

            res, user = await self.bot.wait_for("reaction_add", check=check_react)
            if user != ctx.message.author:
                pass
            elif reactmoji[0] in str(res.emoji):
                await emb_msg.clear_reactions()
                emb_msg = await ubah_staff(emb_msg)
            elif reactmoji[1] in str(res.emoji):
                await emb_msg.clear_reactions()
                emb_msg = await ubah_role(emb_msg)
            elif reactmoji[2] in str(res.emoji):
                await emb_msg.clear_reactions()
                emb_msg = await tambah_episode(emb_msg)
            elif reactmoji[3] in str(res.emoji):
                await emb_msg.clear_reactions()
                emb_msg = await hapus_episode(emb_msg)
            elif reactmoji[4] in str(res.emoji):
                await emb_msg.clear_reactions()
                emb_msg, hapus_utang = await hapus_utang_tanya(emb_msg)
                if hapus_utang:
                    await emb_msg.delete()
                    break
            elif reactmoji[5] in str(res.emoji):
                await emb_msg.clear_reactions()
                await emb_msg.delete()
                break
            elif reactmoji[6] in str(res.emoji):
                await emb_msg.clear_reactions()
                await emb_msg.delete()
                exit_command = True
                break

        if exit_command:
            self.logger.warning(f"{matches[0]}: cancelling...")
            return await ctx.send("**Dibatalkan!**")
        if hapus_utang:
            self.logger.warning(f"{matches[0]}: nuking project...")
            current = self.get_current_ep(program_info["status"])
            try:
                if program_info["status"]["1"]["status"] == "not_released":
                    announce_it = False
                elif not current:
                    announce_it = False
                else:
                    announce_it = True
            except KeyError:
                announce_it = True

            del srv_data["anime"][matches[0]]
            for osrv in koleb_list:
                osrv_data = await self.showqueue.fetch_database(osrv)
                if osrv_data is None:
                    continue
                if "kolaborasi" in osrv_data["anime"][matches[0]]:
                    if server_message in osrv_data["anime"][matches[0]]["kolaborasi"]:
                        klosrv = deepcopy(osrv_data["anime"][matches[0]]["kolaborasi"])
                        klosrv.remove(server_message)

                        remove_all = False
                        if len(klosrv) == 1:
                            if klosrv[0] == osrv:
                                remove_all = True

                        if remove_all:
                            del osrv_data["anime"][matches[0]]["kolaborasi"]
                        else:
                            osrv_data["anime"][matches[0]]["kolaborasi"] = klosrv
                        await self.showqueue.add_job(ShowtimesQueueData(osrv_data, osrv))

            await self.showqueue.add_job(ShowtimesQueueData(srv_data, server_message))
            self.logger.info(f"{matches[0]}: storing final data...")
            await ctx.send("Berhasil menghapus **{}** dari daftar utang".format(matches[0]))

            self.logger.info(f"{server_message}: updating database...")
            success, msg = await self.ntdb.update_data_server(server_message, srv_data)
            for osrv in koleb_list:
                if osrv == server_message:
                    continue
                osrv_data = await self.showqueue.fetch_database(osrv)
                if osrv_data is None:  # Skip if the server doesn't exist :pepega:
                    continue
                self.logger.info(f"{osrv}: updating database...")
                res2, msg2 = await self.ntdb.update_data_server(osrv, osrv_data)
                if not res2:
                    if osrv not in self.bot.showtimes_resync:
                        self.bot.showtimes_resync.append(osrv)
                    self.logger.error(f"{osrv}: failed to update, reason: {msg2}")

            if not success:
                self.logger.error(f"{server_message}: failed to update, reason: {msg}")
                if server_message not in self.bot.showtimes_resync:
                    self.bot.showtimes_resync.append(server_message)

            if "announce_channel" in srv_data:
                announce_chan = srv_data["announce_channel"]
                target_chan = self.bot.get_channel(int(announce_chan))
                embed = discord.Embed(title="{}".format(matches[0]), color=0xB51E1E)
                embed.add_field(
                    name="Dropped...",
                    value="{} telah di drop dari fansub ini :(".format(matches[0]),
                    inline=False,
                )
                embed.set_footer(text=f"Pada: {get_current_time()}")
                if announce_it:
                    self.logger.info(f"{server_message}: announcing removal of a project...")
                    if target_chan:
                        await target_chan.send(embed=embed)
            return

        self.logger.info(f"{matches[0]}: saving new data...")
        await self.showqueue.add_job(ShowtimesQueueData(srv_data, server_message))

        self.logger.info(f"{server_message}: updating database...")
        success, msg = await self.ntdb.update_data_server(server_message, srv_data)
        for osrv in koleb_list:
            if osrv == server_message:
                continue
            osrv_data = await self.showqueue.fetch_database(osrv)
            if osrv_data is None:  # Skip if the server doesn't exist :pepega:
                continue
            self.logger.info(f"{osrv}: updating database...")
            res2, msg2 = await self.ntdb.update_data_server(osrv, osrv_data)
            if not res2:
                if osrv not in self.bot.showtimes_resync:
                    self.bot.showtimes_resync.append(osrv)
                self.logger.error(f"{osrv}: failed to update, reason: {msg2}")

        if not success:
            self.logger.error(f"{server_message}: failed to update, reason: {msg}")
            if server_message not in self.bot.showtimes_resync:
                self.bot.showtimes_resync.append(server_message)

        await ctx.send("Berhasil menyimpan data baru untuk garapan **{}**".format(matches[0]))

    @commands.command(aliases=["addnew"])
    @commands.guild_only()
    async def tambahutang(self, ctx):
        """
        Membuat utang baru, ambil semua user id dan role id yang diperlukan.
        ----
        Menggunakan embed agar terlihat lebih enak dibanding sebelumnya
        Merupakan versi 2
        """
        server_message = str(ctx.message.guild.id)
        self.logger.info(f"requested at {server_message}")
        srv_data = await self.showqueue.fetch_database(server_message)

        if srv_data is None:
            return
        self.logger.info(f"{server_message}: data found.")

        if str(ctx.message.author.id) not in srv_data["serverowner"]:
            self.logger.warning(f"{server_message}: not the server admin")
            return await ctx.send("Hanya admin yang bisa menambah utang")

        srv_anilist, _ = await self.collect_anime_with_alias(srv_data["anime"], srv_data["alias"])

        self.logger.info(f"{server_message}: creating initial data...")
        embed = discord.Embed(title="Menambah Utang", color=0x56ACF3)
        embed.add_field(name="Memulai Proses!", value="Mempersiapkan...", inline=False)
        embed.set_footer(
            text="Dibawakan oleh naoTimes™®", icon_url="https://p.n4o.xyz/i/nao250px.png",
        )
        emb_msg = await ctx.send(embed=embed)
        current_time = int(round(time.time()))
        msg_author = ctx.message.author
        json_tables = {
            "ani_title": "",
            "anilist_id": "",
            "episodes": "",
            "time_data": "",
            "poster_img": "",
            "role_id": "",
            "tlor_id": "",
            "tlcer_id": "",
            "encoder_id": "",
            "editor_id": "",
            "timer_id": "",
            "tser_id": "",
            "qcer_id": "",
            "start_time": 0,
            "settings": {"time_data_are_the_same": False},
            "old_time_data": [],
        }
        cancel_toggled = False  # Some easy check if it's gonna fucked up
        first_time = True

        def check_if_author(m):
            return m.author == msg_author

        async def process_episode(table, emb_msg):
            self.logger.info(f"{server_message}: processing total episodes...")
            embed = discord.Embed(title="Menambah Utang", color=0x96DF6A)
            embed.set_thumbnail(url=table["poster_img"])
            embed.add_field(
                name="Jumlah Episode", value="Ketik Jumlah Episode perkiraan", inline=False,
            )
            embed.set_footer(
                text="Dibawakan oleh naoTimes™®", icon_url="https://p.n4o.xyz/i/nao250px.png",
            )
            await emb_msg.edit(embed=embed)

            while True:
                await_msg = await self.bot.wait_for("message", check=check_if_author)

                if await_msg.content.isdigit():
                    await await_msg.delete()
                    break

                await await_msg.delete()

            anilist_data = await fetch_anilist(table["anilist_id"], 1, int(await_msg.content), True)
            table["episodes"] = anilist_data["total_episodes"]
            table["time_data"] = anilist_data["time_data"]

            return table, emb_msg

        async def process_anilist(table, emb_msg):
            self.logger.info(f"{server_message}: processing anime data...")
            embed = discord.Embed(title="Menambah Utang", color=0x96DF6A)
            embed.add_field(
                name="Anilist ID",
                value="Ketik ID Anilist untuk anime yang diinginkan\n\n"
                "Bisa gunakan `!anime <judul>` dan melihat bagian bawah "
                "untuk IDnya\n\nKetik *cancel* untuk membatalkan proses",
                inline=False,
            )
            embed.set_footer(
                text="Dibawakan oleh naoTimes™®", icon_url="https://p.n4o.xyz/i/nao250px.png",
            )
            await emb_msg.edit(content="", embed=embed)

            while True:
                await_msg = await self.bot.wait_for("message", check=check_if_author)

                if not await_msg.content.startswith("!anime"):
                    if await_msg.content == ("cancel"):
                        return False, "Dibatalkan oleh user."

                    if await_msg.content.isdigit():
                        await await_msg.delete()
                        break

                    await await_msg.delete()

            anilist_data = await fetch_anilist(await_msg.content, 1, 1, True)
            poster_data, title = anilist_data["poster_data"], anilist_data["title"]
            time_data, episodes_total = anilist_data["time_data"], anilist_data["total_episodes"]
            poster_image, poster_color = poster_data["image"], poster_data["color"]

            embed = discord.Embed(title="Menambah Utang", color=0x96DF6A)
            embed.set_thumbnail(url=poster_image)
            embed.add_field(
                name="Apakah benar?", value="Judul: **{}**".format(title), inline=False,
            )
            embed.set_footer(
                text="Dibawakan oleh naoTimes™®", icon_url="https://p.n4o.xyz/i/nao250px.png",
            )
            await emb_msg.edit(embed=embed)

            to_react = ["✅", "❌"]
            for reaction in to_react:
                await emb_msg.add_reaction(reaction)

            def check_react(reaction, user):
                if reaction.message.id != emb_msg.id:
                    return False
                if user != ctx.message.author:
                    return False
                if str(reaction.emoji) not in to_react:
                    return False
                return True

            res, user = await self.bot.wait_for("reaction_add", check=check_react)
            if user != ctx.message.author:
                pass
            elif "✅" in str(res.emoji):
                try:
                    ani_air_data = await fetch_anilist(await_msg.content, 1, 1, return_only_time=True)
                    start_time = ani_air_data["airing_start"]
                except Exception:
                    self.logger.warning(
                        f"{server_message}: failed to fetch air start, please try again later."
                    )
                    return (
                        False,
                        "Gagal mendapatkan start_date, silakan coba lagi ketika sudah "
                        "ada kepastian kapan animenya mulai.",
                    )
                table["ani_title"] = title
                table["poster_data"] = {
                    "url": poster_image,
                    "color": poster_color,
                }
                table["anilist_id"] = str(await_msg.content)
                table["start_time"] = start_time
                await emb_msg.clear_reactions()
            elif "❌" in str(res.emoji):
                await emb_msg.clear_reactions()
                return False, "Dibatalkan oleh user."

            if episodes_total == 1:
                self.logger.info(f"{server_message}: asking episode total to user...")
                table, emb_msg = await process_episode(table, emb_msg)
            else:
                self.logger.info(f"{server_message}: using anilist episode total...")
                table["episodes"] = episodes_total
                table["time_data"] = time_data

            return table, emb_msg

        async def process_role(table, emb_msg):
            self.logger.info(f"{server_message}: processing roles")
            embed = discord.Embed(title="Menambah Utang", color=0x96DF6A)
            embed.set_thumbnail(url=table["poster_img"])
            embed.add_field(
                name="Role ID",
                value="Ketik ID Role atau mention rolenya\n" "Atau ketik `auto` untuk membuatnya otomatis",
                inline=False,
            )
            embed.set_footer(
                text="Dibawakan oleh naoTimes™®", icon_url="https://p.n4o.xyz/i/nao250px.png",
            )
            await emb_msg.edit(embed=embed)

            while True:
                await_msg = await self.bot.wait_for("message", check=check_if_author)

                mentions = await_msg.role_mentions

                if not mentions:
                    if await_msg.content.isdigit():
                        table["role_id"] = await_msg.content
                        await await_msg.delete()
                    elif await_msg.content.startswith("auto"):
                        self.logger.info(f"{server_message}: auto-generating role...")
                        c_role = await ctx.message.guild.create_role(
                            name=table["ani_title"], colour=discord.Colour(0xDF2705), mentionable=True,
                        )
                        table["role_id"] = str(c_role.id)
                        await await_msg.delete()
                else:
                    table["role_id"] = mentions[0].id
                    await await_msg.delete()
                break

            return table, emb_msg

        async def process_staff(table, emb_msg, staffer):
            staffer_mapping = {
                "tl": {"b": "tlor_id", "n": "Translator"},
                "tlc": {"b": "tlcer_id", "n": "TLCer"},
                "enc": {"b": "encoder_id", "n": "Encoder"},
                "ed": {"b": "editor_id", "n": "Editor"},
                "ts": {"b": "tser_id", "n": "Penata Rias"},
                "tm": {"b": "timer_id", "n": "Penata Waktu"},
                "qc": {"b": "qcer_id", "n": "Pemeriksa Akhir"},
            }
            staff_need = staffer_mapping.get(staffer)
            staff_name, table_map = staff_need["n"], staff_need["b"]
            self.logger.info(f"{server_message}: processing {staff_name}")
            embed = discord.Embed(title="Menambah Utang", color=0x96DF6A)
            embed.set_thumbnail(url=table["poster_img"])
            embed.add_field(
                name=f"{staff_name} ID",
                value=f"Ketik ID Discord {staff_name} atau mention orangnya",
                inline=False,
            )
            embed.set_footer(
                text="Dibawakan oleh naoTimes™®", icon_url="https://p.n4o.xyz/i/nao250px.png",
            )
            await emb_msg.edit(embed=embed)

            while True:
                await_msg = await self.bot.wait_for("message", check=check_if_author)
                mentions = await_msg.mentions
                if not mentions:
                    if await_msg.content.isdigit():
                        table[table_map] = await_msg.content
                        await await_msg.delete()
                        break
                else:
                    table[table_map] = mentions[0].id
                    await await_msg.delete()
                    break
                # await await_msg.delete()

            return table, emb_msg

        def check_setting(gear):
            if not gear:
                return "❌"
            return "✅"

        async def process_pengaturan(table, emb_msg):
            # Inner settings
            async def gear_1(table, emb_msg, gear_data):
                self.logger.info("pengaturan: setting all time data to be the same.")
                if not gear_data:
                    table["old_time_data"] = table["time_data"]  # Make sure old time data are not deleted
                    time_table = table["time_data"]
                    new_time_table = []
                    for _ in time_table:
                        new_time_table.append(time_table[0])

                    table["time_data"] = new_time_table
                    table["settings"]["time_data_are_the_same"] = True
                    return table, emb_msg

                new_time_table = []
                for i, _ in enumerate(table["time_data"]):
                    new_time_table.append(table["old_time_data"][i])

                # Remove old time data because it resetted
                table["old_time_data"] = []
                table["settings"]["time_data_are_the_same"] = False
                return table, emb_msg

            self.logger.info("showing settings...")
            while True:
                embed = discord.Embed(title="Menambah Utang", color=0x96DF6A)
                embed.set_thumbnail(url=table["poster_img"])
                embed.add_field(
                    name="1⃣ Samakan waktu tayang",
                    value="Status: **{}**\n\nBerguna untuk anime Netflix yang sekali rilis banyak".format(  # noqa: E501
                        check_setting(table["settings"]["time_data_are_the_same"])
                    ),
                    inline=False,
                )
                embed.add_field(name="Lain-Lain", value="⏪ Kembali", inline=False)
                embed.set_footer(
                    text="Dibawakan oleh naoTimes™®", icon_url="https://p.n4o.xyz/i/nao250px.png",
                )
                await emb_msg.edit(embed=embed)

                to_react = [
                    "1⃣",
                    "⏪",
                ]
                for reaction in to_react:
                    await emb_msg.add_reaction(reaction)

                def check_react(reaction, user):
                    if reaction.message.id != emb_msg.id:
                        return False
                    if user != ctx.message.author:
                        return False
                    if str(reaction.emoji) not in to_react:
                        return False
                    return True

                res, user = await self.bot.wait_for("reaction_add", check=check_react)
                if user != ctx.message.author:
                    pass
                elif to_react[0] in str(res.emoji):
                    await emb_msg.clear_reactions()
                    table, emb_msg = await gear_1(
                        table, emb_msg, table["settings"]["time_data_are_the_same"],
                    )
                elif to_react[-1] in str(res.emoji):
                    await emb_msg.clear_reactions()
                    return table, emb_msg

        json_tables, emb_msg = await process_anilist(json_tables, emb_msg)

        if not json_tables:
            self.logger.warning(f"{server_message}: process cancelled")
            return await ctx.send(emb_msg)

        if json_tables["ani_title"] in srv_anilist:
            self.logger.warning(f"{server_message}: anime already registered on database.")
            return await ctx.send("Anime sudah didaftarkan di database.")

        json_tables, emb_msg = await process_role(json_tables, emb_msg)
        json_tables, emb_msg = await process_staff(json_tables, emb_msg, "tl")
        json_tables, emb_msg = await process_staff(json_tables, emb_msg, "tlc")
        json_tables, emb_msg = await process_staff(json_tables, emb_msg, "enc")
        json_tables, emb_msg = await process_staff(json_tables, emb_msg, "ed")
        json_tables, emb_msg = await process_staff(json_tables, emb_msg, "tm")
        json_tables, emb_msg = await process_staff(json_tables, emb_msg, "ts")
        json_tables, emb_msg = await process_staff(json_tables, emb_msg, "qc")

        async def fetch_username_from_id(_id):
            try:
                user_data = self.bot.get_user(int(_id))
                return "{}#{}".format(user_data.name, user_data.discriminator)
            except Exception:
                return "[Rahasia]"

        self.logger.info(f"{server_message}: checkpoint before commiting")
        while True:
            tl_ = await fetch_username_from_id(json_tables["tlor_id"])
            tlc_ = await fetch_username_from_id(json_tables["tlcer_id"])
            enc_ = await fetch_username_from_id(json_tables["encoder_id"])
            ed_ = await fetch_username_from_id(json_tables["editor_id"])
            tm_ = await fetch_username_from_id(json_tables["timer_id"])
            ts_ = await fetch_username_from_id(json_tables["tser_id"])
            qc_ = await fetch_username_from_id(json_tables["qcer_id"])

            embed = discord.Embed(
                title="Menambah Utang", description="Periksa data!\nReact jika ingin diubah.", color=0xE7E363,
            )
            embed.set_thumbnail(url=json_tables["poster_img"])
            embed.add_field(
                name="1⃣ Judul",
                value="{} ({})".format(json_tables["ani_title"], json_tables["anilist_id"]),
                inline=False,
            )
            embed.add_field(
                name="2⃣ Episode", value="{}".format(json_tables["episodes"]), inline=False,
            )
            embed.add_field(
                name="3⃣ Role",
                value="{}".format(self.get_role_name(json_tables["role_id"], ctx.message.guild.roles)),
                inline=False,
            )
            embed.add_field(name="4⃣ Translator", value=tl_, inline=True)
            embed.add_field(name="5⃣ TLCer", value=tlc_, inline=True)
            embed.add_field(name="6⃣ Encoder", value=enc_, inline=True)
            embed.add_field(name="7⃣ Editor", value=ed_, inline=True)
            embed.add_field(name="8⃣ Timer", value=tm_, inline=True)
            embed.add_field(name="9⃣ Typesetter", value=ts_, inline=True)
            embed.add_field(name="0⃣ Quality Checker", value=qc_, inline=True)
            embed.add_field(
                name="Lain-Lain", value="🔐 Pengaturan\n✅ Tambahkan!\n❌ Batalkan!", inline=False,
            )
            embed.set_footer(
                text="Dibawakan oleh naoTimes™®", icon_url="https://p.n4o.xyz/i/nao250px.png",
            )
            if first_time:
                await emb_msg.delete()
                emb_msg = await ctx.send(embed=embed)
                first_time = False
            else:
                await emb_msg.edit(embed=embed)

            to_react = [
                "1⃣",
                "2⃣",
                "3⃣",
                "4⃣",
                "5⃣",
                "6⃣",
                "7⃣",
                "8⃣",
                "9⃣",
                "0⃣",
                "🔐",
                "✅",
                "❌",
            ]
            for reaction in to_react:
                await emb_msg.add_reaction(reaction)

            def check_react(reaction, user):
                if reaction.message.id != emb_msg.id:
                    return False
                if user != ctx.message.author:
                    return False
                if str(reaction.emoji) not in to_react:
                    return False
                return True

            res, user = await self.bot.wait_for("reaction_add", check=check_react)
            if user != ctx.message.author:
                pass
            elif to_react[0] in str(res.emoji):
                await emb_msg.clear_reactions()
                json_tables, emb_msg = await process_anilist(json_tables, emb_msg)
            elif to_react[1] in str(res.emoji):
                await emb_msg.clear_reactions()
                json_tables, emb_msg = await process_episode(json_tables, emb_msg)
            elif to_react[2] in str(res.emoji):
                await emb_msg.clear_reactions()
                json_tables, emb_msg = await process_role(json_tables, emb_msg)
            elif to_react[3] in str(res.emoji):
                await emb_msg.clear_reactions()
                json_tables, emb_msg = await process_staff(json_tables, emb_msg, "tl")
            elif to_react[4] in str(res.emoji):
                await emb_msg.clear_reactions()
                json_tables, emb_msg = await process_staff(json_tables, emb_msg, "tlc")
            elif to_react[5] in str(res.emoji):
                await emb_msg.clear_reactions()
                json_tables, emb_msg = await process_staff(json_tables, emb_msg, "enc")
            elif to_react[6] in str(res.emoji):
                await emb_msg.clear_reactions()
                json_tables, emb_msg = await process_staff(json_tables, emb_msg, "ed")
            elif to_react[7] in str(res.emoji):
                await emb_msg.clear_reactions()
                json_tables, emb_msg = await process_staff(json_tables, emb_msg, "tm")
            if to_react[8] in str(res.emoji):
                await emb_msg.clear_reactions()
                json_tables, emb_msg = await process_staff(json_tables, emb_msg, "ts")
            elif to_react[9] in str(res.emoji):
                await emb_msg.clear_reactions()
                json_tables, emb_msg = await process_staff(json_tables, emb_msg, "qc")
            elif "🔐" in str(res.emoji):
                await emb_msg.clear_reactions()
                json_tables, emb_msg = await process_pengaturan(json_tables, emb_msg)
            elif "✅" in str(res.emoji):
                await emb_msg.clear_reactions()
                break
            elif "❌" in str(res.emoji):
                self.logger.warning(f"{server_message}: process cancelled")
                cancel_toggled = True
                await emb_msg.clear_reactions()
                break

        if cancel_toggled:
            return await ctx.send("**Dibatalkan!**")

        # Everything are done and now processing data
        self.logger.info(f"{server_message}: commiting data to database...")
        embed = discord.Embed(title="Menambah Utang", color=0x56ACF3)
        embed.add_field(name="Memproses!", value="Membuat data...", inline=True)
        embed.set_footer(
            text="Dibawakan oleh naoTimes™®", icon_url="https://p.n4o.xyz/i/nao250px.png",
        )
        await emb_msg.edit(embed=embed)

        new_anime_data = {}
        staff_data = {}
        status = {}

        new_anime_data["anilist_id"] = json_tables["anilist_id"]
        new_anime_data["last_update"] = str(current_time)
        new_anime_data["role_id"] = json_tables["role_id"]
        new_anime_data["poster_data"] = json_tables["poster_data"]
        new_anime_data["start_time"] = json_tables["start_time"]

        staff_data["TL"] = json_tables["tlor_id"]
        staff_data["TLC"] = json_tables["tlcer_id"]
        staff_data["ENC"] = json_tables["encoder_id"]
        staff_data["ED"] = json_tables["editor_id"]
        staff_data["TM"] = json_tables["timer_id"]
        staff_data["TS"] = json_tables["tser_id"]
        staff_data["QC"] = json_tables["qcer_id"]
        new_anime_data["staff_assignment"] = staff_data

        self.logger.info(f"{server_message}: generating episode...")
        for x in range(int(json_tables["episodes"])):
            st_data = {}
            staff_status = {}

            staff_status["TL"] = "x"
            staff_status["TLC"] = "x"
            staff_status["ENC"] = "x"
            staff_status["ED"] = "x"
            staff_status["TM"] = "x"
            staff_status["TS"] = "x"
            staff_status["QC"] = "x"

            st_data["status"] = "not_released"
            st_data["airing_time"] = json_tables["time_data"][x]
            st_data["staff_status"] = staff_status
            status[str(x + 1)] = st_data

        new_anime_data["status"] = status

        srv_data["anime"][json_tables["ani_title"]] = new_anime_data

        embed = discord.Embed(title="Menambah Utang", color=0x56ACF3)
        embed.add_field(name="Memproses!", value="Mengirim data...", inline=True)
        embed.set_footer(
            text="Dibawakan oleh naoTimes™®", icon_url="https://p.n4o.xyz/i/nao250px.png",
        )
        await emb_msg.edit(embed=embed)

        self.logger.info(f"{server_message}: saving to local database...")
        await self.showqueue.add_job(ShowtimesQueueData(srv_data, server_message))
        embed = discord.Embed(title="Menambah Utang", color=0x96DF6A)
        embed.add_field(
            name="Sukses!",
            value="**{}** telah ditambahkan ke database\nDatabase utama akan diupdate sebentar lagi".format(  # noqa: E501
                json_tables["ani_title"]
            ),
            inline=True,
        )
        embed.set_footer(
            text="Dibawakan oleh naoTimes™®", icon_url="https://p.n4o.xyz/i/nao250px.png",
        )
        await ctx.send(embed=embed)

        self.logger.info(f"{server_message}: updating database...")
        success, msg = await self.ntdb.update_data_server(server_message, srv_data)
        await emb_msg.delete()

        if not success:
            self.logger.error(f"{server_message}: failed to update, reason: {msg}")
            if server_message not in self.bot.showtimes_resync:
                self.bot.showtimes_resync.append(server_message)

        self.logger.info(f"{server_message}: done processing!")
        await ctx.send(
            "Berhasil menambahkan **{}** ke dalam database utama naoTimes".format(  # noqa: E501
                json_tables["ani_title"]
            )
        )

    @commands.command(aliases=["fsdb_integrate"])
    async def integrasi_fsdb(self, ctx):
        server_message = str(ctx.message.guild.id)
        self.logger.info(f"requested at {server_message}")
        srv_data = await self.showqueue.fetch_database(server_message)

        if srv_data is None:
            return
        self.logger.info(f"{server_message}: data found.")

        if str(ctx.message.author.id) not in srv_data["serverowner"]:
            self.logger.warning(f"{server_message}: not the server admin")
            return await ctx.send("Hanya admin yang bisa menambah utang")

        if "fsdb_data" in srv_data:
            self.logger.warning(f"{server_message}: already integrated with fsdb.")
            return await ctx.send("Fansub sudah terintegrasi dengan FansubDB.")

        srv_anilist, _ = await self.collect_anime_with_alias(srv_data["anime"], srv_data["alias"])

        self.logger.info(f"{server_message}: creating initial data...")
        embed = discord.Embed(title="Integrasi FansubDB", color=0x56ACF3)
        embed.add_field(name="Memulai Proses!", value="Mempersiapkan...", inline=False)
        embed.set_footer(
            text="Dibawakan oleh naoTimes™®", icon_url="https://p.n4o.xyz/i/nao250px.png",
        )
        emb_msg = await ctx.send(embed=embed)
        msg_author = ctx.message.author
        json_tables = {
            "fs_id": "",
        }
        cancel_toggled = False  # Some easy check if it's gonna fucked up
        first_time = True

        def check_if_author(m):
            return m.author == msg_author

        async def process_fsdb(table, emb_msg):
            self.logger.info(f"{server_message}: processing anime data...")
            embed = discord.Embed(title="Menambah Utang", color=0x96DF6A)
            embed.add_field(
                name="Fansub ID",
                value="Ketik ID Fansub yang terdaftar di FansubDB.\n\n"
                "Gunakan `!fsdb fansub <pencarian>` untuk mencari ID fansub."
                "\n\nKetik *cancel* untuk membatalkan proses",
                inline=False,
            )
            embed.set_footer(
                text="Dibawakan oleh naoTimes™®", icon_url="https://p.n4o.xyz/i/nao250px.png",
            )
            await emb_msg.edit(content="", embed=embed)

            while True:
                await_msg = await self.bot.wait_for("message", check=check_if_author)

                if not await_msg.content.startswith("!fsdb"):
                    if await_msg.content == ("cancel"):
                        return False, "Dibatalkan oleh user."

                    if await_msg.content.isdigit():
                        await await_msg.delete()
                        break

                    await await_msg.delete()

            table["fs_id"] = int(await_msg.content)
            return table, emb_msg

        async def find_fansub_name(fansub_id: int):
            res, all_fansubs = self.fsdb_conn.fetch_fansubs()[""]
            fansub_name = "Tidak diketahui"
            if not res:
                return fansub_name

            fs_data = await self.split_search_id(all_fansubs, "id", fansub_id)
            fansub_name = await self.fsdb_conn.parse_fs_name(fs_data["name"])
            return fansub_name

        json_tables, emb_msg = await process_fsdb(json_tables, emb_msg)
        if not json_tables:
            self.logger.warning(f"{server_message}: {emb_msg}")
            return await ctx.send(emb_msg)

        self.logger.info(f"{server_message}: checkpoint before commiting")
        while True:
            fs_name = await find_fansub_name(json_tables["fs_id"])
            embed = discord.Embed(
                title="Integrasi FansubDB",
                description="Periksa data!\nReact jika ingin diubah.",
                color=0xE7E363,
            )
            embed.add_field(
                name="1⃣ ID Fansub", value="{} ({})".format(fs_name, json_tables["fs_id"]), inline=False,
            )
            embed.add_field(
                name="Lain-Lain", value="✅ Tambahkan!\n❌ Batalkan!", inline=False,
            )
            embed.set_footer(
                text="Dibawakan oleh naoTimes™®", icon_url="https://p.n4o.xyz/i/nao250px.png",
            )
            if first_time:
                await emb_msg.delete()
                emb_msg = await ctx.send(embed=embed)
                first_time = False
            else:
                await emb_msg.edit(embed=embed)

            to_react = [
                "1⃣",
                "✅",
                "❌",
            ]
            for reaction in to_react:
                await emb_msg.add_reaction(reaction)

            def check_react(reaction, user):
                if reaction.message.id != emb_msg.id:
                    return False
                if user != ctx.message.author:
                    return False
                if str(reaction.emoji) not in to_react:
                    return False
                return True

            res, user = await self.bot.wait_for("reaction_add", check=check_react)
            if user != ctx.message.author:
                pass
            elif to_react[0] in str(res.emoji):
                await emb_msg.clear_reactions()
                json_tables, emb_msg = await process_fsdb(json_tables, emb_msg)
            elif "✅" in str(res.emoji):
                await emb_msg.clear_reactions()
                break
            elif "❌" in str(res.emoji):
                self.logger.warning(f"{server_message}: process cancelled")
                cancel_toggled = True
                await emb_msg.clear_reactions()
                break

        if cancel_toggled:
            return await ctx.send("**Dibatalkan!**")

        self.logger.info(f"{server_message}: adding fsdb_id to anime data...")
        embed = discord.Embed(title="Integrasi FansubDB", color=0x56ACF3)
        embed.add_field(name="Memproses!", value="Memproses utang...", inline=True)
        embed.set_footer(
            text="Dibawakan oleh naoTimes™®", icon_url="https://p.n4o.xyz/i/nao250px.png",
        )
        await emb_msg.edit(embed=embed)
        collect_anime_dataset = []
        res, fsdb_animedb, total_data = await self.fsdb_conn.fetch_anime()
        if res:
            collect_anime_dataset.extend(fsdb_animedb)
            if total_data > 2000:
                leftover = total_data - 2000
                fetch_x_times = (leftover // 2000) + 1
                for i in range(fetch_x_times):
                    res2, fsdb_extradb, _ = await self.fsdb_conn.fetch_anime(start_n=i + 2)
                    if res2:
                        collect_anime_dataset.extend(fsdb_extradb)

        if collect_anime_dataset:
            collect_anime_dataset.sort(lambda x: x["mal_id"])
            for ani in srv_anilist:
                mal_id = srv_data["anime"][ani]["mal_id"]
                fs_id = await self.split_search_id(collect_anime_dataset, "mal_id", mal_id)
                if fs_id is None:
                    res = await self.fsdb_conn.tambah_anime(mal_id)
                srv_data["anime"][ani]["fsdb_id"] = fs_id

        embed = discord.Embed(title="Integrasi FansubDB", color=0x56ACF3)
        embed.add_field(name="Memproses!", value="Membuat data akhir...", inline=True)
        embed.set_footer(
            text="Dibawakan oleh naoTimes™®", icon_url="https://p.n4o.xyz/i/nao250px.png",
        )
        srv_data["fsdb_id"] = json_tables["fs_id"]

        self.logger.info(f"{server_message}: saving to local database...")
        await self.showqueue.add_job(ShowtimesQueueData(srv_data, server_message))
        embed = discord.Embed(title="Menambah Utang", color=0x96DF6A)
        embed.add_field(
            name="Sukses!", value="Server sukses terintegrasi dengan FansubDB", inline=True,
        )
        embed.set_footer(
            text="Dibawakan oleh naoTimes™®", icon_url="https://p.n4o.xyz/i/nao250px.png",
        )
        await ctx.send(embed=embed)

        self.logger.info(f"{server_message}: updating database...")
        success, msg = await self.ntdb.update_data_server(server_message, srv_data)
        await emb_msg.delete()

        if not success:
            self.logger.error(f"{server_message}: failed to update, reason: {msg}")
            if server_message not in self.bot.showtimes_resync:
                self.bot.showtimes_resync.append(server_message)

        self.logger.info(f"{server_message}: done processing!")
