import asyncio

import discord
import discord.ext.commands as commands

from nthelper.kbbiasync import (KBBI, AutentikasiKBBI, BatasSehari,
                                GagalKoneksi, TerjadiKesalahan, TidakDitemukan)


async def secure_results(hasil_entri: list) -> list:
    for x, hasil in enumerate(hasil_entri):
        if "kata_turunan" not in hasil:
            hasil_entri[x]["kata_turunan"] = []
        if "etimologi" not in hasil:
            hasil_entri[x]["etimologi"] = {}
        if "gabungan_kata" not in hasil:
            hasil_entri[x]["gabungan_kata"] = []
        if "peribahasa" not in hasil:
            hasil_entri[x]["peribahasa"] = []
        if "kiasan" not in hasil:
            hasil_entri[x]["kiasan"] = []
    return hasil_entri


async def query_requests_kbbi(kata_pencarian):
    try:
        cari_kata = KBBI(kata_pencarian)
        await cari_kata.cari()
    except TidakDitemukan:
        await cari_kata.tutup()
        return kata_pencarian, 'Tidak dapat menemukan kata tersebut di KBBI.'
    except TerjadiKesalahan:
        await cari_kata.tutup()
        return kata_pencarian, 'Terjadi kesalahan komunikasi dengan server KBBI.'
    except BatasSehari:
        await cari_kata.tutup()
        return kata_pencarian, 'Bot telah mencapai batas pencarian harian, mohon coba esok hari lagi.'
    except GagalKoneksi:
        await cari_kata.tutup()
        return kata_pencarian, 'Tidak dapat terhubung dengan KBBI, kemungkinan KBBI daring sedang down.'

    hasil_kbbi = cari_kata.serialisasi()
    pranala = hasil_kbbi["pranala"]
    hasil_entri = await secure_results(hasil_kbbi["entri"])

    await cari_kata.tutup()
    return pranala, hasil_entri


class ntKBBI(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command(name="kbbi")
    async def _kbbi_cmd_main(self, ctx, *, kata_pencarian):
        print('--> Running kbbi command')
        kata_pencarian = kata_pencarian.lower()

        pranala, hasil_entri = await query_requests_kbbi(kata_pencarian)

        if isinstance(hasil_entri, str):
            return await ctx.send(hasil_entri)

        if not hasil_entri:
            print('[@] No results.')
            return await ctx.send('Tidak dapat menemukan kata tersebut di KBBI')

        add_numbering = False
        if len(hasil_entri) > 1:
            add_numbering = True

        print("--> Memproses hasil dari KBBI")
        final_dataset = []
        for hasil in hasil_entri:
            entri = {
                "nama": "",
                "kata_dasar": "",
                "pelafalan": "",
                "takbaku": "",
                "varian": "",
                "makna": "",
                "contoh": "",
                "etimologi": "",
                "turunan": "",
                "gabungan": "",
                "peribahasa": "",
                "kiasan": ""
            }
            entri["nama"] = hasil['nama']
            if add_numbering:
                entri["nama"] = "{a} ({b})".format(a=hasil["nama"], b=hasil["nomor"])
            if hasil["kata_dasar"]:
                entri["kata_dasar"] = "; ".join(hasil['kata_dasar'])
            if hasil["pelafalan"]:
                entri["pelafalan"] = hasil["pelafalan"]
            if hasil["bentuk_tidak_baku"]:
                entri["takbaku"] = "; ".join(hasil['bentuk_tidak_baku'])
            if hasil["varian"]:
                entri["varian"] = "; ".join(hasil['varian'])
            if hasil["kata_turunan"]:
                entri["turunan"] = "; ".join(hasil['kata_turunan'])
            if hasil["gabungan_kata"]:
                entri["gabungan"] = "; ".join(hasil['gabungan_kata'])
            if hasil["peribahasa"]:
                entri["peribahasa"] = "; ".join(hasil['peribahasa'])
            if hasil["kiasan"]:
                entri["kiasan"] = "; ".join(hasil['kiasan'])
            contoh_tbl = []
            makna_tbl = []
            for nmr_mkn, makna in enumerate(hasil["makna"], 1):
                makna_txt = "**{i}.** ".format(i=nmr_mkn)
                for kls in makna["kelas"]:
                    makna_txt += "*({a})* ".format(a=kls["kode"])
                makna_txt += "; ".join(makna["submakna"])
                if makna["info"]:
                    makna_txt += " " + makna["info"]
                makna_tbl.append(makna_txt)
                contoh_txt = "**{i}.** ".format(i=nmr_mkn)
                if makna["contoh"]:
                    contoh_txt += "; ".join(makna["contoh"])
                    contoh_tbl.append(contoh_txt)
                else:
                    contoh_txt += "Tidak ada"
                    contoh_tbl.append(contoh_txt)
            if hasil["etimologi"]:
                etimologi_txt = ""
                etimol = hasil["etimologi"]
                etimologi_txt += "[{}]".format(etimol["bahasa"])
                etimologi_txt += " ".join("({})".format(k) for k in etimol["kelas"])
                etimologi_txt += " " + " ".join((etimol["asal_kata"], etimol["pelafalan"])) + ": "
                etimologi_txt += "; ".join(etimol["arti"])
                entri["etimologi"] = etimologi_txt
            entri["makna"] = "\n".join(makna_tbl)
            entri["contoh"] = "\n".join(contoh_tbl)
            final_dataset.append(entri)

        async def _highlight_specifics(text: str, hi: str) -> str:
            tokenize = text.split(" ")
            for n, token in enumerate(tokenize):
                if hi in token:
                    if token.endswith('; '):
                        tokenize[n] = "***{}***; ".format(token[:-2])
                    elif token.endswith(';'):
                        tokenize[n] = "***{}***;".format(token[:-1])
                    elif token.startswith("; "):
                        tokenize[n] = "; ***{}***".format(token[2:])
                    elif token.startswith(";"):
                        tokenize[n] = ";***{}***".format(token[1:])
                    else:
                        tokenize[n] = "***{}***".format(token)
            return " ".join(tokenize)

        async def _design_embed(entri):
            embed = discord.Embed(color=0x110063)
            embed.set_author(name=entri["nama"], url=pranala, icon_url="https://p.n4o.xyz/i/kbbi192.png")
            deskripsi = ""
            btb_varian = ""
            if entri["pelafalan"]:
                deskripsi += "**Pelafalan**: {}\n".format(entri["pelafalan"])
            if entri["etimologi"]:
                deskripsi += "**Etimologi**: {}\n".format(entri["etimologi"])
            if entri["kata_dasar"]:
                deskripsi += "**Kata Dasar**: {}\n".format(entri["kata_dasar"])
            if entri["takbaku"]:
                btb_varian += "**Bentuk tak baku**: {}\n".format(entri["takbaku"])
            if entri["varian"]:
                btb_varian += "**Varian**: {}\n".format(entri["varian"])
            if deskripsi:
                embed.description = deskripsi

            entri_terkait = ""
            if entri["turunan"]:
                entri_terkait += "**Kata Turunan**: {}\n".format(entri["turunan"])
            if entri["gabungan"]:
                entri_terkait += "**Kata Gabungan**: {}\n".format(entri["gabungan"])
            if entri["peribahasa"]:
                peri_hi = await _highlight_specifics(entri["peribahasa"], kata_pencarian)
                entri_terkait += "**Peribahasa**: {}\n".format(peri_hi)
            if entri["kiasan"]:
                kias_hi = await _highlight_specifics(entri["kiasan"], kata_pencarian)
                entri_terkait += "**Kiasan**: {}\n".format(kias_hi)
            embed.add_field(name="Makna", value=entri["makna"], inline=False)
            embed.add_field(name="Contoh", value=entri["contoh"] if entri["contoh"] else "Tidak ada", inline=False)
            if entri_terkait:
                embed.add_field(name="Entri Terkait", value=entri_terkait, inline=False)
            if btb_varian:
                embed.add_field(name="Bentuk tak baku/Varian", value=btb_varian, inline=False)
            return embed

        first_run = True
        dataset_total = len(final_dataset)
        pos = 1
        if not final_dataset:
            return await ctx.send('Terjadi kesalahan komunikasi dengan server KBBI.')
        print('--> Mengirim embed, total hasil: ' + str(dataset_total))
        while True:
            if first_run:
                print('--> First run!')
                entri = final_dataset[pos - 1]
                embed = await _design_embed(entri)
                msg = await ctx.send(embed=embed)
                first_run = False

            if dataset_total < 2:
                print('--> Tak ada hasil lagi, menghentikan proses!')
                break
            elif pos == 1:
                to_react = ['⏩', '✅']
            elif dataset_total == pos:
                to_react = ['⏪', '✅']
            elif pos > 1 and pos < dataset_total:
                to_react = ['⏪', '⏩', '✅']

            for react in to_react:
                await msg.add_reaction(react)

            def check_react(reaction, user):
                if reaction.message.id != msg.id:
                    return False
                if user != ctx.message.author:
                    return False
                if str(reaction.emoji) not in to_react:
                    return False
                return True

            try:
                res, user = await self.bot.wait_for('reaction_add', timeout=20.0, check=check_react)
            except asyncio.TimeoutError:
                print('--> Timeout, menghentikan proses!')
                return await msg.clear_reactions()
            if user != ctx.message.author:
                pass
            elif '✅' in str(res.emoji):
                print('--> Selesai, menghentikan proses!')
                return await msg.clear_reactions()
            elif '⏪' in str(res.emoji):
                print('-->> <-- Melihat hasil sebelumnya')
                await msg.clear_reactions()
                pos -= 1
                entri = final_dataset[pos - 1]
                embed = await _design_embed(entri)
                await msg.edit(embed=embed)
            elif '⏩' in str(res.emoji):
                print('-->> Melihat hasil selanjutnya -->')
                await msg.clear_reactions()
                pos += 1
                entri = final_dataset[pos - 1]
                embed = await _design_embed(entri)
                await msg.edit(embed=embed)


def setup(bot):
    bot.add_cog(ntKBBI(bot))
