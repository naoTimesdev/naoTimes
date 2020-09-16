# -*- coding: utf-8 -*-

import asyncio
import logging
import os
import time
from functools import partial

import aiohttp
import discord
from discord.ext import commands

import ujson
from nthelper import HelpGenerator, write_files
from nthelper.showtimes_helper import ShowtimesQueue, ShowtimesQueueData, naoTimesDB

from .base import ShowtimesBase


class ShowtimesOwner(commands.Cog, ShowtimesBase):
    def __init__(self, bot):
        super(ShowtimesOwner, self).__init__()
        self.bot = bot
        self.ntdb: naoTimesDB = bot.ntdb
        self.bot_config = bot.botconf
        self.showqueue: ShowtimesQueue = bot.showqueue
        self.srv_lists = partial(self.fetch_servers, cwd=bot.fcwd)
        self.logger = logging.getLogger("cogs.showtimes_module.owner.ShowtimesOwner")

    def __str__(self):
        return "Showtimes Owner"

    @commands.group(aliases=["naotimesadmin", "naoadmin"])
    @commands.is_owner()
    @commands.guild_only()
    async def ntadmin(self, ctx):
        if ctx.invoked_subcommand is None:
            helpcmd = HelpGenerator(self.bot, "ntadmin", desc=f"Versi {self.bot.semver}",)
            await helpcmd.generate_field(
                "ntadmin", desc="Memunculkan bantuan perintah ini.",
            )
            await helpcmd.generate_field(
                "ntadmin initiate", desc="Menginisiasi showtimes.",
            )
            await helpcmd.generate_field(
                "ntadmin tambah",
                desc="Menambah server baru ke database naoTimes.",
                opts=[
                    {"name": "server id", "type": "r"},
                    {"name": "admin id", "type": "r"},
                    {"name": "#progress channel", "type": "o"},
                ],
            )
            await helpcmd.generate_field(
                "ntadmin hapus",
                desc="Menghapus server dari database naoTimes.",
                opts=[{"name": "server id", "type": "r"}],
            )
            await helpcmd.generate_field(
                "ntadmin tambahadmin",
                desc="Menambah admin ke server baru " "yang terdaftar di database.",
                opts=[{"name": "server id", "type": "r"}, {"name": "admin id", "type": "r"}],
            )
            await helpcmd.generate_field(
                "ntadmin hapusadmin",
                desc="Menghapus admin dari server baru yang" " terdaftar di database.",
                opts=[{"name": "server id", "type": "r"}, {"name": "admin id", "type": "r"}],
            )
            await helpcmd.generate_field(
                "ntadmin fetchdb", desc="Mengambil database lokal dan kirim ke Discord.",
            )
            await helpcmd.generate_field(
                "ntadmin patchdb", desc="Update database dengan file yang dikirim user.",
            )
            await helpcmd.generate_field(
                "ntadmin forcepull", desc="Update paksa database lokal dengan database utama.",
            )
            await helpcmd.generate_field(
                "ntadmin forceupdate", desc="Update paksa database utama dengan database lokal.",
            )
            await helpcmd.generate_aliases(["naotimesadmin", "naoadmin"])
            await ctx.send(embed=helpcmd.get())

    @ntadmin.command()
    async def listserver(self, ctx):
        print("[#] Requested !ntadmin listserver by admin")
        srv_dumps = await self.srv_lists()
        if not srv_dumps:
            return

        srv_list = []
        for srv in srv_dumps:
            if srv == "supermod":
                continue
            srv_ = self.bot.get_guild(int(srv))
            if not srv_:
                print(f"[$] Unknown server: {srv}")
                continue
            srv_list.append(f"{srv_.name} ({srv})")

        text = "**List server ({} servers):**\n".format(len(srv_list))
        for x in srv_list:
            text += x + "\n"

        text = text.rstrip("\n")

        await ctx.send(text)

    @ntadmin.command()
    async def listresync(self, ctx):
        resynclist = self.bot.showtimes_resync
        if not resynclist:
            return await ctx.send("**Server that still need to be resynced**: None")
        resynclist = ["- {}\n".format(x) for x in resynclist]
        main_text = "**Server that still need to be resynced**:\n"
        main_text += "".join(resynclist)
        main_text = main_text.rstrip("\n")
        await ctx.send(main_text)

    @ntadmin.command()
    async def migratedb(self, ctx):
        await ctx.send("Mulai migrasi database!")
        url = "https://gist.githubusercontent.com/{u}/{g}/raw/nao_showtimes.json"
        async with aiohttp.ClientSession() as session:
            while True:
                headers = {"User-Agent": "naoTimes v2.0"}
                print("\t[#] Fetching nao_showtimes.json")
                async with session.get(
                    url.format(u=self.bot_config["github_info"]["username"], g=self.bot_config["gist_id"],),
                    headers=headers,
                ) as r:
                    try:
                        r_data = await r.text()
                        js_data = ujson.loads(r_data)
                        print("\t[@] Fetched and saved.")
                        break
                    except IndexError:
                        pass
        await ctx.send("Berhasil mendapatkan database dari github, " "mulai migrasi ke MongoDB")
        await self.ntdb.patch_all_from_json(js_data)
        await ctx.send("Selesai migrasi database, silakan di coba cuk.")

    @ntadmin.command()
    async def initiate(self, ctx):
        """
        Initiate naoTimes on this server so it can be used on other server
        Make sure everything is filled first before starting this command
        """
        print("[@] Initiated naoTimes first-time setup")
        if self.bot_config["gist_id"] != "":
            print("[@] Already setup, skipping")
            return await ctx.send("naoTimes sudah dipersiapkan dan sudah bisa digunakan")

        print("Membuat data")
        embed = discord.Embed(title="naoTimes", color=0x56ACF3)
        embed.add_field(name="Memulai Proses!", value="Mempersiapkan...", inline=False)
        embed.set_footer(
            text="Dibawakan oleh naoTimes™®", icon_url="https://p.n4o.xyz/i/nao250px.png",
        )
        emb_msg = await ctx.send(embed=embed)
        msg_author = ctx.message.author
        json_tables = {
            "id": "",
            "owner_id": str(msg_author.id),
            "progress_channel": "",
        }

        def check_if_author(m):
            return m.author == ctx.message.author

        async def process_gist(table, emb_msg, author):
            print("[@] Memproses database")
            embed = discord.Embed(title="naoTimes", color=0x96DF6A)
            embed.add_field(name="Gist ID", value="Ketik ID Gist GitHub", inline=False)
            embed.set_footer(
                text="Dibawakan oleh naoTimes™®", icon_url="https://p.n4o.xyz/i/nao250px.png",
            )
            await emb_msg.edit(embed=embed)

            await_msg = await self.bot.wait_for("message", check=check_if_author)
            table["id"] = str(await_msg.content)

            return table, emb_msg

        async def process_progchan(table, emb_msg, author):
            print("[@] Memproses #progress channel")
            embed = discord.Embed(title="naoTimes", color=0x96DF6A)
            embed.add_field(
                name="#progress channel ID", value="Ketik ID channel", inline=False,
            )
            embed.set_footer(
                text="Dibawakan oleh naoTimes™®", icon_url="https://p.n4o.xyz/i/nao250px.png",
            )
            await emb_msg.edit(embed=embed)

            while True:
                await_msg = await self.bot.wait_for("message", check=check_if_author)
                if await_msg.content.isdigit():
                    table["progress_channel"] = str(await_msg.content)
                    await await_msg.delete()
                    break
                await await_msg.delete()

            return table, emb_msg

        async def process_owner(table, emb_msg, author):
            print("[@] Memproses ID Owner")
            embed = discord.Embed(title="naoTimes", color=0x96DF6A)
            embed.add_field(
                name="Owner ID", value="Ketik ID Owner server atau mention orangnya", inline=False,
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
                        table["owner_id"] = str(await_msg.content)
                        await await_msg.delete()
                        break
                else:
                    table["owner_id"] = str(mentions[0].id)
                    await await_msg.delete()
                    break
                await await_msg.delete()

            return table, emb_msg

        json_tables, emb_msg = await process_gist(json_tables, emb_msg, msg_author)
        json_tables, emb_msg = await process_progchan(json_tables, emb_msg, msg_author)

        print("[@] Making sure.")
        first_time = True
        cancel_toggled = False
        while True:
            embed = discord.Embed(
                title="naoTimes", description="Periksa data!\nReact jika ingin diubah.", color=0xE7E363,
            )
            embed.add_field(
                name="1⃣ Gists ID", value="{}".format(json_tables["id"]), inline=False,
            )
            embed.add_field(
                name="2⃣ Owner ID", value="{}".format(json_tables["owner_id"]), inline=False,
            )
            embed.add_field(
                name="3⃣ #progress channel ID",
                value="{}".format(json_tables["progress_channel"]),
                inline=False,
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

            to_react = ["1⃣", "2⃣", "3⃣", "✅", "❌"]
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
            elif to_react[0] in str(res.emoji):
                await emb_msg.clear_reactions()
                json_tables, emb_msg = await process_gist(json_tables, emb_msg, msg_author)
            elif to_react[1] in str(res.emoji):
                await emb_msg.clear_reactions()
                json_tables, emb_msg = await process_owner(json_tables, emb_msg, msg_author)
            elif to_react[2] in str(res.emoji):
                await emb_msg.clear_reactions()
                json_tables, emb_msg = await process_progchan(json_tables, emb_msg, msg_author)
            elif "✅" in str(res.emoji):
                await emb_msg.clear_reactions()
                break
            elif "❌" in str(res.emoji):
                print("[@] Cancelled")
                cancel_toggled = True
                await emb_msg.clear_reactions()
                break

        if cancel_toggled:
            return await ctx.send("**Dibatalkan!**")

        embed = discord.Embed(title="naoTimes", color=0x56ACF3)
        embed.add_field(name="Memproses!", value="Mengirim data...", inline=True)
        embed.set_footer(
            text="Dibawakan oleh naoTimes™®", icon_url="https://p.n4o.xyz/i/nao250px.png",
        )
        await emb_msg.edit(embed=embed)

        main_data = {}
        server_data = {}
        main_data["supermod"] = [json_tables["owner_id"]]

        server_data["serverowner"] = [json_tables["owner_id"]]
        server_data["announce_channel"] = json_tables["progress_channel"]
        server_data["anime"] = {}
        server_data["alias"] = {}

        main_data[str(ctx.message.guild.id)] = server_data
        print("[@] Sending data")
        for srv_patch, srv_data_patch in main_data.items():
            if srv_patch == "supermod":
                await self.dumps_super_admins(srv_data_patch, self.bot.fcwd)
            else:
                await self.showqueue.add_job(ShowtimesQueueData(srv_data_patch, srv_patch))
        _ = await self.ntdb.patch_all_from_json(main_data)

        print("[@] Reconfiguring config files")
        self.bot_config["gist_id"] = json_tables["gist_id"]
        await write_files(self.bot_config, "config.json")
        print("[@] Reconfigured. Every configuration are done, please restart.")
        embed = discord.Embed(title="naoTimes", color=0x56ACF3)
        embed.add_field(
            name="Sukses!",
            value="Sukses membuat database di github\n"
            "Silakan restart bot agar naoTimes dapat diaktifkan.\n\n"
            "Laporkan isu di: "
            "[GitHub Issue](https://github.com/noaione/naoTimes/issues)",
            inline=True,
        )
        embed.set_footer(
            text="Dibawakan oleh naoTimes™®", icon_url="https://p.n4o.xyz/i/nao250px.png",
        )
        await ctx.send(embed=embed)
        await emb_msg.delete()

    @ntadmin.command()
    async def fetchdb(self, ctx):
        print("[#] Requested !ntadmin fetchdb by admin")
        srv_lists = await self.srv_lists()
        if not srv_lists:
            return

        async def _internal_fetch(srv_id):
            data_res = await self.showqueue.fetch_database(srv_id)
            return data_res, srv_id

        channel = ctx.message.channel
        fetch_jobs = [_internal_fetch(srv) for srv in srv_lists]

        final_dataset = {}
        for fjob in asyncio.as_completed(fetch_jobs):
            data_res, srv_id = await fjob
            if data_res is not None:
                final_dataset[srv_id] = data_res

        super_admin = await self.fetch_super_admins(self.bot.fcwd)
        final_dataset["supermod"] = super_admin

        print("Saving .json")
        save_file_name = str(int(round(time.time()))) + "_naoTimes_database.json"
        await write_files(final_dataset, save_file_name)

        print("Sending .json")
        await channel.send(content="Here you go!", file=discord.File(save_file_name))
        os.remove(save_file_name)  # Cleanup

    @ntadmin.command()
    async def forcepull(self, ctx):
        print("[#] Requested !ntadmin forcepull by owner")
        channel = ctx.message.channel

        json_d = await self.ntdb.fetch_all_as_json()
        for srv, srv_data in json_d.items():
            if srv == "supermod":
                await self.dumps_super_admins(srv_data, self.bot.fcwd)
            else:
                await self.showqueue.add_job(ShowtimesQueueData(srv_data, srv))
        await channel.send("Newest database has been pulled and saved to local save")

    @ntadmin.command()
    @commands.guild_only()
    async def patchdb(self, ctx):
        """
        !! Warning !!
        This will patch entire database
        """
        print("[#] Requested !ntadmin patchdb by admin")

        if ctx.message.attachments == []:
            await ctx.message.delete()
            return await ctx.send(
                "Please provide a valid .json file by uploading " "and add `!!ntadmin patchdb` command"
            )

        print("[@] Fetching attachments")

        attachment = ctx.message.attachments[0]
        uri = attachment.url
        filename = attachment.filename

        if filename[filename.rfind(".") :] != ".json":
            await ctx.message.delete()
            return await ctx.send(
                "Please provide a valid .json file by uploading " "and add `!!ntadmin patchdb` command"
            )

        # Start downloading .json file
        print("[@] Downloading file")
        async with aiohttp.ClientSession() as sesi:
            async with sesi.get(uri) as resp:
                data = await resp.text()
                await ctx.message.delete()
                json_to_patch = ujson.loads(data)

        print("[@] Make sure.")
        preview_msg = await ctx.send(
            "**Are you sure you want to patch " "the database with provided .json file?**"
        )
        to_react = ["✅", "❌"]
        for react in to_react:
            await preview_msg.add_reaction(react)

        def check_react(reaction, user):
            if reaction.message.id != preview_msg.id:
                return False
            if user != ctx.message.author:
                return False
            if str(reaction.emoji) not in to_react:
                return False
            return True

        try:
            res, user = await self.bot.wait_for("reaction_add", timeout=15, check=check_react)
        except asyncio.TimeoutError:
            await ctx.send("***Timeout!***")
            return await preview_msg.clear_reactions()
        if user != ctx.message.author:
            pass
        elif "✅" in str(res.emoji):
            for srv, srv_data in json_to_patch.items():
                if srv == "supermod":
                    await self.dumps_super_admins(srv_data, self.bot.fcwd)
                else:
                    await self.showqueue.add_job(ShowtimesQueueData(srv_data, srv))
            success = await self.ntdb.patch_all_from_json(json_to_patch)
            await preview_msg.clear_reactions()
            if success:
                return await preview_msg.edit(content="**Patching success!, try it with !tagih**")
            await preview_msg.edit(content="**Patching failed!, try it again later**")
        elif "❌" in str(res.emoji):
            print("[@] Patch Cancelled")
            await preview_msg.clear_reactions()
            await preview_msg.edit(content="**Ok, cancelled process**")

    @ntadmin.command()
    async def tambah(self, ctx, srv_id, adm_id, prog_chan=None):
        """
        Menambah server baru ke database naoTimes

        :srv_id: server id
        :adm_id: admin id
        :prog_chan: #progress channel id
        """

        print("[#] Requested !ntadmin tambah by admin")
        if srv_id is None:
            return await ctx.send("Tidak ada input server dari user")

        if adm_id is None:
            return await ctx.send("Tidak ada input admin dari user")

        new_server = await self.showqueue.fetch_database(str(srv_id))
        if new_server is not None:
            return await ctx.send("Server `{}` tersebut telah terdaftar di database".format(srv_id))

        new_srv_data = {}

        new_srv_data["serverowner"] = [str(adm_id)]
        if prog_chan:
            new_srv_data["announce_channel"] = str(prog_chan)
        new_srv_data["anime"] = {}
        new_srv_data["alias"] = {}

        supermod_lists = await self.fetch_super_admins(self.bot.fcwd)
        if str(adm_id) not in supermod_lists:
            supermod_lists.append(str(adm_id))  # Add to supermod list
        print("[#] Created new table for server: {}".format(srv_id))

        await self.showqueue.add_job(ShowtimesQueueData(new_srv_data, str(srv_id)))
        await self.dumps_super_admins(supermod_lists, self.bot.fcwd)
        if not prog_chan:
            prog_chan = None

        success, msg = await self.ntdb.new_server(str(srv_id), str(adm_id), prog_chan)
        if not success:
            print("[%] Failed to update, reason: {}".format(msg))
            if str(srv_id) not in self.bot.showtimes_resync:
                self.bot.showtimes_resync.append(str(srv_id))
        await ctx.send(
            "Sukses menambah server dengan info berikut:\n```Server ID: {s}\nAdmin: {a}\nMemakai #progress Channel: {p}```".format(  # noqa: E501
                s=srv_id, a=adm_id, p=bool(prog_chan)
            )
        )

    @ntadmin.command()
    async def hapus(self, ctx, srv_id):
        """
        Menghapus server dari database naoTimes

        :srv_id: server id
        """
        print("[#] Requested !ntadmin hapus by admin")
        if srv_id is None:
            return await ctx.send("Tidak ada input server dari user")
        srv_data = await self.showqueue.fetch_database(str(srv_id))

        if srv_data is None:
            return await ctx.send("Server tidak dapat ditemukan dalam database.")
        adm_id = srv_data["serverowner"][0]

        super_admins = await self.fetch_super_admins(self.bot.fcwd)

        try:
            super_admins.remove(adm_id)
        except Exception:
            return await ctx.send("Gagal menghapus admin dari data super admin")

        await self.dumps_super_admins(super_admins, self.bot.fcwd)
        fpath = os.path.join(self.bot.fcwd, "showtimes_folder", f"{srv_id}.showtimes")
        try:
            os.remove(fpath)
        except Exception:
            # FIXME: Add logging here
            pass
        success, msg = await self.ntdb.remove_server(srv_id, adm_id)
        if not success:
            await ctx.send(
                "Terdapat kegagalan ketika ingin menghapus server\nalasan: {}".format(msg)  # noqa: E501
            )
        await ctx.send("Sukses menghapus server `{s}` dari naoTimes".format(s=srv_id))

    @ntadmin.command()
    async def tambahadmin(self, ctx, srv_id: str, adm_id: str):
        """
        Menambah admin ke server ke database naoTimes

        :srv_id: server id
        :adm_id: admin id
        """

        print("[#] Requested !ntadmin tambahadmin by admin")
        if srv_id is None:
            return await ctx.send("Tidak ada input server dari user")

        if adm_id is None:
            return await ctx.send("Tidak ada input admin dari user")

        srv_data = await self.showqueue.fetch_database(srv_id)

        if srv_data is None:
            return await ctx.send("Server tidak dapat ditemukan dalam database.")

        if adm_id in srv_data["serverowner"]:
            return await ctx.send("Admin sudah terdaftar di server tersebut.")

        srv_data["serverowner"].append(adm_id)

        await self.showqueue.add_job(ShowtimesQueueData(srv_data, srv_id))
        success, msg = await self.ntdb.update_data_server(srv_id, srv_data)
        if not success:
            print("[%] Failed to update main database data")
            print("\tReason: {}".format(msg))
            if srv_id not in self.bot.showtimes_resync:
                self.bot.showtimes_resync.append(srv_id)
        await ctx.send("Sukses menambah admin `{a}` di server `{s}`".format(s=srv_id, a=adm_id))

    @ntadmin.command()
    async def hapusadmin(self, ctx, srv_id: str, adm_id: str):
        """
        Menghapus admin dari server dari database naoTimes

        :srv_id: server id
        :adm_id: admin id
        """
        print("[#] Requested !ntadmin hapusadmin by admin")
        if srv_id is None:
            return await ctx.send("Tidak ada input server dari user")

        if adm_id is None:
            return await ctx.send("Tidak ada input admin dari user")

        srv_data = await self.showqueue.fetch_database(srv_id)

        if srv_data is None:
            return await ctx.send("Server tidak dapat ditemukan dalam database.")

        if adm_id not in srv_data["serverowner"]:
            return await ctx.send("Tidak dapat menemukan admin tersebut.")

        srv_data["serverowner"].remove(adm_id)

        await self.showqueue.add_job(ShowtimesQueueData(srv_data, srv_id))
        print("[%] Removing admin from main database")
        success, msg = await self.ntdb.update_data_server(srv_id, srv_data)
        if not success:
            print("[%] Failed to update main database data")
            print("\tReason: {}".format(msg))
            if srv_id not in self.bot.showtimes_resync:
                self.bot.showtimes_resync.append(srv_id)
        await ctx.send("Sukses menghapus admin `{a}` dari server `{s}`".format(s=srv_id, a=adm_id))
        if adm_id in srv_data["serverowner"]:
            success, msg = await self.ntdb.remove_top_admin(adm_id)
            if not success:
                await ctx.send("Tetapi gagal menghapus admin dari top_admin.")
