import asyncio
import logging
from dataclasses import dataclass
from typing import List, Optional, Tuple, TypeVar, Union

import arrow
import disnake
from disnake.ext import commands

from naotimes.bot import naoTimesBot
from naotimes.config import naoTimesTicketConfig
from naotimes.context import naoTimesContext


class naoTixAttachment:
    def __init__(self, url: str, filename: str, ctype: Optional[str] = None):
        self.url = url
        self.filename = filename
        self._type = ctype

    @property
    def type(self):
        return self._type or ""

    @property
    def is_sticker(self):
        if self.filename.startswith("Stiker:") and self._type in ["png", "apng", "lottie"]:
            return True
        return False

    @classmethod
    def from_dict(cls, data: dict):
        return cls(data["url"], data["filename"], data["type"])

    @classmethod
    def from_attachment(cls, data: disnake.Attachment):
        return cls(data.url, data.filename, data.content_type)

    @classmethod
    def from_sticker(cls, data: disnake.StickerItem):
        return cls(data.url, f"Stiker: {data.name}", data.format.name)

    def serialize(self):
        return {"url": self.url, "filename": self.filename, "type": self._type}


class naoTixUser:
    def __init__(self, id: int, name: str, discriminator: str, avatar: str):
        self.id = id
        self.name = name
        self.discriminator = discriminator
        self.avatar = avatar

    def __str__(self):
        return f"{self.name}#{self.discriminator}"

    @classmethod
    def from_dict(cls, data: dict):
        return cls(
            id=data["id"], name=data["username"], discriminator=data["discriminator"], avatar=data["avatar"]
        )

    @classmethod
    def from_user(cls, member: Union[disnake.Member, disnake.User]):
        return cls(
            id=member.id,
            name=member.name,
            discriminator=member.discriminator,
            avatar=member.avatar.with_format("png").url,
        )

    def serialize(self):
        return {
            "id": self.id,
            "username": self.name,
            "discriminator": self.discriminator,
            "avatar": self.avatar,
        }


class naoTixMessage:
    def __init__(
        self,
        author: naoTixUser,
        content: str,
        attachments: List[naoTixAttachment] = [],
        timestamp: int = None,
    ):
        self.author = author
        self.content = content
        self.attachments = attachments
        self.timestamp = timestamp or arrow.utcnow().int_timestamp

    @classmethod
    def from_dict(cls, data: dict):
        return cls(
            author=naoTixUser.from_dict(data["author"]),
            content=data["content"],
            attachments=[naoTixAttachment.from_dict(attachment) for attachment in data["attachments"]],
            timestamp=data["timestamp"],
        )

    @classmethod
    def from_message(cls, data: disnake.Message):
        content = data.clean_content
        author = naoTixUser.from_user(data.author)
        attachments = [naoTixAttachment.from_attachment(attachment) for attachment in data.attachments]
        stickers = data.stickers
        for sticker in stickers:
            attachments.append(naoTixAttachment.from_sticker(sticker))
        timestamp = data.created_at.timestamp()
        return cls(author=author, content=content, attachments=attachments, timestamp=timestamp)

    def serialize(self):
        return {
            "author": self.author.serialize(),
            "content": self.content,
            "attachments": [attachment.serialize() for attachment in self.attachments],
            "timestamp": self.timestamp,
        }


class naoTixChannel:
    def __init__(self, id: int, name: str):
        self.id = id
        self.name = name

    @classmethod
    def from_dict(cls, data: dict):
        return cls(id=data["id"], name=data["name"])

    @classmethod
    def from_channel(cls, data: disnake.TextChannel):
        return cls(id=data.id, name=data.name)

    def serialize(self):
        return {"id": self.id, "name": self.name}


TicketTarget = TypeVar("TicketTarget", naoTixUser, naoTixChannel)


@dataclass
class TicketForwarder:
    message: naoTixMessage
    target: TicketTarget
    raw_message: disnake.Message


class naoTixHandler:
    def __init__(
        self,
        user: naoTixUser,
        channel: naoTixChannel,
        messages: List[naoTixMessage],
        timestamp: Optional[int] = None,
    ):
        self._user = user
        self._channel = channel
        self._messages = messages
        self._timestamp = timestamp or arrow.utcnow().int_timestamp
        self._closed_by: Optional[naoTixUser] = None

    @property
    def id(self) -> int:
        return self._user.id

    @property
    def user(self) -> naoTixUser:
        return self._user

    @property
    def channel(self) -> naoTixChannel:
        return self._channel

    @channel.setter
    def channel(self, value: naoTixChannel):
        self._channel = value

    @property
    def messages(self) -> List[naoTixMessage]:
        return self._messages

    @property
    def timestamp(self):
        return self._timestamp

    @property
    def closed_by(self):
        return self._closed_by

    def add_message(self, message: naoTixMessage):
        self._messages.append(message)

    def set_closed(self, user: naoTixUser):
        self._closed_by = user

    @property
    def is_on_hold(self):
        return self._closed_by is not None

    @classmethod
    def from_dict(cls, data: dict):
        base = cls(
            user=naoTixUser.from_dict(data["user"]),
            messages=[naoTixMessage.from_dict(message) for message in data["messages"]],
            channel=naoTixChannel.from_dict(data["channel"]),
            timestamp=data["timestamp"],
        )
        if data["closed_by"] is not None:
            base.set_closed(naoTixUser.from_dict(data["closed_by"]))
        return base

    def serialize(self):
        closed_by = None
        if self._closed_by is not None:
            closed_by = self._closed_by.serialize()
        return {
            "user": self._user.serialize(),
            "messages": [message.serialize() for message in self._messages],
            "channel": self._channel.serialize(),
            "timestamp": self._timestamp,
            "closed_by": closed_by,
        }

    def is_valid(self, target_id: int):
        return self._user.id == target_id or self._channel.id == target_id


class BotBrainTicketing(commands.Cog):
    def __init__(self, bot: naoTimesBot) -> None:
        self.bot = bot
        self.logger = logging.getLogger("BotBrain.Ticketing")
        self.db = bot.redisdb

        self._manager: List[naoTixHandler] = []

        self._ticket_queue = asyncio.Queue[TicketForwarder]()
        self._ticket_done_queue = asyncio.Queue[naoTixHandler]()
        self._ticket_start_queue = asyncio.Queue[naoTixHandler]()

        self._ticket_send_task = asyncio.Task(self._ticket_forwarder_task())
        self._ticket_start_task = asyncio.Task(self._ticket_handle_start_task())
        self._ticket_done_task = asyncio.Task(self._ticket_handle_closing_task())

        self._guild: disnake.Guild = None
        self._category: disnake.CategoryChannel = None
        self._log_channel: disnake.TextChannel = None

        self._is_ready = False
        self._dont_run = False
        self._temp_task = self.bot.loop.create_task(self._prepare_ticket_system())

    def cog_unload(self) -> None:
        self._temp_task.cancel()
        self._ticket_done_task.cancel()
        self._ticket_send_task.cancel()
        self._ticket_start_task.cancel()

    async def _prepare_ticket_system(self):
        if self._is_ready:
            return

        if not self.bot.config.ticket:
            return  # exit early

        await self.bot.wait_until_ready()

        self.logger.info("Loading the ticket information data...")
        ticket = self.bot.config.ticket
        if ticket is None:
            self.logger.error("No ticket information data found!")
            self._dont_run = True
            self._is_ready = True
            return
        self.logger.info("Fetching ticket guild...")
        guild = self.bot.get_guild(ticket.srv_id)
        if guild is None:
            self.logger.error("Could not find guild %s", ticket.srv_id)
            self._dont_run = True
            self._is_ready = True
            return

        self._guild = guild
        self.logger.info("Fetching ticket category channel...")
        kategori = guild.get_channel(ticket.id)
        if not isinstance(kategori, disnake.CategoryChannel):
            self.logger.error("Could not find category %s", ticket.id)
            self._dont_run = True
            self._is_ready = True
            return

        self._category = kategori
        self.logger.info("Fetching ticket log channel...")
        log_channel = guild.get_channel(ticket.log_id)
        if not isinstance(log_channel, disnake.TextChannel):
            self.logger.error("Could not find log channel %s", ticket.log_id)
            self._dont_run = True
            self._is_ready = True
            return

        self._log_channel = log_channel

        self.logger.info("Loading tickets...")
        all_tickets = await self.db.getall("nttixv3_*")
        for ticket in all_tickets:
            handler = naoTixHandler.from_dict(ticket)
            self._manager.append(handler)
        self.logger.info(f"Loaded {len(all_tickets)} tickets")
        self._is_ready = True

    async def wait_until_ready(self):
        await self.bot.wait_until_ready()
        while not self._is_ready:
            await asyncio.sleep(0.2)

    def _find_manager(
        self, author: disnake.User = None, channel: disnake.TextChannel = None
    ) -> Tuple[Optional[naoTixHandler], bool]:
        if author is None and channel is None:
            return None, False
        for manager in self._manager:
            if author is not None and manager.is_valid(author.id):
                return manager, False
            elif channel is not None and manager.is_valid(channel.id):
                return manager, True
        return None, False

    async def _update_manager(self, manager: naoTixHandler):
        indx = -1
        for i, m in enumerate(self._manager):
            if m.id == manager.id:
                indx = i
                break
        if indx == -1:
            self._manager.append(manager)
        else:
            self._manager[indx] = manager
        await self.db.set(f"nttixv3_{manager.id}", manager.serialize())

    async def _delete_manager(self, manager: naoTixHandler):
        indx = -1
        for i, m in enumerate(self._manager):
            if m.id == manager.id:
                indx = i
                break
        if indx >= 0:
            del self._manager[indx]
        await self.db.rm(f"nttixv3_{manager.id}")

    async def _actually_forward_message(self, forward: TicketForwarder):
        channel_target: Union[disnake.DMChannel, disnake.TextChannel] = None
        if isinstance(forward.target, naoTixUser):
            self.logger.info(f"Will be sending to user: {forward.target.id}")
            user_target = self.bot.get_user(forward.target.id)
            if user_target is None:
                return
            channel_check = user_target.dm_channel
            if channel_check is None:
                channel_check = await user_target.create_dm()
            channel_target = channel_check
        else:
            self.logger.info(f"Will be sending to channel: {forward.target.id}")
            channel_check = self._guild.get_channel(forward.target.id)
            if not isinstance(channel_check, disnake.TextChannel):
                return
            channel_target = channel_check

        main_msg = forward.message
        timestamp = arrow.get(main_msg.timestamp)
        embed = disnake.Embed(
            title="Pesan diterima", timestamp=timestamp.datetime, color=disnake.Color.dark_orange()
        )
        author = forward.message.author
        cut_name = author.name
        if len(cut_name) >= 250:
            cut_name = cut_name[:238] + "..."
        embed.set_author(name=f"{cut_name}#{author.discriminator}", icon_url=author.avatar)
        embed.description = main_msg.content
        if main_msg.attachments:
            an_image: str = None
            all_attach: List[naoTixAttachment] = []
            for attch in main_msg.attachments:
                if attch.type.startswith("image/") and an_image is None and not attch.is_sticker:
                    an_image = attch.url
                all_attach.append(f"[{attch.filename}]({attch.url})")
            if an_image is not None:
                embed.set_image(url=an_image)
            if all_attach:
                embed.add_field(name="Lampiran", value="\n".join(all_attach))

        embed.set_footer(text="📬 Pesan baru", icon_url=self.bot.user.avatar)
        await channel_target.send(embed=embed)

        raw_receiver = forward.raw_message.channel
        embed_dict = embed.to_dict()
        embed_dict["title"] = "Pesan dikirim"
        embed_dict["color"] = disnake.Color.dark_green().value
        await raw_receiver.send(embed=disnake.Embed.from_dict(embed_dict))

    async def _ticket_forwarder_task(self):
        await self.wait_until_ready()
        if self._dont_run:
            return
        self.logger.info("Starting ticket forwarder task...")
        while True:
            try:
                message = await self._ticket_queue.get()
                try:
                    await self._actually_forward_message(message)
                except Exception as e:
                    self.logger.error(f"Failed to execute ticket-forwarder: {e}", exc_info=e)
                    self.bot.echo_error(e)
                self._ticket_queue.task_done()
            except asyncio.CancelledError:
                break
        self.logger.info("Finished ticket forwarder task...")

    async def _upload_ticket_log(self, ticket: naoTixHandler):
        author = ticket.user
        messages = ticket.messages
        closed_by = ticket.closed_by
        timestamp = ticket.timestamp

        full_context = []
        prepend_context = ["=== Informasi Tiket ==="]
        prepend_context.append(f"Dibuka oleh: {author} ({author.id})")
        prepend_context.append(f"Pada (UNIX): {timestamp}")
        prepend_context.append("=== END OF INFORMATION LINE ===")
        full_context.append(prepend_context)
        if len(messages) < 1:
            full_context.append(["*Tidak ada pesan yang ditukar!*"])
        for pos, message in enumerate(messages, 1):
            content_inner = [f">> Pesan #{pos} <<"]
            content_inner.append(f"Dikirim oleh: {message.author} ({message.author.id})")
            content_inner.append("")
            if message.content:
                content_inner.append(message.content)
            else:
                content_inner.append("*Pesan teks kosong*")
            content_inner.append("")
            content_inner.append("Lampiran File:")
            if message.attachments:
                for n, attch in enumerate(message.attachments, 1):
                    content_inner.append(f"#{n}: {attch.filename} - {attch.url} ({attch.type})")
            else:
                content_inner.append("*Tidak ada lampiran untuk pesan ini*")
            full_context.append(content_inner)
        postpend_context = ["======================================="]
        current_time = int(self.bot.now().timestamp())
        postpend_context.append(f"Tiket ditutup pada: {current_time}")
        postpend_context.append(f"Tiket ditutup oleh: {closed_by} ({closed_by.id})")
        postpend_context.append("========== Akhir pembicaraan ==========")
        full_context.append(postpend_context)

        complete_message = ""
        for ctx in full_context:
            complete_message += "\n".join(ctx) + "\n\n"
        complete_message = complete_message.rstrip()
        current = str(self.bot.now().timestamp())
        filename = f"TicketNaoTimes{current}_{author}_"
        return await self.bot.send_ihateanime(complete_message, filename)

    async def _actually_finish_ticket_task(self, handler: naoTixHandler):
        user = handler.user
        user_data = self.bot.get_user(user.id)
        if user_data is None:
            return
        dm_channel = user_data.dm_channel
        if dm_channel is None:
            dm_channel = await user_data.create_dm()

        channel_data = self._guild.get_channel(handler.channel.id)
        if channel_data is None:
            return

        iha_url, _ = await self._upload_ticket_log(handler)
        current_time = self.bot.now()

        embed = disnake.Embed(
            title="Tiket ditutup",
            colour=disnake.Color.dark_orange(),
            timestamp=current_time.datetime,
        )
        name_cut = user.name
        if len(user.name) >= 250:
            name_cut = user.name[:238] + "..."
        desc_log = "Terima kasih sudah menggunakan fitur ticket kami!\n"
        desc_log += "Anda dapat melihat log pembicaraan di link berikut:"
        desc_log += f"\n{iha_url}"
        embed.description = desc_log
        embed.set_footer(text="📬 Ticket naoTimes", icon_url=self.bot.user.avatar)
        await self._delete_manager(handler)
        await dm_channel.send(embed=embed)
        self.logger.info(f"logged url: {iha_url}")
        desc_log = "Berikut adalah log semua pesan yang dikirim:"
        desc_log += f"\n{iha_url}"
        desc_log += "\n\nLink tersebut valid untuk 2.5 bulan sebelum dihapus selamanya!"
        embed.description = desc_log
        ticket_info = f"Tiket dibuka oleh: {user} ({user.id})\n"
        ticket_info += f"Pada: <t:{handler.timestamp}:F>\n\n"
        ticket_info += f"Ditutup oleh: {handler.closed_by} ({handler.closed_by.id})\n"
        ticket_info += f"Pada: <t:{current_time.int_timestamp}:F>"
        embed.add_field(name="Informasi", value=ticket_info)
        embed.set_footer(text=f"{name_cut}#{user.discriminator}", icon_url=user.avatar)
        await self._log_channel.send(embed=embed)
        await channel_data.delete(reason="Ticket closed")

    async def _ticket_handle_closing_task(self):
        await self.wait_until_ready()
        if self._dont_run:
            return
        self.logger.info("Starting ticket finished task...")
        while True:
            try:
                handler = await self._ticket_done_queue.get()
                self.logger.info("Received ticket finished task...")
                try:
                    await self._actually_finish_ticket_task(handler)
                except Exception as e:
                    self.logger.error(f"Failed to execute ticket-finished: {e}")
                    self.bot.echo_error(e)
                self.logger.info("Ticket-finished are executed!")
                self._ticket_done_queue.task_done()
            except asyncio.CancelledError:
                break
        self.logger.info("Finished ticket finished task...")

    async def _actually_start_ticket_task(self, handler: naoTixHandler):
        find_manager, _ = self._find_manager(handler.user)
        if find_manager is not None:
            return

        text_chan_name = f"📬-tiket-{handler.user.id}"
        text_channel = await self._category.create_text_channel(name=text_chan_name)
        handler.channel = naoTixChannel.from_channel(text_channel)

        user = handler.user
        user_data = self.bot.get_user(user.id)
        if user_data is None:
            return
        dm_channel = user_data.dm_channel
        if dm_channel is None:
            dm_channel = await user_data.create_dm()

        ticket_info = f"Tiket dibuka oleh: {user} ({user.id})"
        ticket_info += f"\nPada: <t:{handler.timestamp}:F>"

        ts_start = arrow.get(handler.timestamp)
        embed = disnake.Embed(
            title="Tiket dibuka!", timestamp=ts_start.datetime, colour=disnake.Color.dark_magenta()
        )
        desc = f"Tiket baru telah dibuka oleh **{user.name}#{user.discriminator}**"
        desc += "\nUntuk menutup ticketnya, cukup ketik `=tutuptiket`"
        desc += f"\nTiket dibuat pada <t:{int(handler.timestamp)}>"
        embed.description = desc
        embed.set_footer(text="📬 Sistem Tiket", icon_url=self._guild.icon)

        await text_channel.send(
            content=f"Tiket baru oleh **{user.name}#{user.discriminator}**",
            embed=embed,
        )
        await dm_channel.send(
            content="Silakan mulai mengetik, pesan anda akan diteruskan otomatis!", embed=embed
        )
        await self._update_manager(handler)

        log_embed = disnake.Embed(
            title="Tiket baru", timestamp=ts_start.datetime, colour=disnake.Colour.dark_green()
        )
        log_embed.description = f"\nGunakan kanal <#{text_channel.id}> untuk berbicara dengan user."
        name_cut = user.name
        if len(user.name) >= 250:
            name_cut = user.name[:238] + "..."
        log_embed.add_field(name="Informasi", value=ticket_info)
        log_embed.set_footer(text=f"{name_cut}#{user.discriminator}", icon_url=user.avatar)
        await self._log_channel.send(embed=log_embed)

    async def _ticket_handle_start_task(self):
        await self.wait_until_ready()
        if self._dont_run:
            return
        self.logger.info("Starting ticket start task...")
        while True:
            try:
                handler = await self._ticket_start_queue.get()
                self.logger.info("Received ticket start task...")
                try:
                    await self._actually_start_ticket_task(handler)
                except Exception as e:
                    self.logger.error(f"Failed to execute ticket-start: {e}")
                    self.bot.echo_error(e)
                self.logger.info("ticket-start are executed!")
                self._ticket_start_queue.task_done()
            except asyncio.CancelledError:
                break
        self.logger.info("Finished ticket start task...")

    def _is_bot_prefix(self, context: disnake.Message):
        pre = self.bot.prefixes(context)
        if context.clean_content.startswith(pre):
            return True
        return False

    @commands.Cog.listener("on_message")
    async def _ticket_register_message(self, message: disnake.Message):
        author = message.author
        if author.bot:
            return
        manager, _ = self._find_manager(author, message.channel)
        if manager is None:
            return
        if manager.is_on_hold:
            return

        is_initiator = author.id == manager.user.id
        clean_content = message.clean_content
        lower_content = clean_content.lower()
        if self._is_bot_prefix(message):
            return
        if lower_content.startswith("=tutuptiket"):
            closed_by = naoTixUser.from_user(author)
            manager.set_closed(closed_by)
            await self._update_manager(manager)
            await message.channel.send(content="Menutup tiket...")
            await self._ticket_done_queue.put(manager)
            return
        valid_channel = [manager.channel.id, manager.user.id]
        if is_initiator:
            if message.channel.id not in valid_channel and not isinstance(message.channel, disnake.DMChannel):
                self.logger.warning("Received message from initiator, but it's not from DMChannel!")
                return
        if len(clean_content) >= 2000:
            await message.channel.send(content="Pesan anda terlalu panjang, mohon dikurangi!")
            return

        parsed_message = naoTixMessage.from_message(message)
        if message.channel.id == manager.channel.id:
            channel_target = manager.user
        else:
            channel_target = manager.channel

        self.logger.info(f"Will be forwarding to {channel_target}")
        manager.add_message(parsed_message)
        await self._update_manager(manager)
        await self._ticket_queue.put(TicketForwarder(parsed_message, channel_target, message))

    @commands.command(name="ticket", aliases=["tiket"])
    @commands.dm_only()
    async def _bb_ticket(self, ctx: naoTimesContext):
        author = ctx.author
        if self.bot.config.ticket is None:
            return await ctx.send("Maaf, owner bot tidak mengaktifkan fitur ticketing.")

        existing_ticket = self._find_manager(author.id)
        if existing_ticket is None:
            return await ctx.send("Masih ada tiket yang berlangsung, silakan hentikan terlebih dahulu.")

        user_dm = author.dm_channel
        if user_dm is None:
            user_dm = await author.create_dm()

        is_confirm = await ctx.confirm("Apakah anda ingin membuka tiket dengan Owner Bot?", True)
        if not is_confirm:
            return await ctx.send("Dibatalkan")

        await ctx.send("Membuka tiket baru...")
        startup = naoTixHandler(naoTixUser.from_user(author), None, [])
        await self._ticket_start_queue.put(startup)

    @commands.command(name="enableticket")
    @commands.guild_only()
    @commands.is_owner()
    async def _bb_ticket_enablefeature(self, ctx: naoTimesContext):
        if self.bot.config.ticket is not None:
            return await ctx.send("Fitur ticketing sudah aktif, mohon atur manual via config.json")

        wait_channel = await ctx.wait_content(
            "Mohon masukan ID channel category...", delete_prompt=True, delete_answer=True
        )
        if not wait_channel:
            return await ctx.send("Dibatalkan")

        if not wait_channel.isdigit():
            return await ctx.send("ID kategori bukanlah angka!")

        category: disnake.CategoryChannel = self.bot.get_channel(int(wait_channel))
        if not isinstance(category, disnake.CategoryChannel):
            return await ctx.send("ID yang dimasukan bukanlah kanal kategori!")

        log_channel = await category.create_text_channel(
            name="ticket-log", reason="Log channel for ticketing data"
        )
        guild_id: int = ctx.guild.id

        ticket_info = naoTimesTicketConfig(category.id, guild_id, log_channel.id)
        self.bot.config.update_config("ticket", ticket_info.serialize())
        await self.bot.save_config()
        await ctx.send("Fitur ticketing berhasil diaktifkan.")


def setup(bot: naoTimesBot):
    bot.add_cog(BotBrainTicketing(bot))
