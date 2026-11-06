import logging

import arrow
import discord
from discord import app_commands
from discord.ext import commands

from naotimes.bot import naoTimesBot
from naotimes.timeparse import TimeString, TimeStringParseError

from .listener import VoteData, VoteManager, VoteMetadata, VoteType

reactions_num = ["1⃣", "2⃣", "3⃣", "4⃣", "5⃣", "6⃣", "7⃣", "8⃣", "9⃣", "🔟"]
res2num = dict(zip(reactions_num, [0, 1, 2, 3, 4, 5, 6, 7, 8, 9]))
num2res = dict(zip([0, 1, 2, 3, 4, 5, 6, 7, 8, 9], reactions_num))


def _humanize_timeout(timeout: arrow.Arrow, locale: str):
    return timeout.humanize(locale=locale, only_distance=True)


class VoteAppCommand(commands.Cog):
    PRE_KEY = "ntvotev2_"

    def __init__(self, bot: naoTimesBot) -> None:
        self.bot = bot
        self.logger = logging.getLogger("VoteSystem.CommandsV2")

    async def _save_vote_data(self, vote_data: VoteData):
        """Save the vote data to redis"""
        mid = vote_data.metadata.message
        if self.bot.redisdb is None:
            raise RuntimeError("Vote storage is unavailable")
        await self.bot.redisdb.set(f"{self.PRE_KEY}{mid}", vote_data.serialize())
        if self.bot.ntevent is None:
            self.logger.error("Cannot announce vote creation because the event manager is unavailable")
            return
        self.bot.ntevent.dispatch("vote_creation", vote_data)

    async def _post_vote(self, inter: discord.Interaction, embed: discord.Embed, reactions: list[str]):
        """Send the vote embed as the interaction response and attach the reactions."""
        await inter.response.send_message(embed=embed)
        sent = await inter.original_response()
        for reaction in reactions:
            await sent.add_reaction(reaction)
        return sent

    def _parse_duration(self, i18n, raw: str, minimum: int) -> tuple[int | None, str | None]:
        try:
            seconds = TimeString.parse(raw).timestamp()
        except TimeStringParseError as errparse:
            return None, i18n.t("voting.duration_parse_error", reason=errparse.reason)
        if seconds < minimum:
            return None, i18n.t("voting.duration_min", minimum=TimeString.from_seconds(minimum).to_string())
        return int(seconds), None

    @app_commands.command(
        name="vote",
        description=app_commands.locale_str("Buat voting baru", key="vote.voting.description"),
    )
    @app_commands.guild_only()
    @app_commands.describe(
        topik=app_commands.locale_str("Hal yang ingin divote", key="vote.voting.option_topik"),
        opsi=app_commands.locale_str(
            "Opsi voting dipisah dengan titik koma (;), minimal 2 dan maksimal 10", key="vote.voting.option_opsi"
        ),
        ya_tidak=app_commands.locale_str(
            "Gunakan mode satu pilihan (ya/tidak) dan abaikan opsi", key="vote.voting.option_ya_tidak"
        ),
        waktu=app_commands.locale_str(
            "Waktu sebelum voting ditutup, contoh: 30m, 1h 30m (minimal 3 menit, default 5 menit)",
            key="vote.voting.option_waktu",
        ),
    )
    async def _vote_main(
        self,
        inter: discord.Interaction,
        topik: str,
        opsi: str | None = None,
        ya_tidak: bool = False,
        waktu: str = "5m",
    ):
        """Buat voting baru"""
        i18n = self.bot.i18n_for(inter.guild, "vote")
        options = [o.strip() for o in (opsi or "").split(";") if o.strip()]
        if not options and not ya_tidak:
            return await inter.response.send_message(i18n.t("voting.need_options"), ephemeral=True)
        if not ya_tidak:
            if len(options) < 2:
                return await inter.response.send_message(i18n.t("voting.min_options"), ephemeral=True)
            if len(options) > 10:
                return await inter.response.send_message(i18n.t("voting.max_options"), ephemeral=True)

        time_limit, error = self._parse_duration(i18n, waktu, 180)
        if error:
            return await inter.response.send_message(error, ephemeral=True)

        ts_max = self.bot.now().shift(seconds=time_limit).int_timestamp
        description = i18n.t("voting.embed_description", topic=topik)
        description += i18n.t("voting.embed_deadline", timestamp=ts_max)

        embed = discord.Embed(title=i18n.t("voting.embed_title"), color=0x2A6968)
        embed.description = description
        all_choices: list[VoteManager] = []
        reactions: list[str] = []
        if ya_tidak:
            embed.add_field(name=i18n.t("shared.field_yes"), value=i18n.t("shared.total", count=0), inline=False)
            embed.add_field(name=i18n.t("shared.field_no"), value=i18n.t("shared.total", count=0), inline=False)
            reactions = ["✅", "❌"]
            all_choices = [
                VoteManager("y", i18n.t("shared.yes_label"), "✅"),
                VoteManager("n", i18n.t("shared.no_label"), "❌"),
            ]
        else:
            for nopsi, opsi_text in enumerate(options):
                nres = num2res[nopsi]
                embed.add_field(name=f"{nres} {opsi_text}", value=i18n.t("shared.total", count=0), inline=False)
                reactions.append(nres)
                all_choices.append(VoteManager(f"mul_{nopsi}", opsi_text, nres))
        embed.set_footer(text=i18n.t("shared.footer_ongoing"))

        sent = await self._post_vote(inter, embed, reactions)
        mode_type = VoteType.YESNO if ya_tidak else VoteType.MULTIPLE
        vote_meta = VoteMetadata(sent.id, sent.channel.id, inter.user.id, topik)
        await self._save_vote_data(VoteData(vote_meta, all_choices, ts_max, mode_type))

    def _create_hierarcy_error(
        self, i18n, user_data: discord.Member, author: discord.Member, guild: discord.Guild, is_ban: bool = False
    ) -> str | None:
        if is_ban:
            verb_active = i18n.t("user_action.ban_active")
            verb_passive = i18n.t("user_action.ban_passive")
        else:
            verb_active = i18n.t("user_action.kick_active")
            verb_passive = i18n.t("user_action.kick_passive")
        if user_data.id == author.id:
            return i18n.t("user_action.self", verb=verb_active)
        bot_user = self.bot.user
        if bot_user is None:
            return i18n.t("user_action.bot_user_unavailable")
        if user_data.id == bot_user.id:
            return i18n.t("user_action.self_bot")
        if user_data.id == guild.owner_id:
            return i18n.t("user_action.owner", verb=verb_active)
        if user_data.guild_permissions.administrator:
            return i18n.t("user_action.admin", verb=verb_active)

        bot_member = guild.me
        if bot_member is None:
            return i18n.t("user_action.bot_member_unavailable")
        hirarki_bot = bot_member.top_role.position
        if user_data.top_role.position >= hirarki_bot:
            return i18n.t("user_action.higher_than_bot", verb_passive=verb_passive)
        if author.guild_permissions.administrator or author.id == guild.owner_id:
            return None
        if user_data.top_role.position >= author.top_role.position:
            return i18n.t("user_action.higher_than_author", verb_passive=verb_passive)
        return None

    async def _vote_user_action(
        self, inter: discord.Interaction, user: discord.Member, batas: int, waktu: str, is_ban: bool
    ):
        i18n = self.bot.i18n_for(inter.guild, "vote")
        if batas < 5:
            return await inter.response.send_message(i18n.t("user_action.min_votes", count=5), ephemeral=True)
        if inter.guild is None or not isinstance(inter.user, discord.Member):
            return await inter.response.send_message(i18n.t("user_action.guild_only"), ephemeral=True)
        error_hierarcy = self._create_hierarcy_error(i18n, user, inter.user, inter.guild, is_ban)
        if error_hierarcy is not None:
            return await inter.response.send_message(error_hierarcy, ephemeral=True)
        time_limit, error = self._parse_duration(i18n, waktu, 30)
        if error:
            return await inter.response.send_message(error, ephemeral=True)

        ts_max = self.bot.now().shift(seconds=time_limit).int_timestamp
        if is_ban:
            emoji, verb, title = "🔨", i18n.t("user_action.ban_verb"), i18n.t("user_action.ban_title")
            no_verb = i18n.t("user_action.ban_no")
        else:
            emoji, verb, title = "🦶", i18n.t("user_action.kick_verb"), i18n.t("user_action.kick_title")
            no_verb = i18n.t("user_action.kick_no")
        real_desc = i18n.t("user_action.embed_description", emoji=emoji, verb=verb, timestamp=ts_max)
        embed = discord.Embed(
            title=i18n.t("user_action.embed_title", title=title, user=user), description=real_desc, color=0x3F0A16
        )
        embed.add_field(
            name=i18n.t("user_action.embed_field", limit=batas), value=i18n.t("shared.votes", count=0), inline=False
        )
        embed.set_footer(text=i18n.t("shared.footer_ongoing"))

        sent = await self._post_vote(inter, embed, ["✅", "❌"])
        all_choices = [
            VoteManager(user.id, title, "✅", batas),
            VoteManager(user.id, no_verb, "❌", batas),
        ]
        vote_meta = VoteMetadata(sent.id, sent.channel.id, inter.user.id, f"{title} {user.id}")
        await self._save_vote_data(VoteData(vote_meta, all_choices, ts_max, VoteType.USER))

    @app_commands.command(
        name="votekick",
        description=app_commands.locale_str(
            "Mulai voting untuk menendang seorang member", key="vote.votekick.description"
        ),
    )
    @app_commands.guild_only()
    @app_commands.default_permissions(kick_members=True)
    @app_commands.checks.has_permissions(kick_members=True)
    @app_commands.describe(
        user=app_commands.locale_str("User yang ingin ditendang", key="vote.votekick.option_user"),
        batas=app_commands.locale_str(
            "Jumlah vote untuk melaksanakan kick (minimal 5)", key="vote.votekick.option_batas"
        ),
        waktu=app_commands.locale_str(
            "Waktu sebelum voting ditutup (minimal 30 detik, default 1 menit)", key="vote.votekick.option_waktu"
        ),
    )
    async def _vote_kick(self, inter: discord.Interaction, user: discord.Member, batas: int = 5, waktu: str = "1m"):
        """Mulai voting untuk menendang seorang member"""
        await self._vote_user_action(inter, user, batas, waktu, False)

    @app_commands.command(
        name="voteban",
        description=app_commands.locale_str(
            "Mulai voting untuk mem-ban seorang member", key="vote.voteban.description"
        ),
    )
    @app_commands.guild_only()
    @app_commands.default_permissions(ban_members=True)
    @app_commands.checks.has_permissions(ban_members=True)
    @app_commands.describe(
        user=app_commands.locale_str("User yang ingin diban", key="vote.voteban.option_user"),
        batas=app_commands.locale_str(
            "Jumlah vote untuk melaksanakan ban (minimal 5)", key="vote.voteban.option_batas"
        ),
        waktu=app_commands.locale_str(
            "Waktu sebelum voting ditutup (minimal 30 detik, default 1 menit)", key="vote.voteban.option_waktu"
        ),
    )
    async def _vote_ban(self, inter: discord.Interaction, user: discord.Member, batas: int = 5, waktu: str = "1m"):
        """Mulai voting untuk mem-ban seorang member"""
        await self._vote_user_action(inter, user, batas, waktu, True)

    @app_commands.command(
        name="giveaway",
        description=app_commands.locale_str("Buat giveaway baru", key="vote.giveaway.description"),
    )
    @app_commands.guild_only()
    @app_commands.describe(
        barang=app_commands.locale_str("Hal yang ingin diberikan", key="vote.giveaway.option_barang"),
        waktu=app_commands.locale_str(
            "Waktu sebelum giveaway ditutup (minimal 5 menit, default 1 jam)", key="vote.giveaway.option_waktu"
        ),
    )
    async def _vote_giveaway(self, inter: discord.Interaction, barang: str, waktu: str = "1h"):
        """Buat giveaway baru"""
        i18n = self.bot.i18n_for(inter.guild, "vote")
        if len("Giveaway: " + barang) >= 256:
            return await inter.response.send_message(i18n.t("giveaway.title_too_long"), ephemeral=True)
        time_limit, error = self._parse_duration(i18n, waktu, 300)
        if error:
            return await inter.response.send_message(error, ephemeral=True)

        ts_max = self.bot.now().shift(seconds=time_limit).int_timestamp
        real_desc = i18n.t("giveaway.embed_description", timestamp=ts_max)
        embed = discord.Embed(title=i18n.t("giveaway.embed_title", item=barang), description=real_desc, color=0x3D72A8)
        embed.add_field(
            name=i18n.t("giveaway.field_participation"),
            value=i18n.t("giveaway.field_participation_value", count=0),
        )
        embed.set_footer(text=i18n.t("giveaway.footer_ongoing"))

        sent = await self._post_vote(inter, embed, ["🎉"])
        choices = [VoteManager("giveaway", barang, "🎉")]
        vote_meta = VoteMetadata(sent.id, sent.channel.id, inter.user.id, barang)
        await self._save_vote_data(VoteData(vote_meta, choices, ts_max, VoteType.GIVEAWAY))


async def setup(bot: naoTimesBot):
    await bot.add_cog(VoteAppCommand(bot))
