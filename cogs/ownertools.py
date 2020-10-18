import asyncio
import logging
import glob
import os
from datetime import datetime, timezone
from typing import Dict, List, Union

import discord
from discord.ext import commands, tasks
from nthelper.bot import naoTimesBot
from nthelper.utils import confirmation_dialog, generate_custom_code, read_files, write_files


class ForwarderData:
    def __init__(
        self,
        message: str,
        attachments: List[discord.Attachment],
        target_id: int,
        sender: discord.abc.User,
        is_user: bool,
        is_deletion: bool = False,
    ):
        self.msg = message
        self.attachments = attachments
        self.target = target_id
        self.sender = sender
        self.is_user = is_user
        self.is_del = is_deletion


class OwnerToolbox(commands.Cog):
    """A toolbox of commands for Bot Owner."""

    def __init__(self, bot: naoTimesBot):
        self.bot = bot
        self.logger = logging.getLogger("cogs.ownertools.OwnerToolbox")
        self._ticket_data: Dict[Union[str, int], Dict[str, Union[str, int]]] = {}

        self._precheck_existing_ticket.start()
        self._forwarder_queue: asyncio.Queue = asyncio.Queue()
        self._forwarder_task: asyncio.Task = asyncio.Task(self._message_forwarder_handler())

    def cog_unload(self):
        self.logger.info("Cancelling all tasks...")
        self._forwarder_task.cancel()

    @tasks.loop(seconds=1, count=1)
    async def _precheck_existing_ticket(self):
        self.logger.info("checking preexisiting ticket data...")
        search_path = os.path.join(self.bot.fcwd, "ticketing")
        if not os.path.isdir(search_path):
            os.makedirs(search_path)
            self.logger.info("Folder deosn't even exist yet, returning...")
            return
        search_path = os.path.join(search_path, "*.ticket")
        self.logger.info("searching for existing data...")
        ticket_datas = glob.glob(search_path)
        if not ticket_datas:
            self.logger.info("no exisiting data, exiting...")
            return
        for path in ticket_datas:
            tix_data = await read_files(path)
            self._ticket_data[tix_data["id"]] = tix_data
            self.logger.info(f"appending {tix_data['id']}...")
            self._ticket_data[tix_data["user_id"]] = tix_data

    async def do_fansubrss_premium(self, server_id, disable_it=False):
        full_path = os.path.join(self.bot.fcwd, "fansubrss_data", f"{server_id}.fsrss")
        rss_metadata = await read_files(full_path)
        if not rss_metadata:
            return False, "Server belum mendaftarkan FansubRSS"
        if not disable_it:
            self.logger.info(f"{server_id}: enabling premium feature for this server...")
            rss_metadata["premium"] = True
            msg_to_send = f"💳 | Fitur premium FansubRSS server `{server_id}` telah diaktifkan!"
        elif disable_it:
            self.logger.info(f"{server_id}: disabling premium feature for this server...")
            rss_metadata["premium"] = False
            msg_to_send = f"🕸️ | Fitur premium FansubRSS server `{server_id}` telah dinonaktifkan!"
        return True, msg_to_send

    async def _message_forwarder_handler(self):
        ticket_logger = self.bot.botconf["ticketing"]["log_id"]
        logger_channel: discord.TextChannel = self.bot.get_channel(ticket_logger)
        self.logger.info("initialized forwarder handler.")
        while True:
            try:
                forward_data: ForwarderData = await self._forwarder_queue.get()
                self.logger.info(f"ForwarderGet: {forward_data.target}")
                tix_data = self._ticket_data[forward_data.target]
                if forward_data.is_del:
                    self.logger.info(f"ForwarderClosing: {forward_data.target}")
                    user_channel: discord.DMChannel = self.bot.get_channel(forward_data.target)
                    chat_channel: discord.TextChannel = self.bot.get_channel(tix_data["id"])
                    await user_channel.send(content="Tiket ditutup, semoga dapat membantu.")
                    embed = discord.Embed(
                        title="Tiket Ditutup!", color=0xC05959, timestamp=datetime.now(tz=timezone.utc)
                    )
                    embed.add_field(
                        name="Peminta",
                        value=f"{user_channel.recipient.name}#{user_channel.recipient.discriminator}"
                        f"\n[{user_channel.recipient.id}]",
                        inline=False,
                    )
                    embed.set_footer(text=tix_data["end_sequence"] + " | Ended.")
                    self.logger.info(f"ForwarderClose: {forward_data.target}")
                    await logger_channel.send(embed=embed)
                    await chat_channel.delete(reason="Ticket closed.")
                    del self._ticket_data[user_channel.id]
                    del self._ticket_data[chat_channel.id]
                    ticket_file = os.path.join(
                        self.bot.fcwd, "ticketing", f"{user_channel.recipient.id}.ticket"
                    )
                    os.remove(ticket_file)
                else:
                    self.logger.info(f"ForwarderSending: {forward_data.target}")
                    target_channel: Union[discord.DMChannel, discord.TextChannel]
                    if forward_data.is_user:
                        target_channel = self.bot.get_channel(forward_data.target)
                    else:
                        target_channel = self.bot.get_channel(forward_data.target)
                    attachments_files = []
                    for attach in forward_data.attachments:
                        file_data = await attach.to_file()
                        attachments_files.append(file_data)
                    sender_data = forward_data.sender
                    fwd_embed = discord.Embed(
                        title="Pesan Baru!", color=0x6879BB, timestamp=datetime.now(tz=timezone.utc)
                    )
                    fwd_embed.description = forward_data.msg
                    fwd_embed.set_author(
                        name=f"{sender_data.name}#{sender_data.discriminator}",
                        icon_url=str(sender_data.avatar_url),
                    )
                    fwd_embed.set_footer(text=tix_data["end_sequence"])
                    self.logger.info(f"ForwarderSend: {forward_data.target}")
                    await target_channel.send(embed=fwd_embed, files=attachments_files)
                self._forwarder_queue.task_done()
            except asyncio.CancelledError:
                return

    @commands.Cog.listener(name="on_message")
    async def ticket_forwarder(self, message: discord.Message):
        if message.author.id == self.bot.user.id:
            return
        if message.channel.id not in self._ticket_data:
            return
        if message.content.startswith(self.bot.prefix):
            return
        ticket_data = self._ticket_data[message.channel.id]
        is_user = False
        target_id = ticket_data["user_id"]
        if message.channel.id == ticket_data["id"]:
            is_user = False
            target_id = ticket_data["user_id"]
        elif message.channel.id == ticket_data["user_id"]:
            is_user = True
            target_id = ticket_data["id"]
        if message.content == ticket_data["end_sequence"]:
            self.logger.info("deletion...")
            await self._forwarder_queue.put(
                ForwarderData(
                    "Tiket ditutup.",
                    [],
                    ticket_data["user_id"],  # type: ignore
                    message.author,
                    is_user,
                    True,
                )
            )
            return

        await self._forwarder_queue.put(
            ForwarderData(
                message.content, message.attachments, target_id, message.author, is_user  # type: ignore
            )
        )

    @commands.command()
    @commands.is_owner()
    async def errorlog(self, ctx, channel_id: int):
        channel_data = self.bot.get_channel(channel_id)
        if channel_data is None:
            return await ctx.send("Tidak dapat menemukan kanal tersebut.")

        self.bot.error_logger = channel_id
        self.bot.botconf["error_logger"] = channel_id
        await write_files(self.bot.botconf, os.path.join(self.bot.fcwd, "config.json"))
        await ctx.send(f"Error log diatur ke: <#{channel_id}>")

    @commands.command()
    @commands.is_owner()
    async def test_error(self, ctx):
        raise ValueError("This is a test error initiated by bot owner.")

    @commands.command()
    @commands.is_owner()
    async def premium_code(self, ctx, command_name: str, server_id: int):
        command_sets = ["fansubrss", "rss"]
        if command_name not in command_sets:
            return await ctx.send("Tidak dapat menemukan fitur premium tersebut.")
        server_data = self.bot.get_guild(server_id)
        if server_data is None:
            return await ctx.send("Tidak dapat menemukan peladen tersebut.")

        random_code = generate_custom_code(24, True, True)
        save_path = os.path.join(self.bot.fcwd, "premium_code")
        if not os.path.isdir(save_path):
            os.mkdir(save_path)
        await write_files({"id": server_id, "cmd": command_name}, os.path.join(save_path, random_code))
        await ctx.send("Berhasil membuat premium code, silakan berikan code ini ke user.")

    @commands.command()
    @commands.is_owner()
    async def aktivasi_fitur(self, ctx, command_name: str, server_id: int):
        command_sets = ["fansubrss", "rss", "ticket", "tiket"]
        if command_name not in command_sets:
            return await ctx.send("Tidak dapat menemukan fitur premium tersebut.")

        res = False
        msg = "Gagal melakukan perubahan."
        if command_name in ["fansubrss", "rss"]:
            res, msg = await self.do_fansubrss_premium(server_id, False)
        if command_name in ["ticket", "tiket"]:
            channel_data: discord.TextChannel = self.bot.get_channel(server_id)
            if channel_data is None:
                return await ctx.send("Tidak dapat menemukan kanal tersebut.")
            category_data: discord.CategoryChannel = channel_data.category
            tserver_id = channel_data.guild.id
            self.bot.botconf["ticketing"] = {
                "id": category_data.id,
                "srv_id": tserver_id,
                "log_id": server_id,
            }
            await write_files(self.bot.botconf, os.path.join(self.bot.fcwd, "config.json"))
            res = True
            msg = f"Ticket log diatur ke: <#{server_id}>"

        if res:
            await ctx.send(msg)
            return await ctx.send("Mohon reload ulang command/cogs agar perubahan tersimpan.")
        await ctx.send(msg)

    @commands.command()
    @commands.is_owner()
    async def deaktivasi_fitur(self, ctx, command_name: str, server_id: int):
        command_sets = ["fansubrss", "rss"]
        if command_name not in command_sets:
            return await ctx.send("Tidak dapat menemukan fitur premium tersebut.")

        if command_name in ["fansubrss", "rss"]:
            res, msg = await self.do_fansubrss_premium(server_id, True)

        if res:
            await ctx.send(msg)
            return await ctx.send("Mohon reload ulang command/cogs agar perubahan tersimpan.")
        await ctx.send(msg)

    @commands.command(aliases=["tiket"])
    async def ticket(self, ctx):
        if isinstance(ctx.message.channel, (discord.TextChannel, discord.GroupChannel)):
            return await ctx.send("Mohon jalankan perintah ini di DM Bot.")
        if "ticketing" not in self.bot.botconf:
            return await ctx.send("Maaf, owner bot tidak mengaktifkan fitur ticketing.")
        do_ticket = await confirmation_dialog(self.bot, ctx, "Apakah anda yakin ingin membuat ticket baru?")
        if not do_ticket:
            return await ctx.send("Dibatalkan.")
        ticketing_folder = os.path.join(self.bot.fcwd, "ticketing")
        if not os.path.isdir(ticketing_folder):
            os.makedirs(ticketing_folder)
        ticket_file = os.path.join(ticketing_folder, f"{ctx.message.author.id}.ticket")
        if os.path.isfile(ticket_file):
            return await ctx.send("Masih ada tiket yang berlangsung, silakan hentikan terlebih dahulu.")
        user_dm = ctx.message.author.dm_channel
        if user_dm is None:
            user_dm = await ctx.message.author.create_dm()
        ending_code = generate_custom_code()
        ticket_logging: discord.TextChannel = self.bot.get_channel(self.bot.botconf["ticketing"]["log_id"])
        ticket_category: discord.CategoryChannel = self.bot.get_channel(self.bot.botconf["ticketing"]["id"])
        ticket_channel: discord.TextChannel = await ticket_category.create_text_channel(
            name=f"ticket-{ctx.message.author.id}",
            reason=f"New Ticket Opened by {ctx.message.author.name}",
            topic=f"🎫👤 Tiket user **{ctx.message.author.name}#{ctx.message.author.discriminator}** | "
            f"Tutup dengan **close!{ending_code}**\n"
            "🤖 Kanal ini diatur oleh Bot, biarkan bot yang mengontrol penerusan pesan.",
        )
        ticket_data = {
            "id": ticket_channel.id,
            "user_id": user_dm.id,
            "end_sequence": f"close!{ending_code}",
        }
        self._ticket_data[user_dm.id] = ticket_data
        self._ticket_data[ticket_channel.id] = ticket_data
        await write_files(ticket_data, ticket_file)
        await ctx.send(
            "Ticket telah dibuka, silakan mulai chat di sini.\n"
            f"Untuk menutup tiket, ketik: `close!{ending_code}`\n"
            f"Pesan apapun yang diawali dengan `{self.bot.prefix}` (prefix bot) "
            "akan diabaikan dan tidak akan diteruskan."
        )
        embed = discord.Embed(title="Tiket Baru!", color=0x5EC059, timestamp=datetime.now(tz=timezone.utc))
        embed.add_field(
            name="Peminta",
            value=f"{ctx.message.author.name}#{ctx.message.author.discriminator}\n[{ctx.message.author.id}]",
            inline=False,
        )
        embed.add_field(name="Kanal", value=f"<#{ticket_channel.id}>", inline=False)
        embed.set_footer(text=f"close!{ending_code}")
        await ticket_logging.send(embed=embed)

    @ticket.error
    async def ticket_cmd_error(self, error, ctx):
        if isinstance(error, commands.PrivateMessageOnly):
            return await ctx.send("Gunakan perintah ini di DM Bot.")

    @commands.command()
    @commands.is_owner()
    async def check_all_cmds(self, ctx):
        cmds: List[Union[commands.Command, commands.Group]] = self.bot.commands
        disallowed_stuff = []
        for cmd in cmds:
            if cmd.checks:
                for checker in cmd.checks:
                    fn_primitive_name = checker.__str__()
                    if "is_owner" in fn_primitive_name:
                        disallowed_stuff.append(cmd)

    @commands.command()
    @commands.is_owner()
    async def cache_members(self, ctx):
        try:
            await ctx.message.guild.chunk()
        except AttributeError:
            return await ctx.send("Tidak menggunakan discord.py versi 1.5.0")
        except discord.ClientException:
            return await ctx.send("Intent Members tidak diaktifkan.")
        await ctx.send("Sukses caching member server ini.")

    @commands.command()
    @commands.is_owner()
    async def botlog(self, ctx):
        self.logger.info("enabling bot logging...")

    @commands.command()
    @commands.is_owner()
    async def book_channel(self, ctx, channel_id: int, *, temp_msg=""):
        channel_data: discord.TextChannel = self.bot.get_channel(channel_id)
        if not channel_data:
            return await ctx.send("Tidak dapat menemukan kanal tersebut.")
        await channel_data.send(content="*Booked for later usage*" if not temp_msg else temp_msg)


def setup(bot: naoTimesBot):
    bot.add_cog(OwnerToolbox(bot))
