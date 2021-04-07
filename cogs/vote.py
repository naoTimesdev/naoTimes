import asyncio
import logging
import os
import random
from copy import deepcopy
from datetime import datetime, timezone
from typing import List, Union

import discord
from discord.ext import commands, tasks

from nthelper.bot import naoTimesBot
from nthelper.cmd_args import Arguments, CommandArgParse
from nthelper.timeparse import TimeString, TimeStringParseError
from nthelper.votebackend import VoteWatcher, VotingData, VotingKickBan

reactions_num = ["1⃣", "2⃣", "3⃣", "4⃣", "5⃣", "6⃣", "7⃣", "8⃣", "9⃣", "🔟"]
res2num = dict(zip(reactions_num, [0, 1, 2, 3, 4, 5, 6, 7, 8, 9]))
num2res = dict(zip([0, 1, 2, 3, 4, 5, 6, 7, 8, 9], reactions_num))

kickban_limit_args = ["--limit", "-l"]
kickban_limit_kwargs = {
    "required": False,
    "default": 5,
    "dest": "batas",
    "action": "store",
    "help": "Limit user untuk melaksanakan kick/ban (minimal 5 orang)",
}
kickban_timer_args = ["--timer", "-t"]
kickban_timer_kwargs = {
    "required": False,
    "default": "1m",
    "dest": "waktu",
    "action": "store",
    "help": "Waktu sebelum voting ditutup (Format time string seperti: "
    "'30m 30s' untuk 30 menit 30 detik, minimal 30 detik, default 1 menit)\n"
    "Referensi time string: https://naoti.me/docs/perintah/vote#time-string-format",
}
vote_opsi_args = ["--opsi", "-O"]
vote_opsi_kwargs = {
    "dest": "opsi",
    "action": "append",
    "help": "Opsi voting (minimal 2, batas 10)",
}
vote_tipe_yn_args = ["--satu-pilihan", "-S"]
vote_tipe_yn_kwargs = {
    "dest": "use_yn",
    "action": "store_true",
    "help": "Gunakan tipe satu pilihan (ya/tidak) untuk reactions.",
}
vote_timer_kwargs = deepcopy(kickban_timer_kwargs)
vote_timer_kwargs["default"] = "5m"
vote_timer_kwargs["help"] = (
    "Waktu sebelum voting ditutup (Format time string seperti: "
    "'30m 30s' untuk 30 menit 30 detik, minimal 3 menit, default 5 menit)\n"
    "Referensi time string: https://naoti.me/docs/perintah/vote#time-string-format"
)

giveaway_timer_kwargs = deepcopy(kickban_timer_kwargs)
giveaway_timer_kwargs["default"] = "1hr"
giveaway_timer_kwargs["help"] = (
    "Waktu sebelum voting ditutup (Format time string seperti: "
    "'30m 30s' untuk 30 menit 30 detik, minimal 5 menit, default 1 jam)\n"
    "Referensi time string: https://naoti.me/docs/perintah/vote#time-string-format"
)

ban_args = Arguments("voteban")
ban_args.add_args("user", help="User yang ingin di ban/kick.")
ban_args.add_args(*kickban_limit_args, **kickban_limit_kwargs)
ban_args.add_args(*kickban_timer_args, **kickban_timer_kwargs)
kick_args = Arguments("votekick")
kick_args.add_args("user", help="User yang ingin di ban/kick.")
kick_args.add_args(*kickban_limit_args, **kickban_limit_kwargs)
kick_args.add_args(*kickban_timer_args, **kickban_timer_kwargs)
vote_args = Arguments("vote")
vote_args.add_args("topik", help="Hal yang ingin divote.")
vote_args.add_args(*vote_opsi_args, **vote_opsi_kwargs)
vote_args.add_args(*kickban_timer_args, **vote_timer_kwargs)
vote_args.add_args(*vote_tipe_yn_args, **vote_tipe_yn_kwargs)
giveaway_args = Arguments("giveaway")
giveaway_args.add_args("barang", help="Hal yang ingin diberikan")
giveaway_args.add_args(*kickban_timer_args, **giveaway_timer_kwargs)
ban_converter = CommandArgParse(ban_args)
kick_converter = CommandArgParse(kick_args)
vote_converter = CommandArgParse(vote_args)
giveaway_converter = CommandArgParse(giveaway_args)


class VoteApp(commands.Cog):
    def __init__(self, bot: naoTimesBot):
        self.bot = bot
        self.logger = logging.getLogger("cogs.vote.VoteApp")

        self.vote_backend = VoteWatcher(self.bot.fcwd, self.bot.redisdb, self.bot.loop)
        self._precheck_existing_vote.start()
        self.readjust_embed.start()

        self._task_handler: asyncio.Task = asyncio.Task(self._voting_over_handler())

    @staticmethod
    def sec_to_left(seconds):
        if seconds >= 3600:
            return f"{int(seconds // 3600)} Jam"
        elif seconds < 3600 and seconds >= 60:
            return f"{int(seconds // 60)} Menit"
        elif seconds < 60:
            return "Kurang dari 1 menit."

    async def count_reactions(self, vote_meta: dict) -> List[dict]:
        message_id = vote_meta["id"]
        channel_id = vote_meta["channel_id"]
        channel_data: discord.TextChannel = self.bot.get_channel(channel_id)
        msg_data: discord.Message = await channel_data.fetch_message(message_id)
        reactions: List[discord.Reaction] = msg_data.reactions

        disallowed_ids: List[int] = [vote_meta["requester"], self.bot.user.id]

        final_data = []
        if reactions:
            self.logger.info("accumulating reaction while bot gone...")
            if vote_meta["type"] in ["kickban", "yn"]:
                self.logger.info("detected y/n type")
                y_reaction: discord.Reaction = reactions[0]
                x_reaction: discord.Reaction = reactions[1]

                users_y: List[Union[discord.User, discord.Member]] = await y_reaction.users().flatten()
                users_n: List[Union[discord.User, discord.Member]] = await x_reaction.users().flatten()
                voter_data_y = [user.id for user in users_y if user.id not in disallowed_ids]
                voter_data_n = [user.id for user in users_n if user.id not in disallowed_ids]
                final_data.append(
                    {"id": "y", "tally": len(voter_data_y), "voter": voter_data_y, "name": "Ya"}
                )
                final_data.append(
                    {"id": "n", "tally": len(voter_data_n), "voter": voter_data_n, "name": "Tidak"}
                )
            elif vote_meta["type"] == "giveaway":
                self.logger.info("Detected giveaway type")
                popper_react: discord.Reaction = reactions[0]

                users_reacted: List[
                    Union[discord.User, discord.Member]
                ] = await popper_react.users().flatten()
                voter_data_real = [user.id for user in users_reacted if user.id not in disallowed_ids]
                final_data.append(
                    {"id": "join", "tally": len(voter_data_real), "voter": voter_data_real, "name": "Join"}
                )
            else:
                self.logger.info("detected other type")
                for reaction in reactions:
                    if str(reaction.emoji) in reactions_num:
                        res_num = res2num[str(reaction.emoji)]

                        users_votes: List[
                            Union[discord.User, discord.Member]
                        ] = await reaction.users().flatten()
                        voters_data = [user.id for user in users_votes if user.id not in disallowed_ids]

                        opts_name = vote_meta["answers"][res_num]["name"]
                        final_data.append(
                            {
                                "id": res_num,
                                "tally": len(voters_data),
                                "voter": voters_data,
                                "name": opts_name,
                            }
                        )
            if final_data:
                return final_data
        if vote_meta["type"] == "kickban":
            return vote_meta["vote_data"]
        elif vote_meta["type"] == "giveaway":
            participants = vote_meta["participants"]
            return [{"id": "join", "tally": len(participants), "voter": participants, "name": "Join"}]
        else:
            return vote_meta["answers"]

    @tasks.loop(seconds=1, count=1)
    async def _precheck_existing_vote(self):
        self.logger.info("checking preexisiting vote data...")
        search_path = os.path.join(self.bot.fcwd, "vote_data")
        if not os.path.isdir(search_path):
            os.makedirs(search_path)
            self.logger.info("Folder deosn't even exist yet, returning...")
            return
        search_path = os.path.join(search_path, "*.votedata")
        self.logger.info("searching for existing data...")
        votes_datas = await self.bot.redisdb.getall("ntvote_*")
        if not votes_datas:
            self.logger.info("no exisiting data, exiting...")
            return
        for vote_meta in votes_datas:
            if vote_meta["type"] == "kickban":
                self.logger.info(f"appending msg `{vote_meta['id']}` to kickban watcher")
                await self.vote_backend.start_watching_vote_kickban(
                    vote_meta["kickban_type"],
                    vote_meta["requester"],
                    {"id": vote_meta["id"], "channel": vote_meta["channel_id"]},
                    vote_meta["user_target"],
                    vote_meta["timeout"],
                    vote_meta["limit"],
                    await self.count_reactions(vote_meta),
                )
            elif vote_meta["type"] == "giveaway":
                self.logger.info(f"appending msg `{vote_meta['id']}` to giveaway watcher")
                await self.vote_backend.start_watching_giveaway(
                    vote_meta["initiator"],
                    {"id": vote_meta["id"], "channel": vote_meta["channel_id"]},
                    vote_meta["item"],
                    vote_meta["timeout"],
                    await self.count_reactions(vote_meta),
                )
            else:
                self.logger.info(f"appending msg `{vote_meta['id']}` to vote watcher")
                await self.vote_backend.start_watching_vote(
                    vote_meta["requester"],
                    {"id": vote_meta["id"], "channel": vote_meta["channel_id"]},
                    vote_meta["question"],
                    await self.count_reactions(vote_meta),
                    vote_meta["timeout"],
                )

    def cog_unload(self):
        self.logger.info("Cancelling all tasks...")
        self._task_handler.cancel()
        self.readjust_embed.cancel()
        self.cog_unload_async.start()
        self.cog_unload_async.stop()

    @tasks.loop(seconds=1, count=1)
    async def cog_unload_async(self):
        self.logger.info("Cancelling all async tasks...")
        await self.vote_backend.stop_and_flush()

    async def _handle_kickban(self, exported_data: dict, channel_data: discord.TextChannel):
        guild_id = channel_data.guild.id
        guild_data: discord.Guild = self.bot.get_guild(guild_id)
        target_user: discord.Member = guild_data.get_member(exported_data["user_target"])
        try:
            if exported_data["kickban_type"] == "kick":
                self.logger.info(f"{guild_data.name}: vote kicking {target_user.display_name} from server")
                await guild_data.kick(
                    user=target_user, reason=f"Voted out from message ID: {exported_data['id']}"
                )
            elif exported_data["kickban_type"] == "ban":
                self.logger.info(f"{guild_data.name}: vote banning {target_user.display_name} from server")
                await guild_data.ban(
                    user=target_user,
                    reason=f"Voted out from message ID: {exported_data['id']}",
                    delete_message_days=0,
                )
        except discord.Forbidden:
            self.logger.error(f"{exported_data['id']}: cannot kick/ban because missing perms.")
        except discord.HTTPException as dehttp:
            self.logger.error(f"{exported_data['id']}: cannot kick/ban because http failures.")
            self.bot.echo_error(dehttp)

    async def _voting_over_handler(self):
        self.logger.info("starting vote done task handling...")
        while True:
            try:
                vote_handler: Union[VotingData, VotingKickBan] = await self.vote_backend.done_queue.get()
                exported_data = vote_handler.export_data()
                self.logger.info(f"{exported_data['id']}: handling vote data...")
                final_tally = vote_handler.tally_all()
                self.logger.info(f"{exported_data['id']}: fetching channel/msg data...")
                channel: discord.TextChannel = self.bot.get_channel(exported_data["channel_id"])
                try:
                    message: discord.Message = await channel.fetch_message(exported_data["id"])
                    embed: discord.Embed = discord.Embed.from_dict(message.embeds[0].to_dict())
                    content_txt = ""
                    if exported_data["type"] == "giveaway":
                        embed.set_footer(text="Giveaway selesai!")
                        content_txt = "🎉 **Giveaway selesai** 🎉"
                    else:
                        embed.set_footer(text="Voting Selesai!")
                    await message.edit(content=content_txt, embed=embed)
                except discord.NotFound:
                    self.logger.warning(f"{exported_data['id']}: message missing, will send results...")
                    pass

                # Decide.
                if exported_data["type"] == "kickban":
                    self.logger.info(f"{exported_data['id']}: deciding kick/ban results...")
                    target_member = channel.guild.get_member(exported_data["user_target"])
                    # Sort results.
                    self.logger.info(f"{exported_data['id']}: sorting data...")
                    sorted_tally = dict(sorted(final_tally.items(), key=lambda item: item[1], reverse=True))
                    if sorted_tally["y"] >= exported_data["limit"]:
                        self.logger.info(f"{exported_data['id']}: limit reached, people voted for yes...")
                        await self._handle_kickban(exported_data, channel)
                        await channel.send(
                            content=f"Limit voting tercapai, Selamat tinggal **{target_member.name}** o7"
                        )
                    elif sorted_tally["n"] >= exported_data["limit"]:
                        self.logger.info(f"{exported_data['id']}: limit reached, people voted for no...")
                        await channel.send(
                            content=f"Limit voting tercapai, **{target_member.name}** aman "
                            f"dari {exported_data['kickban_type']}"
                        )
                    else:
                        self.logger.info(f"{exported_data['id']}: time limit reached...")
                        await channel.send(
                            content=f"Waktu voting habis, **{target_member.name}** aman "
                            f"dari {exported_data['kickban_type']}"
                        )
                elif exported_data["type"] == "giveaway":
                    self.logger.info(f"{exported_data['id']}: deciding giveaway results...")
                    if len(final_tally) < 1:
                        await channel.send(
                            f"Giveaway **__{exported_data['item']}__** selesai! Tetapi tidak ada yang join..."
                        )
                    else:
                        winner_member: discord.Member = None
                        while True:
                            selected_winner = random.choice(final_tally)
                            winner_member = channel.guild.get_member(selected_winner)
                            if winner_member is not None:
                                break
                        if winner_member is None:
                            await channel.send(
                                f"Giveaway **__{exported_data['item']}__** selesai! Tetapi bot "
                                "tidak bisa memilih pemenang..."
                            )
                        else:
                            win_msg = f"Giveaway **__{exported_data['item']}__** selesai!\n"
                            win_msg += f"Selamat kepada <@{winner_member.id}>\n"
                            win_msg += f"<{message.jump_url}>"
                            await channel.send(win_msg)
                else:
                    # Sort results.
                    self.logger.info(f"{exported_data['id']}: sorting data...")
                    sorted_tally = dict(sorted(final_tally.items(), key=lambda item: item[1], reverse=True))
                    if "y" in sorted_tally or "n" in sorted_tally:
                        if sorted_tally["y"] == sorted_tally["n"]:
                            await channel.send(
                                content="Waktu voting habis, Hasil akhir dari "
                                f"**{exported_data['question']}** adalah... **Seri!**"
                            )
                        elif sorted_tally["y"] > sorted_tally["n"]:
                            await channel.send(
                                content="Waktu voting habis, Hasil akhir dari "
                                f"**{exported_data['question']}** adalah... **Ya!**"
                            )
                        elif sorted_tally["y"] < sorted_tally["n"]:
                            await channel.send(
                                content="Waktu voting habis, Hasil akhir dari "
                                f"**{exported_data['question']}** adalah... **Tidak!**"
                            )
                    else:
                        manual_tally = exported_data["answers"]
                        manual_tally.sort(key=lambda x: x["tally"], reverse=True)
                        winner = manual_tally[0]
                        winner_react = num2res[winner["id"]]
                        if winner["tally"] > 0:
                            await channel.send(
                                content="Waktu voting habis, Hasil akhir dari "
                                f"**{exported_data['question']}** adalah... {winner_react} "
                                f"**{winner['name']}** `{winner['tally']} votes`"
                            )
                        else:
                            await channel.send(
                                content="Waktu voting habis, tidak ada yang voting"
                                f" tentang **{exported_data['question']}**"
                            )
                self.vote_backend.done_queue.task_done()
            except asyncio.CancelledError:
                return

    @tasks.loop(seconds=30, count=None)
    async def readjust_embed(self):
        current_time = datetime.now(tz=timezone.utc).timestamp()
        if self.vote_backend.vote_holding:
            msg_votes = deepcopy(self.vote_backend.vote_holding)
            self.logger.info("processing vote embed editing...")
            for _, vote_handler in msg_votes.items():
                exported_data = vote_handler.export_data()
                channel: discord.TextChannel = self.bot.get_channel(exported_data["channel_id"])
                try:
                    message: discord.Message = await channel.fetch_message(exported_data["id"])
                except discord.NotFound:
                    self.logger.warning(f"{exported_data['id']}: message removed by user, handling it...")
                    try:
                        await self.vote_backend.stop_watching_vote(exported_data["id"])
                    except KeyError:
                        pass
                    continue
                embed: discord.Embed = discord.Embed.from_dict(message.embeds[0].to_dict())
                if exported_data["type"] == "kickban":
                    embed.set_field_at(
                        0,
                        name=f"Jumlah vote (Dibutuhkan: {exported_data['limit']})",
                        value=f"{exported_data['vote_data'][0]['tally']} votes",
                        inline=False,
                    )
                elif exported_data["type"] == "yn":
                    y_ans = exported_data["answers"][0]
                    x_ans = exported_data["answers"][1]
                    embed.set_field_at(
                        0, name="✅ Ya", value=f"**Total**: {y_ans['tally']}", inline=True,
                    )
                    embed.set_field_at(
                        1, name="❎ Tidak", value=f"**Total**: {x_ans['tally']}", inline=True,
                    )
                elif exported_data["type"] == "giveaway":
                    participant = exported_data["participants"][0]
                    embed.set_field_at(
                        0, name="Partisipasi", value=f"{participant['tally']} partisipasi", inline=False
                    )
                else:
                    for i in range(len(exported_data["answers"])):
                        react = num2res[i]
                        answers = exported_data["answers"][i]
                        embed.set_field_at(
                            i,
                            name=f"{react} {answers['name']}",
                            value=f"**Total**: {answers['tally']}",
                            inline=False,
                        )
                embed.set_footer(
                    text=f"Sisa Waktu: {self.sec_to_left(abs(current_time - exported_data['timeout']))}"
                    " | Embed akan diperbarui tiap 30 detik."
                )
                await message.edit(embed=embed)

    @commands.Cog.listener(name="on_reaction_add")
    async def vote_added(self, reaction: discord.Reaction, user: Union[discord.Member, discord.User]):
        if user.bot:
            # Ignore bot vote.
            return
        if str(reaction.message.id) not in self.vote_backend.vote_holding:
            # Ignore other msg vote.
            return
        try:
            if "✅" in str(reaction.emoji) or "🎉" in str(reaction.emoji):
                await self.vote_backend.add_vote(reaction.message.id, user.id, 0)
            elif "❌" in str(reaction.emoji) or "❎" in str(reaction.emoji):
                await self.vote_backend.add_vote(reaction.message.id, user.id, 1)
            elif str(reaction.emoji) in reactions_num:
                num_choice = res2num[str(reaction.emoji)]
                await self.vote_backend.add_vote(reaction.message.id, user.id, num_choice)
        except KeyError:
            pass

    @commands.Cog.listener(name="on_reaction_remove")
    async def vote_removed(self, reaction, user):
        if user.bot:
            # Ignore bot vote.
            return
        if str(reaction.message.id) not in self.vote_backend.vote_holding:
            # Ignore other msg vote.
            return
        try:
            if "✅" in str(reaction.emoji) or "🎉" in str(reaction.emoji):
                await self.vote_backend.remove_vote(reaction.message.id, user.id, 0)
            elif "❌" in str(reaction.emoji) or "❎" in str(reaction.emoji):
                await self.vote_backend.remove_vote(reaction.message.id, user.id, 1)
            elif str(reaction.emoji) in reactions_num:
                num_choice = res2num[str(reaction.emoji)]
                await self.vote_backend.remove_vote(reaction.message.id, user.id, num_choice)
        except KeyError:
            pass

    def check_hierarchy(self, ctx, user_data: discord.Member):
        if user_data.id == ctx.message.guild.owner.id:
            return False, "owner"
        if user_data.guild_permissions.administrator:
            return False, "admin"
        hirarki_bot = ctx.message.guild.get_member(self.bot.user.id).top_role.position
        if user_data.top_role.position >= hirarki_bot:
            return False, "higher"
        return True, "can"

    @staticmethod
    def hierarcy_error(reason: str, kb_type: str):
        if reason == "higher":
            return f"Tidak dapat nge{kb_type} user, posisi hirarki lebih tinggi dari bot."
        elif reason == "owner":
            return f"Tidak dapat nge{kb_type} user, user adalah owner server."
        elif reason == "admin":
            return f"Tidak dapat nge{kb_type} user, user adalah admin server."
        return f"Tidak dapat nge{kb_type} user."

    @commands.command()
    async def vote(self, ctx, *, args: vote_converter = vote_converter.show_help()):  # type: ignore
        if isinstance(args, str):
            args = f"```py\n{args}\n```"
            return await ctx.send(args)

        if not args.opsi and not args.use_yn:
            return await ctx.send("Masukan opsi atau pilih mode ya atau tidak (`-S`)")

        if not args.use_yn:
            if len(args.opsi) < 2:
                return await ctx.send("Minimal 2 opsi.")
            if len(args.opsi) > 10:
                return await ctx.send("Maksimal 10 opsi.")

        embed = discord.Embed(title="Vote!", color=0x2A6968)
        embed.description = (
            f"**Pertanyaan**: {args.topik}\n\nMasukan pilihanmu dengan klik reaction di bawah ini"
        )
        if not args.use_yn:
            for nopsi, opsi in enumerate(args.opsi):
                nres = num2res[nopsi]
                embed.add_field(name=f"{nres} {opsi}", value="**Total**: 0", inline=False)
        else:
            embed.add_field(name="✅ Ya", value="**Total**: 0", inline=True)
            embed.add_field(name="❎ Tidak", value="**Total**: 0", inline=True)

        try:
            parsed_time = TimeString.parse(args.waktu)
            time_limit = parsed_time.timestamp()
        except TimeStringParseError as errparse:
            return await ctx.send(f"Gagal parsing batas waktu, {errparse.reason}")
        if time_limit < 180:
            return await ctx.send("Minimal batas waktu adalah 3 menit.")

        embed.set_footer(
            text=f"Sisa Waktu: {self.sec_to_left(time_limit)} | Embed akan diperbarui tiap 30 detik."
        )

        msg: discord.Message = await ctx.send(embed=embed)

        if args.use_yn:
            await msg.add_reaction("✅")
            await msg.add_reaction("❎")
        else:
            for nopsi, _ in enumerate(args.opsi):
                nres = num2res[nopsi]
                await msg.add_reaction(nres)

        gen_ans = self.vote_backend.generate_answers(args.opsi, args.use_yn)
        max_dt = int(round(datetime.now(tz=timezone.utc).timestamp() + time_limit + 2))
        await self.vote_backend.start_watching_vote(
            ctx.message.author.id, {"id": msg.id, "channel": msg.channel.id}, args.topik, gen_ans, max_dt
        )

    @commands.command()
    @commands.has_guild_permissions(kick_members=True)
    @commands.bot_has_guild_permissions(kick_members=True)
    async def votekick(self, ctx, *, args: kick_converter = kick_converter.show_help()):  # type: ignore
        if isinstance(args, str):
            args = f"```py\n{args}\n```"
            return await ctx.send(args)

        vote_limit = args.batas
        if isinstance(vote_limit, (str, float)):
            try:
                vote_limit = int(vote_limit)
            except ValueError:
                return await ctx.send("Minimal vote bukanlah angka.")

        if vote_limit < 5:
            return await ctx.send("Minimal vote adalah 5 orang.")

        user_input = args.user
        user_mentions = ctx.message.mentions

        if not user_mentions:
            if user_input.isdigit():
                try:
                    user_data = ctx.message.guild.get_member(int(user_input))
                except (ValueError, AttributeError, KeyError):
                    return await ctx.send("Mention orang/ketik ID yang valid")
            else:
                return await ctx.send("Mention orang/ketik ID yang ingin di kick")
        else:
            user_data = user_mentions[0]

        better_hierarcy, hierarcy_pos = self.check_hierarchy(ctx, user_data)
        if not better_hierarcy:
            return await ctx.send(self.hierarcy_error(hierarcy_pos, "kick"))

        embed = discord.Embed(
            title="Vote Kick - {0.name}#{0.discriminator}".format(user_data),
            description="React jika ingin user ini dikick.",
            color=0x3F0A16,
        )
        embed.add_field(
            name=f"Jumlah vote (Dibutuhkan: {vote_limit})", value="0 votes", inline=False,
        )

        try:
            parsed_time = TimeString.parse(args.waktu)
            time_limit = parsed_time.timestamp()
        except TimeStringParseError as errparse:
            return await ctx.send(f"Gagal parsing batas waktu, {errparse.reason}")
        if time_limit < 30:
            return await ctx.send("Minimal batas waktu adalah 30 detik.")

        embed.set_footer(
            text=f"Sisa Waktu: {self.sec_to_left(time_limit)} | Embed akan diperbarui tiap 30 detik."
        )

        msg: discord.Message = await ctx.send(embed=embed)
        await msg.add_reaction("✅")
        await msg.add_reaction("❌")

        max_dt = int(round(datetime.now(tz=timezone.utc).timestamp() + time_limit + 2))
        await self.vote_backend.start_watching_vote_kickban(
            "kick",
            ctx.message.author.id,
            {"id": msg.id, "channel": msg.channel.id},
            user_data.id,
            max_dt,
            vote_limit,
        )

    @commands.command()
    @commands.has_guild_permissions(ban_members=True)
    @commands.bot_has_guild_permissions(ban_members=True)
    async def voteban(self, ctx, *, args: ban_converter = ban_converter.show_help()):  # type: ignore
        if isinstance(args, str):
            args = f"```py\n{args}\n```"
            return await ctx.send(args)

        vote_limit = args.batas
        if isinstance(vote_limit, (str, float)):
            try:
                vote_limit = int(vote_limit)
            except ValueError:
                return await ctx.send("Minimal vote bukanlah angka.")

        if vote_limit < 5:
            return await ctx.send("Minimal vote adalah 5 orang.")

        user_input = args.user
        user_mentions = ctx.message.mentions

        if not user_mentions:
            if user_input.isdigit():
                try:
                    user_data = ctx.message.guild.get_member(int(user_input))
                except (AttributeError, KeyError, ValueError):
                    return await ctx.send("Mention orang/ketik ID yang valid")
            else:
                return await ctx.send("Mention orang/ketik ID yang ingin di kick")
        else:
            user_data = user_mentions[0]

        better_hierarcy, hierarcy_pos = self.check_hierarchy(ctx, user_data)
        if not better_hierarcy:
            return await ctx.send(self.hierarcy_error(hierarcy_pos, "ban"))

        embed = discord.Embed(
            title="Vote Ban - {0.name}#{0.discriminator}".format(user_data),
            description="React jika ingin user ini dibanned.",
            color=0x3F0A16,
        )
        embed.add_field(
            name=f"Jumlah vote (Dibutuhkan: {vote_limit})", value="0 votes", inline=False,
        )

        try:
            parsed_time = TimeString.parse(args.waktu)
            time_limit = parsed_time.timestamp()
        except TimeStringParseError as errparse:
            return await ctx.send(f"Gagal parsing batas waktu, {errparse.reason}")
        if time_limit < 30:
            return await ctx.send("Minimal batas waktu adalah 30 detik.")

        embed.set_footer(
            text=f"Sisa Waktu: {self.sec_to_left(time_limit)} | Embed akan diperbarui tiap 30 detik."
        )

        msg: discord.Message = await ctx.send(embed=embed)
        await msg.add_reaction("✅")
        await msg.add_reaction("❌")

        max_dt = int(round(datetime.now(tz=timezone.utc).timestamp() + time_limit + 2))
        await self.vote_backend.start_watching_vote_kickban(
            "ban",
            ctx.message.author.id,
            {"id": msg.id, "channel": msg.channel.id},
            user_data.id,
            max_dt,
            vote_limit,
        )

    @commands.command()
    @commands.guild_only()
    async def giveaway(self, ctx, *, args: giveaway_converter = giveaway_converter.show_help()):
        if isinstance(args, str):
            args = f"```py\n{args}\n```"
            return await ctx.send(args)

        if len("Giveaway: " + args.barang) >= 256:
            return await ctx.send("Nama barang/item terlalu panjang!")

        embed = discord.Embed(
            title=f"Giveaway: {args.barang}", description="React 🎉 untuk join giveaway!", color=0x3D72A8,
        )
        embed.add_field(
            name="Partisipasi", value="0 partisipasi", inline=False,
        )

        try:
            parsed_time = TimeString.parse(args.waktu)
            time_limit = parsed_time.timestamp()
        except TimeStringParseError as errparse:
            return await ctx.send(f"Gagal parsing batas waktu, {errparse.reason}")
        if time_limit < 300:
            return await ctx.send("Minimal batas waktu adalah 5 menit.")

        embed.set_footer(
            text=f"Sisa Waktu: {self.sec_to_left(time_limit)} | Embed akan diperbarui tiap 30 detik."
        )

        msg: discord.Message = await ctx.send(embed=embed)
        await msg.add_reaction("🎉")

        max_dt = int(round(datetime.now(tz=timezone.utc).timestamp() + time_limit + 2))
        await self.vote_backend.start_watching_giveaway(
            ctx.message.author.id, {"id": msg.id, "channel": msg.channel.id}, args.barang, max_dt
        )

    @commands.command()
    @commands.guild_only()
    async def reroll(self, ctx: commands.Context, msg_id: int):
        kanal: discord.TextChannel = ctx.channel
        if kanal is None:
            return await ctx.send("Mohon jalankan command ini ditempat yang sama giveaway dilakukan!")
        try:
            pesan: discord.Message = await kanal.fetch_message(msg_id)
        except discord.NotFound:
            return await ctx.send(
                "Tidak dapat menemukan pesan ID tersebut, "
                "mohon jalankan command ini ditempat yang sama giveaway dilakukan!"
            )
        except discord.Forbidden:
            return await ctx.send("Bot tidak memiliki akses untuk melihat pesan di channel ini.")
        except discord.HTTPException:
            return await ctx.send("Tidak dapat menghubungi Discord, mohon coba lagi!")

        if len(pesan.embeds) < 1:
            return await ctx.send("Tidak dapat menemukan embed pada pesan tersebut!")
        giveaway_embed: discord.Message = None
        for embed in pesan.embeds:
            test: discord.Embed = discord.Embed.from_dict(embed.to_dict())
            if (
                isinstance(test.title, str)
                and test.title.startswith("Giveaway: ")
                and pesan.author.id == self.bot.user.id
            ):
                giveaway_embed = pesan
                break
        if giveaway_embed is None:
            return await ctx.send("Pesan tersebut bukanlah embed giveaway naoTimes")

        reactions = pesan.reactions
        if len(reactions) < 1:
            return await ctx.send("Tidak ada reaction di pesan tersebut?")
        popper_dex: discord.Reaction = None
        for reaction in reactions:
            if "🎉" in str(reaction.emoji):
                popper_dex = reaction
        if popper_dex is None:
            return await ctx.send("Tidak dapat menemukan reaction 🎉 di pesan tersebut")
        reactionist = await popper_dex.users().flatten()
        users = [user for user in reactionist if not user.bot]
        winner = random.choice(users)
        await kanal.send(f"Giveaway <{pesan.jump_url}>, direroll!\nPemenang barunya adalah: <@{winner.id}>")

    @votekick.error
    async def votekick_error(self, ctx, error):
        if isinstance(error, commands.BotMissingPermissions):
            await ctx.send("Tidak bisa melakukan vote kick, bot tidak ada hak.")

    @voteban.error
    async def voteban_error(self, ctx, error):
        if isinstance(error, commands.BotMissingPermissions):
            await ctx.send("Tidak bisa melakukan vote ban, bot tidak ada hak.")

    @commands.command(name="reactcount")
    async def get_react_count(self, ctx, msg_id: int):
        channel_data: discord.TextChannel = self.bot.get_channel(ctx.message.channel.id)
        msg_data: discord.Message = await channel_data.fetch_message(msg_id)
        reactions: List[discord.Reaction] = msg_data.reactions

        reaction_data = []
        for reaction in reactions:
            reaction_data.append(f"{str(reaction.emoji)} {reaction.count}")

        await ctx.send("\n".join(reaction_data))


def setup(bot: naoTimesBot):
    bot.add_cog(VoteApp(bot))
