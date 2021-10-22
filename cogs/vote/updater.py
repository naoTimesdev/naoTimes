import asyncio
import logging
import random

import discord
from discord.ext import commands

from naotimes.bot import naoTimesBot
from naotimes.socket import ntevent

from .listener import VoteData, VoteType


class VoteEmbedUpdater(commands.Cog):
    def __init__(self, bot: naoTimesBot):
        self.bot = bot
        self.logger = logging.getLogger("VoteSystem.Updater")

        self._update_queue = asyncio.Queue[VoteData]()
        self._update_task: asyncio.Task = asyncio.Task(self._loop_vote_update_task())
        self._vote_over_queue = asyncio.Queue[VoteData]()
        self._vote_over_task: asyncio.Task = asyncio.Task(self._loop_vote_over_task())

    def cog_unload(self):
        self._update_task.cancel()
        self._vote_over_task.cancel()

    @ntevent("vote updated")
    async def on_vote_updated(self, vote_data: VoteData):
        self.logger.debug(f"Received update event, {vote_data.id}")
        await self._update_queue.put(vote_data)

    @ntevent("vote finished")
    async def on_vote_finished(self, vote_data: VoteData):
        self.logger.debug(f"Received finished event, {vote_data.id}")
        await self._vote_over_queue.put(vote_data)

    async def _actually_update_embed(self, vote_data: VoteData):
        channel: discord.TextChannel = self.bot.get_channel(vote_data.metadata.channel)
        if channel is None:
            self.logger.warning(f"{vote_data.id}: missing channel?")
            return
        try:
            message = await channel.fetch_message(vote_data.metadata.message)
        except discord.NotFound:
            self.logger.warning(f"{vote_data.id}: missing message?")
            await self._on_vote_finished(vote_data)
            return
        embed: discord.Embed = discord.Embed.from_dict(message.embeds[0].to_dict())
        first_choice = vote_data.choices[0]
        if vote_data.type == VoteType.USER:
            embed.set_field_at(
                0,
                name=f"Jumlah vote (Dibutuhkan: {first_choice.limit})",
                value=f"{first_choice.tally} votes",
            )
        elif vote_data.type == VoteType.YESNO:
            second_choice = vote_data.choices[1]
            embed.set_field_at(0, name="✅ Ya", value=f"**Total**: {first_choice.tally}", inline=False)
            embed.set_field_at(1, name="❌ Tidak", value=f"**Total**: {second_choice.tally}", inline=False)
        elif vote_data.type == VoteType.GIVEAWAY:
            embed.set_field_at(0, name="Partisipasi", value=f"{first_choice.tally} partisipan")
        else:
            for n, choice in enumerate(vote_data.choices):
                embed.set_field_at(
                    n, name=f"{choice.emote} {choice.name}", value=f"**Total**: {choice.tally}", inline=False
                )
        if vote_data.type == VoteType.GIVEAWAY:
            embed.set_footer(text="Giveaway sedang berlangsung")
        else:
            embed.set_footer(text="Voting sedang berlangsung")
        await message.edit(embed=embed)

    async def _actually_handle_kickban(
        self, guild: discord.Guild, member: discord.Member, is_ban: bool = False
    ):
        try:
            if is_ban:
                self.logger.info(f"{guild.name}: vote kicking {member.display_name} from server")
                await guild.ban(
                    member, reason="Banned from voting process by multiple people", delete_message_days=0
                )
            else:
                self.logger.info(f"{guild.name}: vote banning {member.display_name} from server")
                await guild.kick(member, reason="Kicked from voting process by multiple people")
        except discord.Forbidden:
            self.logger.error(f"{member}: cannot kick/ban because missing perms.")
        except discord.HTTPException as dehttp:
            self.logger.error(f"{member}: cannot kick/ban because http failures.")
            self.bot.echo_error(dehttp)

    async def _actually_handle_over(self, vote_data: VoteData):
        self.logger.info(f"Handling over, {vote_data.id}")
        final_answer = vote_data.get_winner()
        channel: discord.TextChannel = self.bot.get_channel(vote_data.metadata.channel)
        if channel is None:
            self.logger.warning(f"{vote_data.id}: missing channel?")
            return
        try:
            message = await channel.fetch_message(vote_data.metadata.message)
            embed: discord.Embed = discord.Embed.from_dict(message.embeds[0].to_dict())
            context_txt = None
            if vote_data.type == VoteType.GIVEAWAY:
                embed.set_footer(text="🎉 Giveaway selesai!")
                context_txt = "🎉 **Giveaway selesai** 🎉"
            else:
                embed.set_footer(text="Voting Selesai!")
            await message.edit(content=context_txt, embed=embed)
        except discord.NotFound:
            self.logger.warning(f"{vote_data.id}: missing message?")

        if vote_data.type == VoteType.USER:
            is_ban = "ban" in final_answer.data.name.lower()
            tally = final_answer.data.tally
            uuid_target = final_answer.data.id
            member_name = channel.guild.get_member(uuid_target)
            if member_name is None:
                self.logger.warning(f"{vote_data.id}: for some reason, the member is already gone?")
                return
            if final_answer.data.emote == "✅":
                self.logger.info(f"{vote_data.id}: limit reached, people voted for yes...")
                await self._actually_handle_kickban(channel.guild, member_name, is_ban)
                await channel.send(content=f"Limit voting tercapai, selamat tinggal **{member_name}** o7")
            elif final_answer.data.emote == "❌" and not final_answer.is_timeout:
                self.logger.info(f"{vote_data.id}: limit reached, people voted for no...")
                await channel.send(
                    content=f"Limit voting tercapai, s**{member_name}** aman untuk sekarang..."
                )
            else:
                self.logger.info(f"{vote_data.id}: Timeout reached, defaulting to no")
                await channel.send(content=f"Waktu voting selesai, s**{member_name}** aman untuk sekarang...")
        elif vote_data.type == VoteType.GIVEAWAY:
            self.logger.info(f"{vote_data.id}: Deciding on giveaway winner...")
            give_item = vote_data.metadata.title
            if final_answer.data.tally < 1:
                await channel.send(f"Giveaway **__{give_item}__** selesai! Tetapi tidak ada yang join..")
            else:
                joined_member = final_answer.data.voter[:]
                winner_member: discord.Member = None
                while True:
                    if len(joined_member) < 1:
                        break
                    for _ in range(3):
                        random.shuffle(joined_member)
                    select_winner = joined_member[0]
                    if not hasattr(channel, "guild"):
                        self.logger.info(f"{vote_data.id}: There's no guild attributes for this, ignoring...")
                        break
                    if channel.guild is None:
                        self.logger.warning(f"{vote_data.id}: This guild attributes is empty, ignoring...")
                        break
                    winner_member = channel.guild.get_member(select_winner)
                    if winner_member is not None:
                        break
                    joined_member.remove(select_winner)
                self.logger.info(f"{vote_data.id}: winner decided: {winner_member}")
                if winner_member is None:
                    await channel.send(
                        content=f"Giveaway **__{give_item}__** selesai! Tetapi bot tidak "
                        "bisa memilih pemenang..."
                    )
                else:
                    win_msg = f"Giveaway **__{give_item}__** selesai!\n"
                    win_msg += f"Selamat kepada {winner_member.mention}\n"
                    win_msg += f"<{message.jump_url}>"
                    await channel.send(win_msg)
        elif vote_data.type == VoteType.YESNO:
            topik = vote_data.metadata.title
            base_msg = f"Waktu voting habis, Hasil akhir dari **{topik}** adalah... "
            if final_answer.is_tied:
                base_msg += "**Seri!**"
            elif final_answer.data.emote == "✅":
                base_msg += "**Ya!**"
            elif final_answer.data.emote == "❌":
                base_msg += "**Tidak!**"
            else:
                base_msg += "**Tidak diketahui!**"
            await channel.send(content=base_msg)
        else:
            topik = vote_data.metadata.title
            tally = final_answer.data.tally
            name = final_answer.data.name
            emote = final_answer.data.emote
            if tally > 0:
                await channel.send(
                    content=f"Waktu voting habis, Hasil akhir dari **{topik}** adalah... "
                    f"{emote} **{name}** `{tally} votes`"
                )
            else:
                await channel.send(
                    content=f"Waktu voting habis, tidak ada yang mengikuti voting **{topik}** ..."
                )

    async def _loop_vote_over_task(self):
        self.logger.info("Starting...")
        while True:
            try:
                vote_data = await self._vote_over_queue.get()
                try:
                    self.logger.info(f"Trying to finish: {vote_data.id}")
                    await self._actually_handle_over(vote_data)
                    self.logger.info(f"Finished: {vote_data.id}")
                except Exception as e:
                    self.logger.error(f"Failed to finish {vote_data.id}", exc_info=e)
                self._vote_over_queue.task_done()
            except asyncio.CancelledError:
                break
        self.logger.info("Got cancelled request, stopping...")

    async def _loop_vote_update_task(self):
        self.logger.info("Starting...")
        while True:
            try:
                vote_data = await self._update_queue.get()
                try:
                    self.logger.info(f"Trying to update: {vote_data.id}")
                    await self._actually_update_embed(vote_data)
                    self.logger.info(f"Updated: {vote_data.id}")
                except Exception as e:
                    self.logger.error(f"Failed to update {vote_data.id}", exc_info=e)
                self._update_queue.task_done()
            except asyncio.CancelledError:
                break
        self.logger.info("Got cancelled request, stopping...")


def setup(bot: naoTimesBot):
    bot.add_cog(VoteEmbedUpdater(bot))
