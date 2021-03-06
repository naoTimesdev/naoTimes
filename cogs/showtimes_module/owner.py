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
from nthelper.utils import HelpGenerator, write_files
from nthelper.showtimes_helper import ShowtimesQueueData
from nthelper.bot import naoTimesBot

from .base import ShowtimesBase


class ShowtimesOwner(commands.Cog, ShowtimesBase):
    def __init__(self, bot: naoTimesBot):
        """Showtimes Owner class.

        This class controls all of stuff that only bot owner can access.

        Args:
            bot (naoTimesBot): Bot
        """
        super(ShowtimesOwner, self).__init__()
        self.bot = bot
        self.ntdb = bot.ntdb
        self.bot_config = bot.botconf
        self.showqueue = bot.showqueue
        self.srv_lists = partial(self.fetch_servers, cwd=bot.fcwd)
        self.logger = logging.getLogger("cogs.showtimes_module.owner.ShowtimesOwner")

    def __str__(self):
        return "Showtimes Owner"

    @commands.group(aliases=["naotimesadmin", "naoadmin"])
    @commands.is_owner()
    @commands.guild_only()
    async def ntadmin(self, ctx):  # noqa: D102
        if ctx.invoked_subcommand is None:
            helpcmd = HelpGenerator(self.bot, "ntadmin", desc=f"Versi {self.bot.semver}",)
            await helpcmd.generate_field(
                "ntadmin", desc="Memunculkan bantuan perintah ini.",
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
                desc="Menambah admin ke server baru yang terdaftar di database.",
                opts=[{"name": "server id", "type": "r"}, {"name": "admin id", "type": "r"}],
            )
            await helpcmd.generate_field(
                "ntadmin hapusadmin",
                desc="Menghapus admin dari server baru yang terdaftar di database.",
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
            await helpcmd.generate_aliases(["naotimesadmin", "naoadmin"])
            await ctx.send(embed=helpcmd.get())

    @ntadmin.command()
    async def listserver(self, ctx):  # noqa: D102
        if self.ntdb is None:
            self.logger.info("owner hasn't enabled naoTimesDB yet.")
            return
        self.logger.info("Requested list server by bot owner.")
        srv_dumps = await self.srv_lists()
        if not srv_dumps:
            return

        srv_list = []
        for srv in srv_dumps:
            if srv == "supermod":
                continue
            srv_ = self.bot.get_guild(int(srv))
            if not srv_:
                self.logger.warning(f"{srv}: unknown server")
                continue
            srv_list.append(f"{srv_.name} ({srv})")

        text = "**List server ({} servers):**\n".format(len(srv_list))
        for x in srv_list:
            text += x + "\n"

        text = text.rstrip("\n")

        await ctx.send(text)

    @ntadmin.command()
    async def listresync(self, ctx):  # noqa: D102
        if self.ntdb is None:
            self.logger.info("owner hasn't enabled naoTimesDB yet.")
            return
        self.logger.info("Requested resync list by bot owner.")
        resynclist = self.bot.showtimes_resync
        if not resynclist:
            return await ctx.send("**Server that still need to be resynced**: None")
        resynclist = ["- {}\n".format(x) for x in resynclist]
        main_text = "**Server that still need to be resynced**:\n"
        main_text += "".join(resynclist)
        main_text = main_text.rstrip("\n")
        await ctx.send(main_text)

    @ntadmin.command()
    async def fetchdb(self, ctx):  # noqa: D102
        if self.ntdb is None:
            self.logger.info("owner hasn't enabled naoTimesDB yet.")
            return
        self.logger.info("Fetching database from local db.")
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

        super_admin = await self.fetch_super_admins(self.bot.redisdb)
        final_dataset["supermod"] = super_admin

        self.logger.info("Dumping database to one big json.")
        save_file_name = str(int(round(time.time()))) + "_naoTimes_database.json"
        await write_files(final_dataset, save_file_name)

        self.logger.info("Sending to requester.")
        await channel.send(content="Here you go!", file=discord.File(save_file_name))
        os.remove(save_file_name)  # Cleanup

    @ntadmin.command()
    async def forcepull(self, ctx):  # noqa: D102
        if self.ntdb is None:
            self.logger.info("owner hasn't enabled naoTimesDB yet.")
            return
        self.logger.info("Forcing local database with remote database.")
        channel = ctx.message.channel

        json_d = await self.ntdb.fetch_all_as_json()
        for srv, srv_data in json_d.items():
            if srv == "supermod":
                await self.dumps_super_admins(srv_data, self.bot.redisdb)
            else:
                self.logger.info(f"{srv}: saving...")
                await self.showqueue.add_job(ShowtimesQueueData(srv_data, srv))
        await channel.send("Newest database has been pulled and saved to local save")

    @ntadmin.command()
    @commands.guild_only()
    async def patchdb(self, ctx):  # noqa: D102
        if self.ntdb is None:
            self.logger.info("owner hasn't enabled naoTimesDB yet.")
            return
        """This will patch entire database."""
        self.logger.info("Initiating database by bot owner")

        if ctx.message.attachments == []:
            await ctx.message.delete()
            return await ctx.send(
                "Please provide a valid .json file by uploading and add `!!ntadmin patchdb` command"
            )

        self.logger.info("Fetching attachments...")
        attachment = ctx.message.attachments[0]
        uri = attachment.url
        filename = attachment.filename

        if filename[filename.rfind(".") :] != ".json":
            await ctx.message.delete()
            return await ctx.send(
                "Please provide a valid .json file by uploading and add `!!ntadmin patchdb` command"
            )

        # Start downloading .json file
        self.logger.info("Downloading attachments...")
        async with aiohttp.ClientSession() as sesi:
            async with sesi.get(uri) as resp:
                data = await resp.text()
                await ctx.message.delete()
                json_to_patch = ujson.loads(data)

        self.logger.info("Making sure...")
        preview_msg = await ctx.send(
            "**Are you sure you want to patch the database with provided .json file?**"
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
            self.logger.info("Patching database...")
            for srv, srv_data in json_to_patch.items():
                if srv == "supermod":
                    await self.dumps_super_admins(srv_data, self.bot.redisdb)
                else:
                    await self.showqueue.add_job(ShowtimesQueueData(srv_data, srv))
            self.logger.info("Patching remote database...")
            success = await self.ntdb.patch_all_from_json(json_to_patch)
            await preview_msg.clear_reactions()
            if success:
                self.logger.info("Remote database patched successfully")
                return await preview_msg.edit(content="**Patching success!, try it with !tagih**")
            self.logger.error("Failed to patch remote database...")
            await preview_msg.edit(content="**Patching failed!, try it again later**")
        elif "❌" in str(res.emoji):
            self.logger.warning("Database patching cancelled.")
            await preview_msg.clear_reactions()
            await preview_msg.edit(content="**Ok, cancelled process**")

    @ntadmin.command()
    async def tambah(self, ctx, srv_id, adm_id, prog_chan=None):  # noqa: D102
        if self.ntdb is None:
            self.logger.info("owner hasn't enabled naoTimesDB yet.")
            return
        self.logger.info("Initiated new server addition to database...")
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

        if "announce_channel" in new_srv_data and new_srv_data["announce_channel"] == "":
            del new_srv_data["announce_channel"]

        supermod_lists = await self.fetch_super_admins(self.bot.redisdb)
        if str(adm_id) not in supermod_lists:
            supermod_lists.append(str(adm_id))  # Add to supermod list
        self.logger.info(f"Created new server data for: {srv_id}")

        self.logger.info(f"{srv_id}: dumping to local db")
        await self.showqueue.add_job(ShowtimesQueueData(new_srv_data, str(srv_id)))
        await self.dumps_super_admins(supermod_lists, self.bot.redisdb)
        if not prog_chan:
            prog_chan = None

        self.logger.info(f"{srv_id}: committing to remote database")
        success, msg = await self.ntdb.new_server(str(srv_id), str(adm_id), prog_chan)
        if not success:
            self.logger.error(f"{srv_id}: failed to update remote db, reason: {msg}")
            if str(srv_id) not in self.bot.showtimes_resync:
                self.bot.showtimes_resync.append(str(srv_id))
        self.logger.info(f"{srv_id}: new server added with admin {adm_id} and {prog_chan} channel.")
        await ctx.send(
            "Sukses menambah server dengan info berikut:\n```Server ID: {s}\nAdmin: {a}\nMemakai #progress Channel: {p}```".format(  # noqa: E501
                s=srv_id, a=adm_id, p=bool(prog_chan)
            )
        )

    @ntadmin.command()
    async def hapus(self, ctx, srv_id):  # noqa: D102
        if self.ntdb is None:
            self.logger.info("owner hasn't enabled naoTimesDB yet.")
            return
        self.logger.info("Initiated server removal from database...")
        if srv_id is None:
            return await ctx.send("Tidak ada input server dari user")
        srv_data = await self.showqueue.fetch_database(str(srv_id))

        if srv_data is None:
            self.logger.warning(f"{srv_id}: Unknown server")
            return await ctx.send("Server tidak dapat ditemukan dalam database.")
        adm_id = srv_data["serverowner"][0]

        self.logger.info(f"{srv_id}: Removing super admin")
        super_admins = await self.fetch_super_admins(self.bot.redisdb)

        try:
            super_admins.remove(adm_id)
        except Exception:
            return await ctx.send("Gagal menghapus admin dari data super admin")

        await self.dumps_super_admins(super_admins, self.bot.redisdb)
        self.logger.warning(f"{srv_id}: Removing from database")
        fpath = os.path.join(self.bot.fcwd, "showtimes_folder", f"{srv_id}.showtimes")
        try:
            os.remove(fpath)
        except FileNotFoundError:
            pass
        success, msg = await self.ntdb.remove_server(srv_id, adm_id)
        if not success:
            self.logger.error(f"{srv_id}: Failed to remove from main database, reason: {msg}")
            await ctx.send(
                "Terdapat kegagalan ketika ingin menghapus server\nalasan: {}".format(msg)  # noqa: E501
            )
        self.logger.info(f"{srv_id}: Server removed from database.")
        await ctx.send("Sukses menghapus server `{s}` dari naoTimes".format(s=srv_id))

    @ntadmin.command()
    async def tambahadmin(self, ctx, srv_id: str, adm_id: str):  # noqa: D102
        if self.ntdb is None:
            self.logger.info("owner hasn't enabled naoTimesDB yet.")
            return
        self.logger.info(f"{srv_id}: Adding new admin ({adm_id})")
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

        self.logger.info(f"{srv_id}: Commiting to database...")
        await self.showqueue.add_job(ShowtimesQueueData(srv_data, srv_id))
        success, msg = await self.ntdb.update_data_server(srv_id, srv_data)
        if not success:
            self.logger.error(f"{srv_id}: Failed to update main database, reason: {msg}")
            if srv_id not in self.bot.showtimes_resync:
                self.bot.showtimes_resync.append(srv_id)
        self.logger.info(f"{srv_id}: Admin `{adm_id}` added to database...")
        await ctx.send("Sukses menambah admin `{a}` di server `{s}`".format(s=srv_id, a=adm_id))

    @ntadmin.command()
    async def hapusadmin(self, ctx, srv_id: str, adm_id: str):  # noqa: D102
        if self.ntdb is None:
            self.logger.info("owner hasn't enabled naoTimesDB yet.")
            return
        self.logger.info(f"{srv_id}: Removing admin ({adm_id})")
        if srv_id is None:
            return await ctx.send("Tidak ada input server dari user")

        if adm_id is None:
            return await ctx.send("Tidak ada input admin dari user")

        srv_data = await self.showqueue.fetch_database(srv_id)
        super_admins = await self.fetch_super_admins(self.bot.redisdb)

        if srv_data is None:
            return await ctx.send("Server tidak dapat ditemukan dalam database.")

        if adm_id not in srv_data["serverowner"]:
            return await ctx.send("Tidak dapat menemukan admin tersebut.")

        srv_data["serverowner"].remove(adm_id)

        self.logger.info(f"{srv_id}: Commiting to database...")
        await self.showqueue.add_job(ShowtimesQueueData(srv_data, srv_id))
        success, msg = await self.ntdb.update_data_server(srv_id, srv_data)
        if not success:
            self.logger.error(f"{srv_id}: Failed to update main database, reason: {msg}")
            if srv_id not in self.bot.showtimes_resync:
                self.bot.showtimes_resync.append(srv_id)
        self.logger.info(f"{srv_id}: Admin `{adm_id}` removed from database...")
        await ctx.send("Sukses menghapus admin `{a}` dari server `{s}`".format(s=srv_id, a=adm_id))
        if str(adm_id) in super_admins:
            self.logger.info(f"{srv_id}: Commiting to top admin database...")
            super_admins.remove(str(adm_id))
            await self.dumps_super_admins(super_admins, self.bot.redisdb)
            success, msg = await self.ntdb.remove_top_admin(adm_id)
            if not success:
                self.logger.error(f"{srv_id}: Failed to update top admin database, reason: {msg}")
                await ctx.send("Tetapi gagal menghapus admin dari top_admin.")

    @ntadmin.command(name="initialisasi", aliases=["init", "initialize"])
    async def ntadmin_initialisasi(self, ctx):
        if self.ntdb is None:
            self.logger.info("owner hasn't enabled naoTimesDB yet.")
            return await ctx.send(
                "naoTimesDB are not connected, please restart bot or use reloadconf to try and reconnect it."
            )
        server_lists = await self.srv_lists()
        if server_lists:
            return await ctx.send("naoTimes Showtimes already initialized.")

    @ntadmin.command()
    async def modify_db(self, ctx):  # noqa: D102
        if self.ntdb is None:
            self.logger.info("owner hasn't enabled naoTimesDB yet.")
            return
        self.logger.info("Batch modifying db, this time: mal_id addition...")

        async def _internal_fetch(srv_id):
            data_res = await self.showqueue.fetch_database(srv_id)
            return data_res, srv_id

        srv_lists = await self.srv_lists()
        fetch_jobs = [_internal_fetch(srv) for srv in srv_lists]

        msg_dc = await ctx.send("Fetching all database...")
        final_dataset = {}
        for fjob in asyncio.as_completed(fetch_jobs):
            data_res, srv_id = await fjob
            if data_res is not None:
                final_dataset[srv_id] = data_res

        def get_username_of_user(user_id):
            try:
                user_data = self.bot.get_user(int(user_id))
                return user_data.name
            except Exception:
                return None

        await msg_dc.edit(content="Monkey-patching DB...")
        for srv_id, srv_data in final_dataset.items():
            for ani, ani_data in srv_data["anime"].items():
                staffes = ani_data["staff_assignment"]
                new_staffes = {}
                for staff_pos, staff_id in staffes.items():
                    if isinstance(staff_id, dict):
                        new_staffes[staff_pos] = staff_id
                    else:
                        new_staffes[staff_pos] = {"id": staff_id, "name": get_username_of_user(staff_id)}
                final_dataset[srv_id]["anime"][ani]["staff_assignment"] = new_staffes

        super_admins = await self.fetch_super_admins(self.bot.redisdb)
        final_dataset["supermod"] = super_admins

        self.logger.info("Patching database...")
        await msg_dc.edit(content="Patching to database...")
        for srv, srv_data in final_dataset.items():
            if srv == "supermod":
                await self.dumps_super_admins(srv_data, self.bot.redisdb)
            else:
                await self.showqueue.add_job(ShowtimesQueueData(srv_data, srv))
        self.logger.info("Patching remote database...")
        success = await self.ntdb.patch_all_from_json(final_dataset)
        if success:
            await ctx.send("Success!")
