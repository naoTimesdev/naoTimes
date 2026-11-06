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

    async def cog_unload(self):
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
        channel = self.bot.get_channel(vote_data.metadata.channel)
        if not isinstance(channel, discord.TextChannel):
            self.logger.warning(f"{vote_data.id}: missing channel?")
            return
        i18n = self.bot.i18n_for(channel.guild, "vote")
        try:
            message = await channel.fetch_message(vote_data.metadata.message)
        except discord.NotFound:
            self.logger.warning(f"{vote_data.id}: missing message?")
            await self.on_vote_finished(vote_data)
            return
        embed: discord.Embed = discord.Embed.from_dict(message.embeds[0].to_dict())
        first_choice = vote_data.choices[0]
        if vote_data.type == VoteType.USER:
            embed.set_field_at(
                0,
                name=i18n.t("user_action.embed_field", limit=first_choice.limit),
                value=i18n.t("shared.votes", count=first_choice.tally),
            )
        elif vote_data.type == VoteType.YESNO:
            second_choice = vote_data.choices[1]
            embed.set_field_at(
                0, name=i18n.t("shared.field_yes"), value=i18n.t("shared.total", count=first_choice.tally), inline=False
            )
            embed.set_field_at(
                1, name=i18n.t("shared.field_no"), value=i18n.t("shared.total", count=second_choice.tally), inline=False
            )
        elif vote_data.type == VoteType.GIVEAWAY:
            embed.set_field_at(
                0,
                name=i18n.t("giveaway.field_participation"),
                value=i18n.t("giveaway.field_participation_value", count=first_choice.tally),
            )
        else:
            for n, choice in enumerate(vote_data.choices):
                embed.set_field_at(
                    n,
                    name=f"{choice.emote} {choice.name}",
                    value=i18n.t("shared.total", count=choice.tally),
                    inline=False,
                )
        if vote_data.type == VoteType.GIVEAWAY:
            embed.set_footer(text=i18n.t("shared.footer_giveaway_ongoing"))
        else:
            embed.set_footer(text=i18n.t("shared.footer_ongoing"))
        await message.edit(embed=embed)

    @staticmethod
    async def _resolve_member(guild: discord.Guild, member_id: int) -> discord.Member | None:
        """Get a member from cache, falling back to the API (no members intent needed)."""
        member = guild.get_member(member_id)
        if member is not None:
            return member
        try:
            return await guild.fetch_member(member_id)
        except (discord.NotFound, discord.Forbidden, discord.HTTPException):
            return None

    async def _actually_handle_kickban(self, guild: discord.Guild, member: discord.Member, is_ban: bool = False):
        try:
            if is_ban:
                self.logger.info(f"{guild.name}: vote kicking {member.display_name} from server")
                await guild.ban(member, reason="Banned from voting process by multiple people", delete_message_days=0)
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
        channel = self.bot.get_channel(vote_data.metadata.channel)
        if not isinstance(channel, discord.TextChannel):
            self.logger.warning(f"{vote_data.id}: missing channel?")
            return
        i18n = self.bot.i18n_for(channel.guild, "vote")
        try:
            message = await channel.fetch_message(vote_data.metadata.message)
            embed: discord.Embed = discord.Embed.from_dict(message.embeds[0].to_dict())
            context_txt = None
            if vote_data.type == VoteType.GIVEAWAY:
                embed.set_footer(text=i18n.t("giveaway.finished_footer"))
                context_txt = i18n.t("giveaway.finished_content")
            else:
                embed.set_footer(text=i18n.t("voting.finished_footer"))
            await message.edit(content=context_txt, embed=embed)
        except discord.NotFound:
            self.logger.warning(f"{vote_data.id}: missing message?")
            return

        if vote_data.type == VoteType.USER:
            is_ban = "ban" in str(final_answer.data.name).lower()
            tally = final_answer.data.tally
            uuid_target = final_answer.data.id
            try:
                member_id = int(uuid_target)
            except (TypeError, ValueError):
                self.logger.error("Vote target ID is invalid: %r", uuid_target)
                return
            member_name = await self._resolve_member(channel.guild, member_id)
            if member_name is None:
                self.logger.warning(f"{vote_data.id}: for some reason, the member is already gone?")
                return
            if final_answer.data.emote == "✅":
                self.logger.info(f"{vote_data.id}: limit reached, people voted for yes...")
                await self._actually_handle_kickban(channel.guild, member_name, is_ban)
                await channel.send(content=i18n.t("user_action.limit_yes", member=member_name))
            elif final_answer.data.emote == "❌" and not final_answer.is_timeout:
                self.logger.info(f"{vote_data.id}: limit reached, people voted for no...")
                await channel.send(content=i18n.t("user_action.limit_no", member=member_name))
            else:
                self.logger.info(f"{vote_data.id}: Timeout reached, defaulting to no")
                await channel.send(content=i18n.t("user_action.timeout_no", member=member_name))
        elif vote_data.type == VoteType.GIVEAWAY:
            self.logger.info(f"{vote_data.id}: Deciding on giveaway winner...")
            give_item = vote_data.metadata.title
            if final_answer.data.tally < 1:
                await channel.send(i18n.t("giveaway.no_join", item=give_item))
            else:
                joined_member = final_answer.data.voter[:]
                winner_member: discord.Member | None = None
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
                    winner_member = await self._resolve_member(channel.guild, select_winner)
                    if winner_member is not None:
                        break
                    joined_member.remove(select_winner)
                self.logger.info(f"{vote_data.id}: winner decided: {winner_member}")
                if winner_member is None:
                    await channel.send(i18n.t("giveaway.winner_failed", item=give_item))
                else:
                    await channel.send(
                        i18n.t(
                            "giveaway.winner",
                            item=give_item,
                            winner=winner_member.mention,
                            jump_url=f"<{message.jump_url}>",
                        )
                    )
        elif vote_data.type == VoteType.YESNO:
            topik = vote_data.metadata.title
            if final_answer.is_tied:
                verdict = i18n.t("voting.verdict_tied")
            elif final_answer.data.emote == "✅":
                verdict = i18n.t("voting.verdict_yes")
            elif final_answer.data.emote == "❌":
                verdict = i18n.t("voting.verdict_no")
            else:
                verdict = i18n.t("voting.verdict_unknown")
            await channel.send(content=i18n.t("voting.yesno_result", topic=topik, verdict=verdict))
        else:
            topik = vote_data.metadata.title
            tally = final_answer.data.tally
            name = final_answer.data.name
            emote = final_answer.data.emote
            if tally > 0:
                await channel.send(
                    content=i18n.t("voting.multiple_result", topic=topik, emote=emote, name=name, count=tally)
                )
            else:
                await channel.send(content=i18n.t("voting.multiple_empty", topic=topik))

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


async def setup(bot: naoTimesBot):
    await bot.add_cog(VoteEmbedUpdater(bot))
