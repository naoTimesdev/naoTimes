import logging
from copy import deepcopy
from typing import List

import arrow
import discord
from discord.ext import commands

from naotimes.bot import naoTimesBot
from naotimes.context import naoTimesContext
from naotimes.converters import Arguments, CommandArgParse
from naotimes.timeparse import TimeString, TimeStringParseError
from naotimes.utils import quoteblock

from .listener import VoteData, VoteManager, VoteMetadata, VoteType

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


def _humanize_timeout(timeout: arrow.Arrow):
    return timeout.humanize(locale="id", only_distance=True)


class VoteAppCommand(commands.Cog):
    PRE_KEY = "ntvotev2_"

    def __init__(self, bot: naoTimesBot) -> None:
        self.bot = bot
        self.logger = logging.getLogger("VoteSystem.CommandsV2")

    async def _save_vote_data(self, vote_data: VoteData):
        """Save the vote data to redis"""
        mid = vote_data.metadata.message
        await self.bot.redisdb.set(f"{self.PRE_KEY}{mid}", vote_data.serialize())
        self.bot.ntevent.dispatch("vote_creation", vote_data)

    @commands.command(name="vote")
    @commands.guild_only()
    async def _vote_main(self, ctx: naoTimesContext, *, args: vote_converter = vote_converter.show_help()):
        if isinstance(args, str):
            return await ctx.send(quoteblock(args, code="py"))

        use_yn: bool = args.use_yn
        options: List[str] = args.opsi
        topik: str = args.topik
        if not options and not use_yn:
            return await ctx.send("Masukan opsi atau pilih mode `ya atau tidak` (`-S`)")

        if not use_yn:
            if len(options) < 2:
                return await ctx.send("Masukan opsi lebih dari 1")
            if len(options) > 10:
                return await ctx.send("Maksimal 10 opsi")

        try:
            parsed_time = TimeString.parse(args.waktu)
            time_limit = parsed_time.timestamp()
        except TimeStringParseError as errparse:
            return await ctx.send(f"Gagal parsing batas waktu, {errparse.reason}")

        if time_limit < 180:
            return await ctx.send("Minimal batas waktu adalah 3 menit.")

        current = self.bot.now()
        timeout_time = current.shift(seconds=time_limit)
        ts_max = timeout_time.int_timestamp
        description = f"**Pertanyaan**: {topik}\n\nMasukan pilihanmu dengan klik reaction di bawah ini!"
        description += f"\nSelesai: <t:{ts_max}> (<t:{ts_max}:R>)"

        embed = discord.Embed(title="Vote!", color=0x2A6968)
        embed.description = description
        if not use_yn:
            for nopsi, opsi in enumerate(options):
                nres = num2res[nopsi]
                embed.add_field(name=f"{nres} {opsi}", value="**Total**: 0", inline=False)
        else:
            embed.add_field(name="✅ Ya", value="**Total**: 0", inline=False)
            embed.add_field(name="❌ Tidak", value="**Total**: 0", inline=False)
        embed.set_footer(text="Voting sedang berlangsung")

        real_msg = await ctx.send(embed=embed)

        all_choices = []
        mode_type = VoteType.YESNO if use_yn else VoteType.MULTIPLE
        if use_yn:
            await real_msg.add_reaction("✅")
            await real_msg.add_reaction("❌")
            all_choices.append(VoteManager("y", "Ya", "✅"))
            all_choices.append(VoteManager("n", "Tidak", "❌"))
        else:
            for nopsi, opsi in enumerate(options):
                nres = num2res[nopsi]
                await real_msg.add_reaction(nres)
                all_choices.append(VoteManager(f"mul_{nopsi}", opsi, nres))

        vote_meta = VoteMetadata(real_msg.id, real_msg.channel.id, ctx.author.id, topik)
        vote_data = VoteData(vote_meta, all_choices, ts_max, mode_type)
        await self._save_vote_data(vote_data)

    def _create_hierarcy_error(
        self, user_data: discord.Member, author: discord.Member, guild: discord.Guild, is_ban: bool = False
    ):
        tendang = ("menendang", "ditendang")
        ban = ("ngeban", "diban")
        pick = ban if is_ban else tendang
        if user_data.id == author.id:
            return f"Anda tidak bisa {pick[0]} diri sendiri!"
        if user_data.id == self.bot.user.id:
            return "No."
        if user_data.id == guild.owner.id:
            return f"Bot tidak dapat {pick[0]} owner peladen!"
        if user_data.guild_permissions.administrator:
            return f"Bot tidak dapat {pick[0]} admin!"

        hirarki_bot = guild.get_member(self.bot.user.id).top_role.position
        if user_data.top_role.position >= hirarki_bot:
            return f"User tersebut tidak dapat {pick[1]} karena hirarki yang lebih tinggi dari bot!"
        if author.guild_permissions.administrator or author.id == guild.owner_id:
            return None
        if user_data.top_role.position >= author.top_role.position:
            return f"User tersebut tidak dapat {pick[1]} karena hirarki yang lebih tinggi dari anda!"
        return None

    @commands.command(name="votekick")
    @commands.guild_only()
    @commands.has_permissions(kick_members=True)
    async def _vote_kick(self, ctx: naoTimesContext, *, args: kick_converter = kick_converter.show_help()):
        if isinstance(args, str):
            return await ctx.send(quoteblock(args, code="py"))

        guild: discord.Guild = ctx.guild
        author: discord.Member = ctx.author

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

        user_data: discord.Member
        if not user_mentions:
            if user_input.isdigit():
                user_data = guild.get_member(int(user_input))
                if user_data is None:
                    return await ctx.send("Mention orang/ketik ID yang valid")
            else:
                return await ctx.send("Mention orang/ketik ID yang ingin di kick")
        else:
            user_data = user_mentions[0]

        error_hierarcy = self._create_hierarcy_error(user_data, author, guild)
        if error_hierarcy is not None:
            return await ctx.send(error_hierarcy)

        try:
            parsed_time = TimeString.parse(args.waktu)
            time_limit = parsed_time.timestamp()
        except TimeStringParseError as errparse:
            return await ctx.send(f"Gagal parsing batas waktu, {errparse.reason}")
        if time_limit < 30:
            return await ctx.send("Minimal batas waktu adalah 30 detik.")

        current = self.bot.now()
        timeout_time = current.shift(seconds=time_limit)
        ts_max = timeout_time.int_timestamp
        real_desc = f"[🦶] React ✅ jika user ingin anda tendang!\nSelesai: <t:{ts_max}> (<t:{ts_max}:R>)"

        embed = discord.Embed(
            title=f"Vote Kick - {user_data}",
            description=real_desc,
            color=0x3F0A16,
        )
        embed.add_field(
            name=f"Jumlah vote (Dibutuhkan: {vote_limit})",
            value="0 votes",
            inline=False,
        )
        embed.set_footer(text="Voting sedang berlangsung")

        real_msg = await ctx.send(embed=embed)
        await real_msg.add_reaction("✅")
        await real_msg.add_reaction("❌")

        all_choices = [
            VoteManager(user_data.id, "Kick", "✅", vote_limit),
            VoteManager(user_data.id, "Jangan kick", "❌", vote_limit),
        ]
        vote_meta = VoteMetadata(real_msg.id, real_msg.channel.id, author.id, f"Tendang {user_data.id}")
        vote_data = VoteData(vote_meta, all_choices, ts_max, VoteType.USER)
        await self._save_vote_data(vote_data)

    @commands.command(name="voteban")
    @commands.guild_only()
    @commands.has_permissions(ban_members=True)
    async def _vote_ban(self, ctx: naoTimesContext, *, args: ban_converter = ban_converter.show_help()):
        if isinstance(args, str):
            return await ctx.send(quoteblock(args, code="py"))

        guild: discord.Guild = ctx.guild
        author: discord.Member = ctx.author

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

        user_data: discord.Member
        if not user_mentions:
            if user_input.isdigit():
                user_data = guild.get_member(int(user_input))
                if user_data is None:
                    return await ctx.send("Mention orang/ketik ID yang valid")
            else:
                return await ctx.send("Mention orang/ketik ID yang ingin di kick")
        else:
            user_data = user_mentions[0]

        error_hierarcy = self._create_hierarcy_error(user_data, author, guild)
        if error_hierarcy is not None:
            return await ctx.send(error_hierarcy)

        try:
            parsed_time = TimeString.parse(args.waktu)
            time_limit = parsed_time.timestamp()
        except TimeStringParseError as errparse:
            return await ctx.send(f"Gagal parsing batas waktu, {errparse.reason}")
        if time_limit < 30:
            return await ctx.send("Minimal batas waktu adalah 30 detik.")

        current = self.bot.now()
        timeout_time = current.shift(seconds=time_limit)
        ts_max = timeout_time.int_timestamp
        real_desc = f"[🔨] React ✅ jika user ingin anda ban!\nSelesai: <t:{ts_max}> (<t:{ts_max}:R>)"

        embed = discord.Embed(
            title=f"Vote Ban - {user_data}",
            description=real_desc,
            color=0x3F0A16,
        )
        embed.add_field(
            name=f"Jumlah vote (Dibutuhkan: {vote_limit})",
            value="0 votes",
            inline=False,
        )
        embed.set_footer(text="Voting sedang berlangsung")

        real_msg = await ctx.send(embed=embed)
        await real_msg.add_reaction("✅")
        await real_msg.add_reaction("❌")

        all_choices = [
            VoteManager(user_data.id, "Ban", "✅", vote_limit),
            VoteManager(user_data.id, "Jangan ban", "❌", vote_limit),
        ]
        vote_meta = VoteMetadata(real_msg.id, real_msg.channel.id, author.id, f"Ban {user_data.id}")
        vote_data = VoteData(vote_meta, all_choices, ts_max, VoteType.USER)
        await self._save_vote_data(vote_data)

    @commands.command(name="giveaway")
    @commands.guild_only()
    async def _vote_giveaway(
        self, ctx: naoTimesContext, *, args: giveaway_converter = giveaway_converter.show_help()
    ):
        if isinstance(args, str):
            return await ctx.send(quoteblock(args, code="py"))

        barang: str = args.barang
        if len("Giveaway: " + barang) >= 256:
            return await ctx.send("Nama barang/item terlalu panjang!")

        try:
            parsed_time = TimeString.parse(args.waktu)
            time_limit = parsed_time.timestamp()
        except TimeStringParseError as errparse:
            return await ctx.send(f"Gagal parsing batas waktu, {errparse.reason}")
        if time_limit < 300:
            return await ctx.send("Minimal batas waktu adalah 5 menit.")
        current = self.bot.now()
        timeout_time = current.shift(seconds=time_limit)
        ts_max = timeout_time.int_timestamp
        real_desc = f"React 🎉 untuk join giveaway!\nSelesai: <t:{ts_max}> (<t:{ts_max}:R>)"

        embed = discord.Embed(title=f"Giveaway: {barang}", description=real_desc, color=0x3D72A8)
        embed.add_field(name="Partisipasi", value="0 partisipan")
        embed.set_footer(text="Giveaway sedang berlangsung")

        real_msg: discord.Message = await ctx.send(embed=embed)
        await real_msg.add_reaction("🎉")

        choices = [VoteManager("giveaway", barang, "🎉")]
        vote_meta = VoteMetadata(real_msg.id, real_msg.channel.id, ctx.author.id, barang)
        vote_data = VoteData(vote_meta, choices, ts_max, VoteType.GIVEAWAY)
        await self._save_vote_data(vote_data)


def setup(bot: naoTimesBot):
    bot.add_cog(VoteAppCommand(bot))
