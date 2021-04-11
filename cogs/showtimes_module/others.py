# -*- coding: utf-8 -*-

import asyncio
import logging
from copy import deepcopy
from functools import partial

import discord
from discord.ext import commands

from nthelper.bot import naoTimesBot
from nthelper.showtimes_helper import ShowtimesQueueData
from nthelper.utils import HelpGenerator, generate_custom_code

from .base import ShowtimesBase


class ShowtimesAlias(commands.Cog, ShowtimesBase):
    def __init__(self, bot: naoTimesBot):
        super(ShowtimesAlias, self).__init__()
        self.bot = bot
        self.ntdb = bot.ntdb
        self.cog_name = "Showtimes Alias"
        self.showqueue = bot.showqueue
        self.srv_fetch = partial(self.fetch_showtimes, redisdb=bot.redisdb)
        self.srv_dumps = partial(self.dumps_showtimes, redisdb=bot.redisdb)
        self.logger = logging.getLogger("cogs.showtimes_module.others.ShowtimesAlias")

    def __str__(self):
        return "Showtimes Alias"

    @commands.group(case_insensitive=True)
    @commands.guild_only()
    async def alias(self, ctx):
        """
        Initiate alias creation for certain anime
        """
        if self.ntdb is None:
            self.logger.info("owner hasn't enabled naoTimesDB yet.")
            return
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

            propagated_anilist = self.propagate_anime_with_aliases(srv_data["anime"])
            srv_anilist = []
            existing_aliases = []
            existing_aliases_dex = []
            for data in propagated_anilist:
                if data["type"] == "real":
                    srv_anilist.append(data)
                elif data["type"] == "alias":
                    existing_aliases.append(data["name"])
                    existing_aliases_dex.append(data)

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
            json_tables = {"alias_anime": "", "target_anime": -1}

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
                matches = self.find_any_matches(await_msg.content, anime_list)
                await await_msg.delete()
                if not matches:
                    await ctx.send("Tidak dapat menemukan judul tersebut di database")
                    return False, False
                if len(matches) > 1:
                    matches = await self.choose_anime(bot=self.bot, ctx=ctx, matches=matches)
                    if not matches:
                        return await ctx.send("**Dibatalkan!**")

                matched = matches[0]
                ani_title = matched["name"]

                embed = discord.Embed(title="Alias", color=0x96DF6A)
                embed.add_field(
                    name="Apakah benar?", value="Judul: **{}**".format(ani_title), inline=False,
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
                    table["target_anime"] = matched["index"]
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
                if json_tables["target_anime"] < 0:
                    anime_name = "*[Unknown]*"
                else:
                    anime_name = srv_data["anime"][json_tables["target_anime"]]["title"]
                embed = discord.Embed(
                    title="Alias", description="Periksa data!\nReact jika ingin diubah.", color=0xE7E363,
                )
                embed.add_field(
                    name="1⃣ Anime/Garapan", value=anime_name, inline=False,
                )
                embed.add_field(
                    name="2⃣ Alias", value=json_tables["alias_anime"], inline=False,
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

            if json_tables["alias_anime"] in existing_aliases:
                aindex = existing_aliases.index(json_tables["alias_anime"])
                anime_match = existing_aliases_dex[aindex]
                embed = discord.Embed(title="Alias", color=0xE24545)
                embed.add_field(
                    name="Dibatalkan!",
                    value="Alias **{}** sudah terdaftar untuk **{}**".format(
                        json_tables["alias_anime"], anime_match["real_name"],
                    ),
                    inline=True,
                )
                embed.set_footer(
                    text="Dibawakan oleh naoTimes™®", icon_url="https://p.n4o.xyz/i/nao250px.png",
                )
                await emb_msg.delete()
                return await ctx.send(embed=embed)

            program_info = srv_data["anime"][json_tables["target_anime"]]
            if "aliases" not in program_info:
                program_info["aliases"] = []
            program_info["aliases"].append(json_tables["alias_anime"])

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
                    json_tables["alias_anime"], program_info["title"]
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
                    json_tables["alias_anime"], program_info["title"]
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

        propagated_anilist = self.propagate_anime_with_aliases(srv_data["anime"])
        srv_anilist = []
        existing_aliases = []
        for data in propagated_anilist:
            if data["type"] == "real":
                srv_anilist.append(data)
            elif data["type"] == "alias":
                existing_aliases.append(data)

        if not existing_aliases:
            return await ctx.send("Tidak ada alias yang terdaftar.")

        if not judul:
            return await self.send_all_projects(ctx, srv_data["anime"], server_message)

        self.logger.info(f"{server_message}: getting close matches...")
        matches = self.find_any_matches(judul, srv_anilist)
        if not matches:
            self.logger.warning(f"{server_message}: no matches.")
            return await ctx.send("Tidak dapat menemukan judul tersebut di database")
        if len(matches) > 1:
            self.logger.info(f"{server_message}: multiple matches!")
            matches = await self.choose_anime(bot=self.bot, ctx=ctx, matches=matches)
            if not matches:
                return await ctx.send("**Dibatalkan!**")

        matched_anime = matches[0]
        indx = matched_anime["index"]

        self.logger.info(f"{server_message}: matched {matched_anime}")
        srv_anilist_alias = []
        for aliases in existing_aliases:
            if aliases["index"] == indx:
                srv_anilist_alias.append(aliases["name"])

        text_value = ""
        if not srv_anilist_alias:
            text_value += "Tidak ada"

        if not text_value:
            text_value += self.make_numbered_alias(srv_anilist_alias)

        self.logger.info(f"{server_message}: sending alias!")
        embed = discord.Embed(title="Alias list", color=0x47E0A7)
        embed.add_field(name=matched_anime["name"], value=text_value, inline=False)
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

        propagated_anilist = self.propagate_anime_with_aliases(srv_data["anime"])
        srv_anilist = []
        existing_aliases = []
        for data in propagated_anilist:
            if data["type"] == "real":
                srv_anilist.append(data)
            elif data["type"] == "alias":
                existing_aliases.append(data)

        if not judul:
            return await self.send_all_projects(ctx, srv_anilist, server_message)

        matches = self.find_any_matches(judul, srv_anilist)
        if not matches:
            self.logger.warning(f"{server_message}: no matches.")
            return await ctx.send("Tidak dapat menemukan judul tersebut di database")
        if len(matches) > 1:
            self.logger.info(f"{server_message}: multiple matches!")
            matches = await self.choose_anime(bot=self.bot, ctx=ctx, matches=matches)
            if not matches:
                return await ctx.send("**Dibatalkan!**")

        matched_anime = matches[0]
        indx = matched_anime["index"]

        self.logger.info(f"{server_message}: matched {matched_anime}")
        srv_anilist_alias = []
        for aliases in existing_aliases:
            if aliases["index"] == indx:
                srv_anilist_alias.append(aliases)

        if not srv_anilist_alias:
            self.logger.info(f"{matched_anime['name']}: no registered alias.")
            return await ctx.send(
                "Tidak ada alias yang terdaftar untuk judul **{}**".format(matched_anime["name"])
            )

        alias_chunked = [srv_anilist_alias[i : i + 5] for i in range(0, len(srv_anilist_alias), 5)]

        def _create_naming_scheme(chunked_thing):
            name_only = []
            for chunk in chunked_thing:
                name_only.append(chunk["name"])
            return self.make_numbered_alias(name_only)

        first_run = True
        n = 1
        max_n = len(alias_chunked)
        while True:
            if first_run:
                self.logger.info(f"{server_message}: sending results...")
                chunked = alias_chunked[n - 1]
                first_run = False
                embed = discord.Embed(title="Alias list", color=0x47E0A7)
                embed.add_field(
                    name=matched_anime["name"], value=_create_naming_scheme(chunked), inline=False,
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
                n -= 1
                await emb_msg.clear_reactions()
                embed = discord.Embed(title="Alias list", color=0x47E0A7)
                embed.add_field(
                    name=matched_anime["name"],
                    value=_create_naming_scheme(alias_chunked[n - 1]),
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
                n += 1
                await emb_msg.clear_reactions()
                embed = discord.Embed(title="Alias list", color=0x47E0A7)
                embed.add_field(
                    name=matched_anime["name"],
                    value=_create_naming_scheme(alias_chunked[n - 1]),
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
                to_be_deleted = alias_chunked[n - 1][index_del]
                try:
                    srv_data["anime"][indx]["aliases"].remove(to_be_deleted["name"])
                except (ValueError, IndexError, KeyError):
                    pass

                await self.showqueue.add_job(ShowtimesQueueData(srv_data, server_message))
                await ctx.send(
                    "Alias **{} ({})** telah dihapus dari database".format(
                        to_be_deleted["name"], matched_anime["name"]
                    )
                )

                self.logger.info(f"{server_message}: updating database...")
                success, msg = await self.ntdb.update_data_server(server_message, srv_data)

                if not success:
                    self.logger.error(f"{server_message}: failed to update, reason: {msg}")
                    if server_message not in self.bot.showtimes_resync:
                        self.bot.showtimes_resync.append(server_message)
                break


class ShowtimesKolaborasi(commands.Cog, ShowtimesBase):
    def __init__(self, bot: naoTimesBot):
        super(ShowtimesKolaborasi, self).__init__()
        self.bot = bot
        self.ntdb = bot.ntdb
        self.cog_name = "Showtimes Kolaborasi"
        self.showqueue = bot.showqueue
        self.srv_fetch = partial(self.fetch_showtimes, redisdb=bot.redisdb)
        self.srv_dumps = partial(self.dumps_showtimes, redisdb=bot.redisdb)
        self.srv_lists = partial(self.fetch_servers, redisdb=bot.redisdb)
        self.logger = logging.getLogger("cogs.showtimes_module.others.ShowtimesKolaborasi")

    def __str__(self):
        return "Showtimes Kolaborasi"

    @commands.group(aliases=["joint", "join", "koleb"], case_insensitive=True)
    @commands.guild_only()
    async def kolaborasi(self, ctx):
        if self.ntdb is None:
            self.logger.info("owner hasn't enabled naoTimesDB yet.")
            return
        if not ctx.invoked_subcommand:
            helpcmd = HelpGenerator(self.bot, ctx, "kolaborasi", f"Versi {self.bot.semver}")
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

        propagated_anilist = self.propagate_anime_with_aliases(srv_data["anime"])
        if not judul:
            return await self.send_all_projects(ctx, srv_data["anime"], server_message)

        self.logger.info(f"{server_message}: getting close matches...")
        matches = self.find_any_matches(judul, propagated_anilist)
        if not matches:
            self.logger.warning(f"{server_message}: no matches.")
            return await ctx.send("Tidak dapat menemukan judul tersebut di database")
        if len(matches) > 1:
            self.logger.info(f"{server_message}: multiple matches!")
            matches = await self.choose_anime(bot=self.bot, ctx=ctx, matches=matches)
            if not matches:
                return await ctx.send("**Dibatalkan!**")

        matched_anime = matches[0]
        indx = matched_anime["index"]
        ani_title = matched_anime["name"] if matched_anime["type"] == "real" else matched_anime["real_name"]

        self.logger.info(f"{server_message}: matched {matched_anime}")
        program_info = srv_data["anime"][indx]

        if "kolaborasi" in program_info and server_id in program_info["kolaborasi"]:
            self.logger.info(f"{ani_title}: already on collab.")
            return await ctx.send("Server tersebut sudah diajak kolaborasi.")

        randomize_confirm = generate_custom_code(16)  # nosec

        cancel_toggled = False
        first_time = True
        while True:
            try:
                server_identd = self.bot.get_guild(int(server_id))
                server_ident = server_identd.name
            except (AttributeError, ValueError, TypeError):
                server_ident = server_id
            embed = discord.Embed(
                title="Kolaborasi", description="Periksa data!\nReact jika ingin diubah.", color=0xE7E363,
            )
            embed.add_field(name="Anime/Garapan", value=ani_title, inline=False)
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
                self.logger.warning(f"{ani_title}: cancelling...")
                cancel_toggled = True
                await emb_msg.clear_reactions()
                await emb_msg.delete()
                break

        if cancel_toggled:
            return await ctx.send("**Dibatalkan!**")

        table_data = {}
        table_data["id"] = randomize_confirm
        table_data["anime_id"] = matched_anime["id"]
        table_data["server_id"] = server_message

        if "konfirmasi" not in target_server:
            target_server["konfirmasi"] = []
        target_server["konfirmasi"].append(table_data)

        embed = discord.Embed(title="Kolaborasi", color=0x56ACF3)
        embed.add_field(name="Memproses!", value="Mengirim data...", inline=True)
        embed.set_footer(
            text="Dibawakan oleh naoTimes™®", icon_url="https://p.n4o.xyz/i/nao250px.png",
        )
        await emb_msg.edit(embed=embed)

        self.logger.info(f"{server_message}-{server_id}: storing data...")
        await self.showqueue.add_job(ShowtimesQueueData(target_server, server_id))
        embed = discord.Embed(title="Kolaborasi", color=0x96DF6A)
        embed.add_field(
            name="Sukses!",
            value=f"Berikan kode berikut `{randomize_confirm}` kepada fansub/server lain.\n"
            "Database utama akan diupdate sebentar lagi",
            inline=True,
        )
        embed.set_footer(
            text="Dibawakan oleh naoTimes™®", icon_url="https://p.n4o.xyz/i/nao250px.png",
        )
        await emb_msg.delete()
        await ctx.send(embed=embed)

        self.logger.info(f"{server_id}: updating database...")
        success, msg = await self.ntdb.kolaborasi_dengan(server_id, table_data)

        if not success:
            self.logger.error(f"{server_id}: failed to update, reason: {msg}")
            if server_message not in self.bot.showtimes_resync:
                self.bot.showtimes_resync.append(server_message)

        await ctx.send(
            f"Berikan kode berikut `{randomize_confirm}` kepada fansub/server yang ditentukan tadi.\n"
            f"Konfirmasi di server tersebut dengan `{self.bot.prefix}kolaborasi "
            f"konfirmasi {randomize_confirm}`"
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
        klb_data_dex = self._search_data_index(srv_data["konfirmasi"], "id", konfirm_id)
        if klb_data_dex is None:
            self.logger.warning(f"{konfirm_id}: can't find that confirm id.")
            return await ctx.send("Tidak dapat menemukan kode kolaborasi yang diberikan.")
        klb_data = srv_data["konfirmasi"][klb_data_dex]

        try:
            server_identd = self.bot.get_guild(int(klb_data["server_id"]))
            server_ident = server_identd.name
        except (AttributeError, ValueError, TypeError):
            server_ident = klb_data["server_id"]

        source_srv = await self.showqueue.fetch_database(klb_data["server_id"])
        ani_idx = self._search_data_index(source_srv["anime"], "id", klb_data["anime_id"])
        if ani_idx is None:
            return await ctx.send("Tidak dapat menemukan anime yang akan diajak kolaborasi.")
        selected_anime = source_srv["anime"][ani_idx]

        embed = discord.Embed(title="Konfirmasi Kolaborasi", color=0xE7E363)
        embed.add_field(name="Anime/Garapan", value=selected_anime["title"], inline=False)
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

        find_target_id = self._search_data_index(srv_data["anime"], "id", selected_anime["id"])

        ani_srv_role = ""
        old_koleb_data = []
        if find_target_id is not None:
            self.logger.warning(f"{server_message}: existing data, changing with source server")
            ani_srv_role += srv_data["anime"][find_target_id]["role_id"]
            if "kolaborasi" in srv_data["anime"][find_target_id]:
                old_koleb_data.extend(srv_data["anime"][find_target_id]["kolaborasi"])
            srv_data["anime"].pop(find_target_id)

        if not ani_srv_role:
            self.logger.info(f"{server_message}: creating roles...")
            c_role = await ctx.message.guild.create_role(
                name=selected_anime["title"], colour=discord.Colour.random(), mentionable=True,
            )
            ani_srv_role = str(c_role.id)

        copied_data = deepcopy(selected_anime)
        copied_data["role_id"] = ani_srv_role

        join_srv = [klb_data["server_id"], server_message]
        if old_koleb_data:
            join_srv.extend(old_koleb_data)
        join_srv = list(dict.fromkeys(join_srv))
        if "kolaborasi" in selected_anime:
            join_srv.extend(selected_anime["kolaborasi"])
        join_srv = list(dict.fromkeys(join_srv))
        source_srv["anime"][ani_idx]["kolaborasi"] = join_srv
        copied_data["kolaborasi"] = join_srv
        srv_data["anime"].append(copied_data)

        update_osrv_data = {}
        for osrv in join_srv:
            if osrv in (klb_data["server_id"], server_message):
                continue
            osrv_data = await self.showqueue.fetch_database(osrv)
            osrv_id_anime = self._search_data_index(osrv_data["anime"], "id", copied_data["id"])
            if osrv_id_anime is None:
                continue
            osrv_data["anime"][osrv_id_anime]["kolaborasi"] = join_srv
            await self.showqueue.add_job(ShowtimesQueueData(osrv_data, osrv))
            update_osrv_data[osrv] = osrv_data

        try:
            srv_data["konfirmasi"].remove(klb_data)
        except ValueError:
            try:
                srv_data["konfirmasi"].pop(klb_data_dex)
            except IndexError:
                pass

        embed = discord.Embed(title="Kolaborasi", color=0x56ACF3)
        embed.add_field(name="Memproses!", value="Mengirim data...", inline=True)
        embed.set_footer(
            text="Dibawakan oleh naoTimes™®", icon_url="https://p.n4o.xyz/i/nao250px.png",
        )
        await emb_msg.edit(embed=embed)

        self.logger.info(f"{server_message}-{klb_data['server_id']}: storing data...")
        await self.showqueue.add_job(ShowtimesQueueData(source_srv, klb_data["server_id"]))
        await self.showqueue.add_job(ShowtimesQueueData(srv_data, server_message))
        embed = discord.Embed(title="Kolaborasi", color=0x96DF6A)
        embed.add_field(
            name="Sukses!",
            value="Berhasil konfirmasi dengan server **{}**.\nDatabase utama akan diupdate sebentar lagi".format(  # noqa: E501
                klb_data["server_id"]
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
            klb_data["server_id"], server_message, source_srv, srv_data,
        )

        if not success:
            self.logger.error(f"{server_message}: failed to update, reason: {msg}")
            if server_message not in self.bot.showtimes_resync:
                self.bot.showtimes_resync.append(server_message)

        for osrv, osrv_data in update_osrv_data.items():
            if osrv in (klb_data["server_id"], server_message):
                continue
            self.logger.info(f"{osrv}: updating database...")
            res2, msg2 = await self.ntdb.update_data_server(osrv, osrv_data)
            if not res2:
                if osrv not in self.bot.showtimes_resync:
                    self.bot.showtimes_resync.append(osrv)
                self.logger.error(f"{osrv}: failed to update, reason: {msg2}")

        await ctx.send(
            f"Berhasil menambahkan kolaborasi dengan **{klb_data['server_id']}** ke dalam database utama"
            f" naoTimes\nBerikan role berikut agar bisa menggunakan perintah staff <@&{ani_srv_role}>"
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
        klb_data_dex = self._search_data_index(other_srv_data["konfirmasi"], "id", konfirm_id)
        if klb_data_dex is None:
            self.logger.warning(f"{konfirm_id}: can't find that confirm id.")
            return await ctx.send("Tidak dapat menemukan kode kolaborasi yang diberikan.")
        klb_data = other_srv_data["konfirmasi"][klb_data_dex]
        if klb_data["server_id"] != server_message:
            return await ctx.send("Anda tidak berhak untuk menghapus kode ini!")
        try:
            other_srv_data["konfirmasi"].remove(klb_data)
        except ValueError:
            try:
                other_srv_data["konfirmasi"].pop(klb_data_dex)
            except IndexError:
                return await ctx.send("Gagal menghapus kode konfirmasi!")

        self.logger.info(f"{server_message}-{server_id}: storing data...")
        await self.showqueue.add_job(ShowtimesQueueData(other_srv_data, server_id))
        embed = discord.Embed(title="Kolaborasi", color=0x96DF6A)
        embed.add_field(
            name="Sukses!",
            value=f"Berhasil membatalkan kode konfirmasi **{konfirm_id}**.\n"
            "Database utama akan diupdate sebentar lagi",
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

        await ctx.send(f"Berhasil membatalkan kode konfirmasi **{konfirm_id}** dari database utama naoTimes")

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

        propagated_anilist = self.propagate_anime_with_aliases(srv_data["anime"])
        if not judul:
            return await self.send_all_projects(ctx, srv_data["anime"], server_message)

        self.logger.info(f"{server_message}: getting close matches...")
        matches = self.find_any_matches(judul, propagated_anilist)
        if not matches:
            self.logger.warning(f"{server_message}: no matches.")
            return await ctx.send("Tidak dapat menemukan judul tersebut di database")
        if len(matches) > 1:
            self.logger.info(f"{server_message}: multiple matches!")
            matches = await self.choose_anime(bot=self.bot, ctx=ctx, matches=matches)
            if not matches:
                return await ctx.send("**Dibatalkan!**")

        matched_anime = matches[0]
        indx = matched_anime["index"]
        ani_title = matched_anime["name"] if matched_anime["type"] == "real" else matched_anime["real_name"]

        self.logger.info(f"{server_message}: matched {matched_anime}")
        program_info = srv_data["anime"][indx]

        if "kolaborasi" not in program_info:
            self.logger.warning(f"{server_message}-{ani_title}: no registered collaboration on this title.")
            return await ctx.send("Tidak ada kolaborasi sama sekali pada judul ini.")

        self.logger.warning(f"{ani_title}: start removing server from other server...")
        for osrv in program_info["kolaborasi"]:
            if osrv == server_message:
                continue
            osrv_data = await self.showqueue.fetch_database(osrv)
            indx_other = self._search_data_index(osrv_data["anime"], "id", program_info["id"])
            if indx_other is None:
                continue
            osrv_anime = osrv_data["anime"][indx_other]
            if "kolaborasi" in osrv_anime and osrv_anime["kolaborasi"]:
                try:
                    osrv_data["anime"][indx_other]["kolaborasi"].remove(server_message)
                except ValueError:
                    pass

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
            del srv_data["anime"][indx]["fsdb_data"]

        self.logger.info(f"{server_message}: storing data...")
        srv_data["anime"][indx]["kolaborasi"] = []
        await self.showqueue.add_job(ShowtimesQueueData(srv_data, server_message))
        embed = discord.Embed(title="Kolaborasi", color=0x96DF6A)
        embed.add_field(
            name="Sukses!",
            value=f"Berhasil memputuskan kolaborasi **{ani_title}**.\n"
            "Database utama akan diupdate sebentar lagi",
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

        await ctx.send(f"Berhasil memputuskan kolaborasi **{ani_title}** dari database utama naoTimes")
        if fsdb_binded:
            await ctx.send(
                "Binding FansubDB untuk anime terputus, "
                f"silakan hubungkan ulang dengan: `{self.bot.prefixes(ctx)}fsdb bind {ani_title}`"
            )
