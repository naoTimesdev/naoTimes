import logging
import random

import disnake
from disnake.ext import commands

from naotimes.bot import naoTimesBot
from naotimes.context import naoTimesContext
from naotimes.utils import bold as discord_bold


class FunRNGJesus(commands.Cog):
    def __init__(self, bot: naoTimesBot):
        self.bot = bot
        self.logger = logging.getLogger("Fun.RNGJesus")

    @commands.command(name="pilih")
    async def _fun_rng_pilih(self, ctx: naoTimesContext, *, konteks: str):
        pisah_konteks = konteks.split(",")
        pisah_konteks = [x for x in pisah_konteks if x]

        if not pisah_konteks:
            return await ctx.send("Tidak ada input untuk dipilih\nGunakan `,` sebagai pemisah.")

        if len(pisah_konteks) < 2:
            return await ctx.send("Hanya ada 1 input untuk dipilih\nGunakan `,` sebagai pemisah.")

        generate_chance = random.uniform(0.0, float(len(pisah_konteks) - 1))
        hasil_pilih = pisah_konteks[int(round(generate_chance))]
        await ctx.send(f"**{ctx.author}** aku memilih: **{hasil_pilih.strip()}**")

    @commands.command(name="kontol", aliases=["penis", "dick", "kntl"])
    async def _fun_rng_kontol(self, ctx: naoTimesContext, *, orang_lain: commands.MemberConverter = None):
        _mul = {1: "cm", 2: "m", 5: "km"}
        cocka = random.randint(2, 12)
        member = ctx.author
        if isinstance(orang_lain, disnake.Member):
            member = orang_lain
        omega = f"Panjang kntl **{member}** adalah:\n"
        mult = random.choice([1, 2, 5])
        mul = _mul.get(mult, "??")

        omega += "`8"
        omega += "=" * cocka * mult
        omega += "D`"
        omega += f" {cocka}{mul}"
        await ctx.send(omega)

    @commands.command(name="dadu", aliases=["dice"])
    async def _fun_rng_dadu(self, ctx: naoTimesContext, dice_type: str):
        try:
            roll_amount, dice_faces = dice_type.split("d")
        except ValueError:
            return await ctx.send("Jenis dadu tidak diketahui, gunakan format seperti `d20`")

        if not roll_amount.strip():
            roll_amount = 1
        else:
            if not roll_amount.isdigit():
                return await ctx.send(f"Jumlah roll `{roll_amount}` bukanlah angka")
            roll_amount = int(roll_amount)
        if not dice_faces.isdigit():
            return await ctx.send(f"Jumlah sisi dadu `{dice_faces}` bukanlah angka")
        dice_faces = int(dice_faces)
        dice_faces_range = list(range(1, dice_faces + 1))

        total_output = []
        for _ in range(roll_amount):
            total_output.append(random.choice(dice_faces_range))

        total_output_text = list(map(discord_bold, total_output))
        output_text = f"Hasil kocok dadu (**{dice_type}**): "
        output_text += " + ".join(total_output_text)
        if len(output_text) > 1:
            cash_out = sum(total_output)
            output_text += f" = **{cash_out}**"
        await ctx.send(output_text)

    @commands.command(name="kocok", aliases=["roll"])
    async def _fun_rng_kocok_dadu(self, ctx: naoTimesContext, *, range_amount: str):
        split_range = range_amount.split("-")
        first_range = split_range[0]
        second_range = split_range[0]
        if len(split_range) > 1:
            second_range = split_range[1]
        if not isinstance(first_range, int):
            try:
                first_range = int(first_range)
            except ValueError:
                return await ctx.send(f"Angka `{first_range}` bukanlah angka yang benar!")
        if not isinstance(second_range, int):
            try:
                second_range = int(second_range)
            except ValueError:
                second_range = first_range

        if first_range > second_range:
            return await ctx.send(f"Range {first_range} tidak bisa lebih besar dari angka {second_range}")

        range_num = f"**1**-**{second_range}**"
        if first_range == second_range:
            dice_faces_range = list(range(1, second_range + 1))
        else:
            range_num = f"**{first_range}**-**{second_range}**"
            dice_faces_range = list(range(first_range, second_range + 1))

        roll_outcome = random.choice(dice_faces_range)
        await ctx.send(f"Hasil kocok dadu: **{roll_outcome}** ({range_num})")


def setup(bot: naoTimesBot):
    bot.add_cog(FunRNGJesus(bot))
