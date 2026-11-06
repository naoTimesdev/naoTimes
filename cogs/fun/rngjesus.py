import logging
import random

import discord
from discord import app_commands
from discord.ext import commands

from naotimes.bot import naoTimesBot
from naotimes.utils import bold as discord_bold


class FunRNGJesus(commands.Cog):
    def __init__(self, bot: naoTimesBot):
        self.bot = bot
        self.logger = logging.getLogger("Fun.RNGJesus")

    @app_commands.command(
        name="pilih",
        description=app_commands.locale_str("Pilih salah satu dari beberapa pilihan", key="fun.pilih.description"),
    )
    @app_commands.describe(
        pilihan=app_commands.locale_str("Daftar pilihan, pisahkan dengan koma (,)", key="fun.pilih.option_pilihan")
    )
    async def _fun_rng_pilih(self, inter: discord.Interaction, pilihan: str):
        i18n = self.bot.i18n_for(inter.guild, "fun")
        options = [x.strip() for x in pilihan.split(",") if x.strip()]
        if len(options) < 2:
            return await inter.response.send_message(i18n.t("pilih.need_two"), ephemeral=True)
        await inter.response.send_message(i18n.t("pilih.result", user=inter.user, choice=random.choice(options)))

    @app_commands.command(
        name="kontol",
        description=app_commands.locale_str("Ukur panjang... sesuatu", key="fun.kontol.description"),
    )
    @app_commands.describe(
        orang=app_commands.locale_str("Orang yang ingin diukur (default: kamu)", key="fun.kontol.option_orang")
    )
    async def _fun_rng_kontol(self, inter: discord.Interaction, orang: discord.Member | None = None):
        i18n = self.bot.i18n_for(inter.guild, "fun")
        mul_ = {1: "cm", 2: "m", 5: "km"}
        cocka = random.randint(2, 12)
        member = orang or inter.user
        mult = random.choice([1, 2, 5])
        mul = mul_.get(mult, "??")
        bar = "`8" + "=" * cocka * mult + "D`"
        await inter.response.send_message(i18n.t("kontol.result", member=member, bar=bar, size=f"{cocka}{mul}"))

    @app_commands.command(
        name="dadu",
        description=app_commands.locale_str("Kocok dadu, contoh: d20 atau 3d6", key="fun.dadu.description"),
    )
    @app_commands.describe(
        jenis=app_commands.locale_str("Jenis dadu, contoh: d20 atau 3d6", key="fun.dadu.option_jenis")
    )
    async def _fun_rng_dadu(self, inter: discord.Interaction, jenis: str):
        i18n = self.bot.i18n_for(inter.guild, "fun")
        try:
            roll_amount, dice_faces = jenis.lower().split("d")
        except ValueError:
            return await inter.response.send_message(i18n.t("dadu.invalid_format"), ephemeral=True)

        if not roll_amount.strip():
            amount = 1
        elif roll_amount.isdigit():
            amount = int(roll_amount)
        else:
            return await inter.response.send_message(i18n.t("dadu.invalid_amount", amount=roll_amount), ephemeral=True)
        if not dice_faces.isdigit() or int(dice_faces) < 1:
            return await inter.response.send_message(i18n.t("dadu.invalid_faces", faces=dice_faces), ephemeral=True)
        if not 1 <= amount <= 100:
            return await inter.response.send_message(i18n.t("dadu.invalid_range"), ephemeral=True)

        results = [random.randint(1, int(dice_faces)) for _ in range(amount)]
        output_text = i18n.t("dadu.result", jenis=jenis, results=" + ".join(map(discord_bold, map(str, results))))
        if len(results) > 1:
            output_text += i18n.t("dadu.result_total", total=sum(results))
        await inter.response.send_message(output_text[:2000])

    @app_commands.command(
        name="kocok",
        description=app_commands.locale_str("Kocok angka acak dalam rentang tertentu", key="fun.kocok.description"),
    )
    @app_commands.describe(
        dari=app_commands.locale_str("Angka awal", key="fun.kocok.option_dari"),
        sampai=app_commands.locale_str(
            "Angka akhir (default: sama dengan angka awal, mulai dari 1)", key="fun.kocok.option_sampai"
        ),
    )
    async def _fun_rng_kocok_dadu(self, inter: discord.Interaction, dari: int, sampai: int | None = None):
        i18n = self.bot.i18n_for(inter.guild, "fun")
        if sampai is None:
            dari, sampai = 1, dari
        if dari > sampai:
            return await inter.response.send_message(
                i18n.t("kocok.invalid_range", start=dari, end=sampai), ephemeral=True
            )
        outcome = random.randint(dari, sampai)
        await inter.response.send_message(i18n.t("kocok.result", outcome=outcome, start=dari, end=sampai))

    @app_commands.command(
        name="santet",
        description=app_commands.locale_str("Kirim santet ke seseorang", key="fun.santet.description"),
    )
    @app_commands.describe(target=app_commands.locale_str("Target santet", key="fun.santet.option_target"))
    @app_commands.guild_only()
    async def _fun_santet(self, inter: discord.Interaction, target: discord.Member):
        i18n = self.bot.i18n_for(inter.guild, "fun")
        guild = inter.guild
        author = inter.user
        should_kick_user = (
            isinstance(author, discord.Member) and random.random() <= 0.1 and author.guild_permissions.kick_members
        )

        if should_kick_user:
            try:
                await target.send(i18n.t("santet.victim_message", author=author, guild=guild))
                await target.kick(reason=i18n.t("santet.kick_reason", author=author))
            except discord.HTTPException:
                should_kick_user = False

        if should_kick_user:
            return await inter.response.send_message(
                i18n.t("santet.result_kicked", author=author, target=target, guild=guild)
            )
        await inter.response.send_message(i18n.t("santet.result", author=author, target=target))


async def setup(bot: naoTimesBot):
    await bot.add_cog(FunRNGJesus(bot))
