# -*- coding: utf-8 -*-

import asyncio
import logging
from copy import deepcopy
from functools import partial
from random import choice
from string import ascii_lowercase, digits

import discord
from discord.ext import commands
from nthelper.bot import naoTimesBot
from nthelper.showtimes_helper import ShowtimesQueueData
from nthelper.utils import HelpGenerator

from .base import ShowtimesBase


class ShowtimesAlias(commands.Cog, ShowtimesBase):
    def __init__(self, bot: naoTimesBot):
        super(ShowtimesAlias, self).__init__()
        self.bot = bot
        self.ntdb = bot.ntdb
        self.cog_name = "Showtimes Alias"
        self.showqueue = bot.showqueue
        self.srv_fetch = partial(self.fetch_showtimes, cwd=bot.fcwd)
        self.srv_dumps = partial(self.dumps_showtimes, cwd=bot.fcwd)
        self.logger = logging.getLogger("cogs.showtimes_module.others.ShowtimesAlias")

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
    def __init__(self, bot: naoTimesBot):
        super(ShowtimesKolaborasi, self).__init__()
        self.bot = bot
        self.ntdb = bot.ntdb
        self.cog_name = "Showtimes Kolaborasi"
        self.showqueue = bot.showqueue
        self.srv_fetch = partial(self.fetch_showtimes, cwd=bot.fcwd)
        self.srv_dumps = partial(self.dumps_showtimes, cwd=bot.fcwd)
        self.srv_lists = partial(self.fetch_servers, cwd=bot.fcwd)
        self.logger = logging.getLogger("cogs.showtimes_module.others.ShowtimesKolaborasi")

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

        randomize_confirm = "".join(choice(ascii_lowercase + digits) for i in range(16))  # nosec

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

        update_osrv_data = {}
        for osrv in join_srv:
            if osrv in (srv_source, server_message):
                continue
            osrv_data = await self.showqueue.fetch_database(osrv)
            osrv_data["anime"][klb_data["anime"]]["kolaborasi"] = join_srv
            await self.showqueue.add_job(ShowtimesQueueData(osrv_data, osrv))
            update_osrv_data[osrv] = osrv_data

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

        for osrv, osrv_data in update_osrv_data.items():
            if osrv in (srv_source, server_message):
                continue
            self.logger.info(f"{osrv}: updating database...")
            res2, msg2 = await self.ntdb.update_data_server(osrv, osrv_data)
            if not res2:
                if osrv not in self.bot.showtimes_resync:
                    self.bot.showtimes_resync.append(osrv)
                self.logger.error(f"{osrv}: failed to update, reason: {msg2}")

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

        fsdb_binded = False
        if "fsdb_data" in program_info:
            fsdb_binded = True
            del srv_data["anime"][matches[0]]["fsdb_data"]

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
        success, msg = await self.ntdb.update_data_server(server_message, srv_data)

        if not success:
            self.logger.error(f"{server_message}: failed to update, reason: {msg}")
            if server_message not in self.bot.showtimes_resync:
                self.bot.showtimes_resync.append(server_message)

        await ctx.send(
            "Berhasil memputuskan kolaborasi **{}** dari database utama naoTimes".format(  # noqa: E501
                matches[0]
            )
        )
        if fsdb_binded:
            await ctx.send(
                "Binding FansubDB untuk anime terputus, "
                f"silakan hubungkan ulang dengan: `{self.bot.prefix}fsdb bind {matches[0]}`"
            )
