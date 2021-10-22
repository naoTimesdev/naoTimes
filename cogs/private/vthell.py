import logging
import re
from typing import Any, Dict, NamedTuple, Optional, Union
from urllib.parse import quote_plus

import discord
from discord.ext import commands, tasks

from naotimes.bot import naoTimesBot
from naotimes.context import naoTimesContext
from naotimes.helpgenerator import HelpField, HelpOption
from naotimes.socket import ntsocket


class VTHellReceive(NamedTuple):
    id: str
    title: str
    callback: int = None
    path: str = None
    filename: str = None
    is_member: bool = False

    @classmethod
    def from_dict(cls, data: dict):
        file_path = data.get("path")
        file_name = data.get("fn")
        is_member = data.get("member_only", False)
        return cls(
            id=data["id"],
            title=data["title"],
            callback=data.get("callback"),
            path=file_path,
            filename=file_name,
            is_member=is_member,
        )

    def serialize(self):
        return {
            "id": self.id,
            "title": self.title,
            "callback": self.callback,
            "path": self.path,
            "fn": self.filename,
            "is_member": self.is_member,
        }


class VTHellCallback(NamedTuple):
    id: int
    author: int
    channel: int
    guild: int = None

    @classmethod
    def from_dict(cls, data: dict):
        return cls(
            id=int(data["req_callback"]), author=data["author"], channel=data["channel"], guild=data["server"]
        )

    def serialize(self):
        return {
            "req_callback": self.id,
            "author": self.author,
            "channel": self.channel,
            "server": self.guild,
        }


class VTHellReload(NamedTuple):
    id: int
    data: VTHellReceive
    callback: Optional[VTHellCallback] = None

    @classmethod
    def from_dict(cls, data: dict):
        callback = data.get("callback")
        if callback is not None:
            callback = VTHellCallback.from_dict(callback)
        return cls(
            id=data["id"],
            data=VTHellReceive.from_dict(data["data"]),
            callback=callback,
        )

    def serialize(self):
        return {
            "id": self.id,
            "data": self.data.serialize(),
            "callback": self.callback.serialize(),
        }

    def get(self, key: str, default: Any = None):
        try:
            return self.__getattribute__(key)
        except AttributeError:
            return default


def clean_escapes(argument: str):
    if argument.startswith("<") and argument.endswith(">"):
        return argument[1:-1]
    elif argument.startswith("<"):
        return argument[1:]
    elif argument.endswith(">"):
        return argument[:-1]
    return argument


class PrivateVTHell(commands.Cog):
    VTHELL_URL = "https://vthell.ihateani.me/"
    MIZORE_URL = "https://mizore.ihateani.me/vthell/api"
    BASE_KEY = "nvthell_"

    def __init__(self, bot: naoTimesBot):
        self.bot = bot
        self.logger = logging.getLogger("Private.VTHell")

        self.yt_re = re.compile(
            r"(?:https?:\/\/)?(?:youtu\.be\/|(?:www\.|m\.)?youtube\.com\/(?:watch|v|embed)(?:\.php)?(?:\?.*v=|\/))(?P<id>[a-zA-Z0-9\_-]+)"  # noqa: E501
        )

        self._CALLBACK_RELOAD: Dict[int, VTHellReload] = {}
        self._USER_REQUESTED: Dict[int, int] = {}
        self._initialize_vthell.start()

    def cog_unload(self):
        self._initialize_vthell.cancel()

    # Init
    @tasks.loop(seconds=1.0, count=1)
    async def _initialize_vthell(self):
        self.logger.info("Fetching all currently running request...")
        all_request = await self.bot.redisdb.getall(self.BASE_KEY + "*")
        for request in all_request:
            parsed_req = VTHellCallback.from_dict(request)
            self._add_to_count(parsed_req.id)
        self.logger.info("Fetching all reload pending...")
        all_pending_request = await self.bot.redisdb.getall("nvthellreload_*")
        for pending in all_pending_request:
            parsed_pending = VTHellReload.from_dict(pending)
            self._CALLBACK_RELOAD[parsed_pending.id] = parsed_pending
        self.logger.info("Initialization complete!")

        await self.bot.wait_until_ready()
        self.logger.info("Fetching callback channel")
        self.CALLBACK = self.bot.get_channel(764312743851196476)

    # Counter
    def _add_to_count(self, id: int):
        if id not in self._USER_REQUESTED:
            self._USER_REQUESTED[id] = 1
        else:
            self._USER_REQUESTED[id] += 1

    def _get_count(self, id: int):
        if id not in self._USER_REQUESTED:
            self._USER_REQUESTED[id] = 0
        return self._USER_REQUESTED[id]

    def _remove_from_count(self, id: int):
        if id in self._USER_REQUESTED:
            self._USER_REQUESTED[id] -= 1
            if self._USER_REQUESTED[id] < 0:
                self._USER_REQUESTED[id] = 0
        else:
            self._USER_REQUESTED[id] = 0

    # Redis quick function
    async def _remove_request(self, request_id: str):
        await self.bot.redisdb.delete(self.BASE_KEY + request_id)

    async def _add_request(self, data: VTHellCallback):
        await self.bot.redisdb.set(self.BASE_KEY + str(data.id), data.serialize())

    async def _get_request(self, id: Union[int, str]):
        data = await self.bot.redisdb.get(self.BASE_KEY + str(id))
        if data is None:
            return None
        return VTHellCallback.from_dict(data)

    async def _set_reload_request(self, reload: VTHellReload):
        await self.bot.redisdb.set(f"nvthellreload_{reload.id}", reload.serialize())

    async def _remove_reload_request(self, id: Union[int, str]):
        await self.bot.redisdb.delete(f"nvthellreload_{id}")

    # HTTP API
    async def add_new_job(self, url: str, callback: int = None):
        if callback is not None:
            callback = str(callback)
        data = {"url": url, "passkey": "randomizethis", "callback": callback}
        async with self.bot.aiosession.post(f"{self.MIZORE_URL}/jobs", json=data) as resp:
            res = await resp.json()
            if res["status_code"] == 200:
                return True, "Sukses"
            else:
                return False, res["message"]

    async def put_reload_job(self, data: VTHellReceive):
        data = {"url": f"https://youtube.com/watch?v={data.id}", "passkey": "randomizethis"}
        async with self.bot.aiosession.put(f"{self.MIZORE_URL}/jobs", json=data) as resp:
            res = await resp.json()
            if res["status_code"] == 200:
                return True, "Sukses"
            else:
                return False, res["message"]

    async def delete_job(self, url: str):
        data = {"url": url, "passkey": "randomizethis"}
        async with self.bot.aiosession.delete(f"{self.MIZORE_URL}/jobs", json=data) as resp:
            res = await resp.json()
            if res["status_code"] == 200:
                return True, "Sukses"
            else:
                return False, res["message"]

    # vthell paused reaction
    @commands.Cog.listener("on_reaction_add")
    async def _handle_reload_reaction(self, reaction: discord.Reaction, user: discord.Member):
        message = reaction.message
        if message.guild is None:
            return
        msg_id = message.id
        reload_info: Optional[VTHellReload] = self._CALLBACK_RELOAD.get(msg_id, None)
        if reload_info is None:
            return

        callback = reload_info.callback
        if callback is not None and user.id != callback.author:
            return

        if reaction.emoji == "✅":
            await self._remove_reload_request(reload_info.id)
            data = reload_info.data
            success, msg = await self.put_reload_job(data)
            if success:
                await message.channel.send(f"Request/Job ID {data.id} berhasil dimuat ulang!")
            else:
                await message.channel.send(
                    f"Terjadi kesalahan ketika memuat ulang, mohon kontak Owner Bot!\n`{msg}`"
                )
        elif reaction.emoji == "❌":
            await self._remove_reload_request(reload_info.id)
            if reload_info.callback is not None:
                await self._remove_request(reload_info.callback.id)
            await message.clear_reactions()

    # vthell request reaction
    @commands.Cog.listener("on_reaction_add")
    async def _handle_request_reaction(self, reaction: discord.Reaction, user: discord.Member):
        message = reaction.message
        if message.guild is None:
            return
        msg_id = message.id
        request_info = await self.bot.redisdb.get(f"nvthellreq_{msg_id}")
        if request_info is None:
            return
        parsed_callback = VTHellCallback.from_dict(request_info)

        channel: discord.TextChannel = self.bot.get_channel(parsed_callback.channel)
        vth_url = request_info["url"]
        if reaction.emoji == "✅":
            await self.add_new_job(vth_url, parsed_callback.id)
            await self._add_request(parsed_callback)
            await self.bot.redisdb.delete(f"nvthellreq_{msg_id}")
            await message.clear_reactions()
            await channel.send(
                content=f"✅ <@{parsed_callback.author}> Request anda telah diterima oleh Owner Bot!\n"
                f"Mohon periksa dengan `{self.bot.prefixes(channel)}vthell status {vth_url}`"
            )
        elif reaction.emoji == "❌":
            await self._remove_request(parsed_callback.id)
            await self.bot.redisdb.delete(f"nvthellreq_{msg_id}")
            await message.clear_reactions()
            await channel.send(
                f"❌ <@{parsed_callback.author}> Request anda ditolak oleh Owner Bot. [<{vth_url}>]"
            )

    # vthell start
    @ntsocket("vthell start", False)
    async def _handle_started_stream(self, sid: str, raw_data: dict):
        data = VTHellReceive.from_dict(raw_data)
        callback: discord.TextChannel = self.CALLBACK
        request = None
        if data.callback is not None:
            request = await self._get_request(data.callback)
            if request is not None:
                cb_test = self.bot.get_channel(request.channel)
                if isinstance(callback, (discord.TextChannel, discord.DMChannel)):
                    callback = cb_test

        send_msg = None
        if request is not None:
            author = request.author
            send_msg = f"<@{author}> Request anda mulai direkam!"
        self.logger.info(f"{sid}: creating embed...")
        embed = discord.Embed(
            title="VTHell Start...",
            color=0xA49BE6,
            timestamp=self.bot.now().datetime,
        )
        job_title = data.title
        task_id = data.id
        embed.description = f"Rekaman dimulai!\n**{job_title}**\n"
        embed.description += f"URL: **https://youtu.be/{task_id}**"
        embed.set_image(url=f"https://i.ytimg.com/vi/{task_id}/maxresdefault.jpg")
        self.logger.info(f"{sid}: sending data...")
        await callback.send(send_msg, embed=embed)
        if callback != self.CALLBACK:
            await self.CALLBACK.send(embed=embed)
        return "ok"

    @staticmethod
    def _secure_url_path(path: str, filename: str):
        explode_path = path.replace("\\", "/").split("/")
        secured_path = []
        for p in explode_path:
            secured_path.append(quote_plus(p))
        secured_path.append(quote_plus(filename))
        return "/".join(secured_path)

    # vthell done
    @ntsocket("vthell done", False)
    async def _handle_finish_stream(self, sid: str, raw_data: dict):
        data = VTHellReceive.from_dict(raw_data)
        callback: discord.TextChannel = self.CALLBACK
        request = None
        if data.callback is not None:
            request = await self._get_request(data.callback)
            if request is not None:
                cb_test = self.bot.get_channel(request.channel)
                if isinstance(callback, (discord.TextChannel, discord.DMChannel)):
                    callback = cb_test
                # Remove
                await self._remove_request(data.callback)

        EXTEND_PATH = self.VTHELL_URL
        EXTEND_PATH += "0:/" if not data.is_member else "4:/"
        EXTEND_PATH += self._secure_url_path(data.path, data.filename)
        send_msg = None
        if request is not None:
            author = request.author
            send_msg = f"<@{author}> Request anda selesai direkam."
        self.logger.info(f"{sid}: creating embed...")
        embed = discord.Embed(
            title="VTHell Done",
            color=0x9FE69B,
            timestamp=self.bot.now().datetime,
        )
        job_title = data.title
        embed.description = f"Rekaman Selesai\n**{job_title}**"
        task_id = data.id
        embed.add_field(name="Link", value=f"[Rekaman]({EXTEND_PATH})\n[Stream](https://youtu.be/{task_id})")
        embed.set_image(url=f"https://i.ytimg.com/vi/{task_id}/maxresdefault.jpg")
        self.logger.info(f"{sid}: sending data...")
        await callback.send(send_msg, embed=embed)
        if callback != self.CALLBACK:
            await self.CALLBACK.send(embed=embed)
        return "ok"

    # vthell restart
    @ntsocket("vthell restart", False)
    async def _handle_restarted_stream(self, sid: str, raw_data: dict):
        data = VTHellReceive.from_dict(raw_data)
        callback: discord.TextChannel = self.CALLBACK
        request = None
        if data.callback is not None:
            request = await self._get_request(data.callback)
            if request is not None:
                cb_test = self.bot.get_channel(request.channel)
                if isinstance(callback, (discord.TextChannel, discord.DMChannel)):
                    callback = cb_test

        send_msg = None
        if request is not None:
            author = request.author
            send_msg = f"<@{author}> Request rekaman anda sedang dilanjutkan kembali!"
        self.logger.info(f"{sid}: creating embed...")
        embed = discord.Embed(
            title="VTHell Continuing...",
            color=0xE6DF9B,
            timestamp=self.bot.now().datetime,
        )
        job_title = data.title
        task_id = data.id
        embed.description = f"Rekaman dilanjutkan\n**{job_title}**\n"
        embed.description += f"URL: **https://youtu.be/{task_id}**"
        embed.set_image(url=f"https://i.ytimg.com/vi/{task_id}/maxresdefault.jpg")
        self.logger.info(f"{sid}: sending data...")
        await callback.send(content=send_msg, embed=embed)
        if callback != self.CALLBACK:
            await self.CALLBACK.send(embed=embed)
        return "ok"

    # vthell autoadd
    @ntsocket("vthell autoadd", False)
    async def _handle_autoadd_streams(self, sid: str, raw_data: dict):
        data = VTHellReceive.from_dict(raw_data)
        self.logger.info(f"Received auto-add from {sid}: {raw_data}")
        embed = discord.Embed(title="VTHell Auto-add", color=0xD0DF69, timestamp=self.bot.now().datetime)
        embed.description = f"**{data.title}**\n[Link](https://youtu.be/{data.id})"
        embed.set_image(url=f"https://i.ytimg.com/vi/{data.id}/maxresdefault.jpg")
        await self.CALLBACK.send(embed=embed)
        return "ok"

    # vthell error
    @ntsocket("vthell error", False)
    async def _handle_error_streams(self, sid: str, raw_data: dict):
        self.logger.info(f"Received error from {sid}: {raw_data}")
        data = VTHellReceive.from_dict(raw_data)
        embed = discord.Embed(title="VTHell Error", color=0xB93C3C, timestamp=self.bot.now().datetime)
        description = f"**{data.title}**\n[Link](https://youtu.be/{data.id})"
        err_reason = data.get("reason", "An unknown error occured!")
        description += f"\n**Reason**: {err_reason}"
        embed.description = description
        embed.set_image(url=f"https://i.ytimg.com/vi/{data.id}/maxresdefault.jpg")
        await self.CALLBACK.send(embed=embed)
        return "ok"

    # vthell paused
    @ntsocket("vthell paused", False)
    async def _handle_paused_streams(self, sid: str, raw_data: dict):
        self.logger.info(f"Received paused data from {sid}: {raw_data}")
        data = VTHellReceive.from_dict(raw_data)
        callback: discord.TextChannel = self.CALLBACK
        request = None
        if data.callback is not None:
            request = await self._get_request(data.callback)
            if request is not None:
                cb_test = self.bot.get_channel(request.channel)
                if isinstance(callback, (discord.TextChannel, discord.DMChannel)):
                    callback = cb_test

        send_msg = None
        if request is not None:
            author = request.author
            send_msg = f'<@{author}> Request anda sedang "pause", mohon klik reaction untuk mulai ulang!'

        embed = discord.Embed(
            title="VTHell Paused",
            color=0xB93C3C,
            timestamp=self.bot.now().datetime,
        )
        embed.description = f"**{data.title}**\n[Link](https://youtu.be/{data.id})"
        embed.set_image(url=f"https://i.ytimg.com/vi/{data.id}/maxresdefault.jpg")

        if not isinstance(callback, discord.TextChannel):
            send_msg = None
            callback = self.CALLBACK

        new_callback = await callback.send(content=send_msg, embed=embed)
        self.logger.info(f"{sid}: reacting to message")
        await new_callback.add_reaction("✅")
        await new_callback.add_reaction("❌")
        RELOAD_DATA = VTHellReload(new_callback.id, data, request)
        self._CALLBACK_RELOAD[new_callback.id] = RELOAD_DATA
        await self._set_reload_request(RELOAD_DATA)
        return "ok"

    # Commands
    @commands.group(name="vthell", aliases=["vtrec"])
    async def _pp_vthell(self, ctx: naoTimesContext):
        if ctx.invoked_subcommand is None:
            if not ctx.empty_subcommand(2):
                return await ctx.send("Tidak dapat menemukan perintah tersebut.")
            helpcmd = ctx.create_help("VTuberHell Recorder[*]", desc=f"Versi {self.bot.semver}")
            is_owner = await self.bot.is_owner(ctx.author)
            helpcmd.add_fields(
                [
                    HelpField(
                        "vthell request", "Request rekam stream VTuber", [HelpOption("url", required=True)]
                    ),
                    # HelpField("vthell list", "List stream VTuber yang sedang/akan direkam"),
                    HelpField(
                        "vthell stats",
                        "Lihat informasi rekaman stream VTuber",
                        [
                            HelpOption(
                                "url",
                                required=True,
                            )
                        ],
                    ),
                ]
            )
            if is_owner:
                helpcmd.add_fields(
                    [
                        HelpField(
                            "vthell add",
                            "Tambah stream baru ke tools rekaman",
                            [
                                HelpOption(
                                    "url",
                                    required=True,
                                )
                            ],
                        ),
                        HelpField(
                            "vthell remove",
                            "Hapus stream VTuber dari tools rekaman",
                            [
                                HelpOption(
                                    "url",
                                    required=True,
                                )
                            ],
                        ),
                    ]
                )
            helpcmd.add_aliases(["vtrec"])
            await ctx.send(embed=helpcmd.get())

    @_pp_vthell.command(name="request")
    @commands.guild_only()
    async def _pp_vthell_request(self, ctx: naoTimesContext, *, url: clean_escapes):
        channel: discord.TextChannel = ctx.channel
        guild: discord.Guild = ctx.guild
        author: discord.Member = ctx.author
        self.logger.info(f"requested new recording by {str(author)}")
        count = self._get_count(author.id)
        if count >= 2:
            return await ctx.send("Tidak bisa request lagi, maksimum 2 request tiap user!")

        validate_url = re.match(self.yt_re, url)
        if not validate_url:
            return await ctx.send("Bukan URL YouTube!")
        match_id = validate_url.group("id")
        if not match_id:
            return await ctx.send("Bukan URL YouTube!")

        embed = discord.Embed(title="VTHell Request", color=0x6989DF, timestamp=self.bot.now().datetime)
        embed.description = f"Requested by: **{str(author)}**\nStream: **https://youtu.be/{match_id}**"
        embed.set_image(url=f"https://i.ytimg.com/vi/{match_id}/maxresdefault.jpg")
        main_msg = await self.CALLBACK.send(embed=embed)
        await main_msg.add_reaction("✅")
        await main_msg.add_reaction("❌")

        callback_base = VTHellCallback(main_msg.id, author.id, channel.id, guild.id)
        request_data = callback_base.serialize()
        request_data["url"] = f"https://youtube.com/watch?v={match_id}"
        await self.bot.redisdb.set(f"nvthellreq_{callback_base.id}", request_data)
        await ctx.send("Request diterima, mohon tunggu jawaban owner.")

    @_pp_vthell.command(name="add")
    @commands.is_owner()
    async def _pp_vthell_add_owner(self, ctx: naoTimesContext, *, url: clean_escapes):
        validate_url = re.match(self.yt_re, url)
        if not validate_url:
            return await ctx.send("Bukan URL YouTube!")
        match_id = validate_url.group("id")
        if not match_id:
            return await ctx.send("Bukan URL YouTube!")

        await self.add_new_job(f"https://youtube.com/watch?v={match_id}")
        await ctx.send(f"Tertambah, silakan periksa dengan command `{self.bot.prefixes(ctx)}vthell stats`")

    @_pp_vthell.command(name="remove")
    @commands.is_owner()
    async def _pp_vthell_remove_owner(self, ctx: naoTimesContext, *, url: clean_escapes):
        validate_url = re.match(self.yt_re, url)
        if not validate_url:
            return await ctx.send("Bukan URL YouTube!")
        match_id = validate_url.group("id")
        if not match_id:
            return await ctx.send("Bukan URL YouTube!")

        res, msg = await self.delete_job(f"https://youtube.com/watch?v={match_id}")
        if res:
            return await ctx.send("Job berhasil dihapus dari tools rekaman!")
        await ctx.send(f"Terjadi kesalahan, pesan dari API: `{msg}`")

    @_pp_vthell.command(name="stats", aliases=["status"])
    async def _pp_vthell_status(self, ctx: naoTimesContext, *, url: clean_escapes):
        validate_url = re.match(self.yt_re, url)
        if not validate_url:
            return await ctx.send("Bukan URL YouTube.")
        match_id = validate_url.group("id")
        if not match_id:
            return await ctx.send("Bukan URL YouTube.")

        async with self.bot.aiosession.get(f"{self.MIZORE_API}/status/{match_id}") as resp:
            raw_response = (await resp.json())["data"]
            if match_id not in raw_response:
                return await ctx.send("Tidak dapat menemukan URL tersebut di VTHell")

        status_response = raw_response[match_id]
        if not status_response:
            return await ctx.send("Tidak dapat menemukan URL tersebut di VTHell")

        callback_data: Optional[VTHellCallback] = None
        if "discordCallback" in status_response:
            callback_data = await self._get_request(status_response["discordCallback"])

        recording_status = status_response["stats"]
        embed = discord.Embed(color=0x6989DF, title="VTHell Status")
        descr = ""
        if callback_data is not None:
            user_data = self.bot.get_user(callback_data.author)
            if user_data is not None:
                descr += f"Requested by: **{str(user_data)}**\n"
        descr += f"**{status_response['title']}**\n"
        descr += f"Stream: **{status_response['url']}**\n"
        if recording_status["member"]:
            descr += "**Member-Only Stream**\n"
        descr += "\n"
        embed.set_image(url=status_response["thumb"])

        rec_status = "Unknown"
        if recording_status["recording"] is False and recording_status["recorded"] is False:
            rec_status = "Waiting for Stream!"
        elif recording_status["recording"] is True:
            rec_status = "Recording Stream!"
        elif recording_status["recording"] is False and recording_status["recorded"] is True:
            rec_status = "Saving Recording!"
        elif recording_status["paused"] is True:
            rec_status = "Recording Paused, please refresh."
        descr += f"Current Status: **{rec_status}**"
        embed.description = descr

        await ctx.send(embed=embed)

    @_pp_vthell.command(name="mock")
    @commands.is_owner()
    async def _pp_vthell_mock(self, ctx: naoTimesContext):
        author = ctx.author
        channel = ctx.channel
        guild = ctx.guild
        match_id = "zE_cNfrIogo"
        embed = discord.Embed(title="VTHell Request", color=0x6989DF, timestamp=self.bot.now().datetime)
        embed.description = f"Requested by: **{str(author)}**\nStream: **https://youtu.be/{match_id}**"
        embed.set_image(url=f"https://i.ytimg.com/vi/{match_id}/maxresdefault.jpg")
        main_msg = await self.CALLBACK.send(embed=embed)

        callback_base = VTHellCallback(main_msg.id, author.id, channel.id, guild.id)
        request_data = callback_base.serialize()
        request_data["url"] = f"https://youtube.com/watch?v={match_id}"
        await self.bot.redisdb.set(f"{self.BASE_KEY}{callback_base.id}", request_data)
        await ctx.send(f"Callback ID: {callback_base.id}")


def setup(bot: naoTimesBot):
    bot.add_cog(PrivateVTHell(bot))
