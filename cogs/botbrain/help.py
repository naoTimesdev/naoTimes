import logging
from typing import List, Union

import discord
from discord.ext import commands

from naotimes.bot import naoTimesBot, naoTimesContext
from naotimes.helpgenerator import HelpField, HelpOption

POSISI_TEXT = ", ".join(["TL", "TLC", "ENC", "ED", "TM", "TS", "QC"])

ANIMANGAVN_HELP = r"""```
<judul>: Judul anime ataupun manga yang ada di Anilist.co atau VN yang ada di vndb.org
```
"""  # noqa: E501


class BotBrainHelper(commands.Cog):
    """A custom !help command for all of my bot command"""

    def __init__(self, bot: naoTimesBot):
        self.bot = bot
        self.logger = logging.getLogger("BotBrain.Helper")

    @staticmethod
    def _owner_only_command(command: commands.Command):
        if command.checks:
            for check in command.checks:
                fn_primitive_name = check.__str__()
                if "is_owner" in fn_primitive_name:
                    return True
        return False

    async def _fallback_help(self, ctx: naoTimesContext):
        msg = ctx.message
        split_message: List[str] = msg.clean_content.split(" ")
        if len(split_message) < 2:
            return None
        cmd_info: Union[commands.Command, None] = self.bot.get_command(split_message[1])
        if cmd_info is None:
            return None
        is_owner = await self.bot.is_owner(ctx.author)
        if self._owner_only_command(cmd_info) and not is_owner:
            return None
        cmd_opts = []
        for key, val in cmd_info.clean_params.items():
            anotasi = val.annotation if val.annotation is not val.empty else None
            if anotasi is not None:
                anotasi = anotasi.__name__
            cmd_sample = {"name": key}
            if val.default is val.empty:
                cmd_sample["type"] = "r"
                cmd_sample["desc"] = f"Parameter `{key}` dibutuhkan untuk menjalankan perintah ini!"
            else:
                cmd_sample["type"] = "o"
                cmd_sample["desc"] = f"Parameter `{key}` opsional dan bisa diabaikan!"
            if anotasi is not None and "desc" in cmd_sample:
                cmd_sample["desc"] += f"\n`{key}` akan dikonversi ke format `{anotasi}` nanti."
            cmd_opts.append(HelpOption.from_dict(cmd_sample))

        extra_kwargs = {"cmd_name": cmd_info.qualified_name}
        if cmd_info.description:
            extra_kwargs["desc"] = cmd_info.description
        helpcmd = ctx.create_help(**extra_kwargs)
        if len(cmd_opts) > 0:
            helpcmd.add_field(HelpField(cmd_info.qualified_name, options=cmd_opts))
        else:
            helpcmd.add_field(HelpField(cmd_info.qualified_name, "Cukup jalankan perintah ini!"))
        helpcmd.add_aliases(cmd_info.aliases)
        return helpcmd.get()

    @commands.command(name="help", aliases=["bantuan"])
    async def _bbhelp_original_main(self, ctx: naoTimesContext):
        new_h = "Dokumentasi telah dipindah ke website baru!\n"
        new_h += "Silakan kunjungi <https://naoti.me/docs> untuk melihat "
        new_h += "bantuan dan dokumentasi bot!\n\n"
        new_h += f"Untuk melihat bantuan lama, gunakan {self.bot.prefix}oldhelp di DM Bot"
        await ctx.send(new_h)

    @commands.group(name="oldhelp", aliases=["bantuanlama"])
    @commands.dm_only()
    async def _bbhelp(self, ctx: naoTimesContext):
        is_nsfw = False
        if isinstance(ctx.channel, discord.TextChannel):
            is_nsfw = ctx.channel.is_nsfw()
        if ctx.invoked_subcommand is None:
            if not ctx.empty_subcommand(2):
                gen_help = await self._fallback_help(ctx)
                if isinstance(gen_help, discord.Embed):
                    return await ctx.send(embed=gen_help)
                return await ctx.send("Tidak dapat menemukan bantuan perintah tersebut.")
            is_owner = await self.bot.is_owner(ctx.author)
            helpcmd = ctx.create_help(desc=f"Versi {self.bot.semver}")

            helpcmd.add_field(HelpField("help", "Munculkan bantuan perintah"))
            helpcmd.add_field(HelpField("oldhelp", "Munculkan bantuan perintah ini"))
            helpcmd.add_field(
                HelpField("oldhelp showtimes", "Munculkan bantuan perintah berkaitan dengan Showtimes")
            )
            helpcmd.add_field(
                HelpField("oldhelp weebs", "Munculkan bantuan perintah berkaitan dengan Anime/VN/VTuber")
            )
            helpcmd.add_field(HelpField("oldhelp kutubuku", "Munculkan bantuan perintah berkaitan KBBI"))
            helpcmd.add_field(HelpField("oldhelp fun", "Munculkan bantuan yang *menyenangkan*"))
            helpcmd.add_field(
                HelpField(
                    "oldhelp peninjau", "Munculkan berbagai macam perintah yang mengambil data dari Internet."
                )
            )
            helpcmd.add_field(HelpField("oldhelp moderasi", "Munculkan semua perintah moderasi naoTimes."))
            helpcmd.add_field(
                HelpField("oldhelp vote", "Munculkan bantuan perintah untuk voting dan giveaway")
            )
            helpcmd.add_field(HelpField("oldhelp mod", "Munculkan bantuan perintah untuk moderasi peladen"))
            if is_nsfw:
                helpcmd.add_field(HelpField("oldhelp nsfw", "Munculkan bantuan perintah untuk hal NSFW"))
            if is_owner:
                helpcmd.add_field(HelpField("oldhelp owner", "Munculkan bantuan perintah khusus Owner Bot"))
            helpcmd.generate_aliases(["bantuanlama"])
            await ctx.send(embed=helpcmd.get())

    @_bbhelp.error
    async def _bboldhelp_error(self, ctx: naoTimesContext, error: Exception):
        if isinstance(error, commands.PrivateMessageOnly):
            await ctx.send("Mohon gunakan perintah ini di DM Bot!")

    """
    Owner extensions
    """

    @_bbhelp.command(name="owner")
    @commands.is_owner()
    async def _bbhelp_owner(self, ctx: naoTimesContext):
        helpcmd = ctx.create_help("Admin[*]", desc=f"Versi {self.bot.semver}")
        helpcmd.add_field(
            HelpField("load", "Load sebuah module yang ada di Bot", [HelpOption("module", required=True)])
        )
        helpcmd.add_field(
            HelpField("unload", "Unload module yang ada di Bot", [HelpOption("module", required=True)])
        )
        helpcmd.add_field(
            HelpField("reload", "Reload module yang ada di Bot", [HelpOption("module", required=True)])
        )
        helpcmd.add_field(
            HelpField(
                "gprefix",
                "Ubah prefix utama bot",
                [HelpOption(name="prefix", description="Prefix baru untuk bot")],
            )
        )
        await ctx.send(embed=helpcmd.get())

    @_bbhelp.command(name="load")
    @commands.is_owner()
    async def _bbhelp_owner_load(self, ctx: naoTimesContext):
        helpcmd = ctx.create_help("load", desc="Load sebuah module yang ada di Bot")
        helpcmd.add_field(
            HelpField(
                "load",
                options=[HelpOption("module", "`<module>` yang akan di load", required=True)],
                examples=["kutubuku.kbbi", "cogs.kutubuku.kbbi"],
            )
        )
        helpcmd.generate_aliases(add_note=False)
        await ctx.send(embed=helpcmd.get())

    @_bbhelp.command(name="unload")
    @commands.is_owner()
    async def _bbhelp_owner_unload(self, ctx: naoTimesContext):
        helpcmd = ctx.create_help("unload", desc="Unload sebuah module yang ada di Bot")
        helpcmd.add_field(
            HelpField(
                "unload",
                options=[HelpOption("module", "`<module>` yang akan di unload", required=True)],
                examples=["kutubuku.kbbi", "cogs.kutubuku.kbbi"],
            )
        )
        helpcmd.generate_aliases(add_note=False)
        await ctx.send(embed=helpcmd.get())

    @_bbhelp.command(name="reload")
    @commands.is_owner()
    async def _bbhelp_owner_reload(self, ctx: naoTimesContext):
        helpcmd = ctx.create_help("reload", desc="Reload sebuah module yang ada di Bot")
        helpcmd.add_field(
            HelpField(
                "reload",
                options=[HelpOption("module", "`<module>` yang akan di reload", required=True)],
                examples=["kutubuku.kbbi", "cogs.kutubuku.kbbi"],
            )
        )
        helpcmd.generate_aliases(add_note=False)
        await ctx.send(embed=helpcmd.get())

    @_bbhelp.command(name="gprefix")
    @commands.is_owner()
    async def _bbhelp_owner_gprefix(self, ctx: naoTimesContext):
        helpcmd = ctx.create_help("gprefix", desc="Ubah prefix utama bot")
        helpcmd.add_field(
            HelpField(
                "prefix",
                options=[
                    HelpOption("prefix", "`<prefix>` baru yang akan digunakan untuk Bot", required=True)
                ],
                examples=["n!", "c!"],
            )
        )
        helpcmd.generate_aliases(add_note=False)
        await ctx.send(embed=helpcmd.get())

    """
    Showtimes extensions
    """

    @_bbhelp.group(name="showtimes")
    async def _bbhelp_showtimes(self, ctx: naoTimesContext):
        if not ctx.invoked_subcommand:
            if not ctx.empty_subcommand():
                return await ctx.send("Tidak dapat menemukan bantuan perintah tersebut.")
            helpcmd = ctx.create_help("Showtimes[*]", desc=f"Versi {self.bot.prefix}")
            helpcmd.add_field(
                HelpField("oldhelp showtimes user", "Munculkan bantuan perintah Showtimes untuk pengguna")
            )
            helpcmd.add_field(
                HelpField("oldhelp showtimes staff", "Munculkan bantuan perintah Showtimes untuk staff")
            )
            helpcmd.add_field(
                HelpField(
                    "oldhelp showtimes admin", "Munculkan bantuan perintah Showtimes untuk admin peladen"
                )
            )
            helpcmd.add_field(
                HelpField("oldhelp showtimes alias", "Munculkan bantuan perintah Showtimes untuk alias anime")
            )
            helpcmd.add_field(
                HelpField(
                    "oldhelp showtimes kolaborasi",
                    "Munculkan bantuan perintah Showtimes untuk kolaborasi proyek",
                )
            )
            helpcmd.add_field(
                HelpField(
                    "oldhelp showtimes fansubdb",
                    "Munculkan bantuan perintah Showtimes untuk integrasi FansubDB",
                )
            )
            is_owner = await self.bot.is_owner(ctx.author)
            if is_owner:
                helpcmd.add_field(
                    HelpField(
                        "oldhelp showtimes owner", "Munculkan bantuan perintah Showtimes untuk Owner Bot"
                    )
                )
            helpcmd.add_field(HelpField("oldhelp fansubrss", "Munculkan bantuan perintah untuk FansubRSS"))
            await ctx.send(embed=helpcmd.get())

    @staticmethod
    def _showtimes_get_text(switch: str):
        judul_info = "`<judul>` adalah garapan yang "
        judul_info += "terdaftar di database naoTimes."
        judul_info += "\n`<judul>` dapat disingkat sesingkat mungkin."

        posisi_info = "`<posisi>` merupakan salah satu dari 7 posisi ini:\n"
        posisi_info += "```\ntl, tlc, enc, ed, tm, ts, atau qc\n"
        posisi_info += "(Translator, Translation Checker, Encoder, Editor, "
        posisi_info += "Timer, Typesetter, Quality Checker)\n```"

        jumlah_info = "`<jumlah>` adalah total episode yang mau dirilis (dari episode yang terakhir dirilis)\n"  # noqa: E501
        jumlah_info += "Misalkan lagi ngerjain Episode 4, terus mau rilis sampe episode 7\n"  # noqa: E501
        jumlah_info += "Total dari Episode 4 sampai 7 ada 4 (4, 5, 6, 7)\n"
        jumlah_info += "Maka tulis jumlahnya 4"

        switches = {
            "judul": judul_info,
            "posisi": posisi_info,
            "jumlah": jumlah_info,
        }

        return switches.get(switch, "")

    # Showtimes user extensions
    @_bbhelp_showtimes.command(name="user", aliases=["pengguna"])
    async def _bbhelp_showtimes_user(self, ctx: naoTimesContext):
        helpcmd = ctx.create_help(
            "Showtimes User[*]", desc="Perintah-perintah yang dapat digunakan oleh semua pengguna."
        )
        helpcmd.add_field(
            HelpField("tagih", "Melihat progres garapan untuk sebuah anime.", [HelpOption("judul")])
        )
        helpcmd.add_field(HelpField("jadwal", "Melihat jadwal untuk episode selanjutnya untuk musim ini"))
        helpcmd.add_field(
            HelpField(
                "staff",
                "Melihat informasi staff untuk sebuah garapan",
                [HelpOption("judul")],
            )
        )
        await ctx.send(embed=helpcmd.get())

    @_bbhelp.command("tagih", aliases=["blame", "mana"])
    async def _bbhelp_showtimes_user_tagih(self, ctx: naoTimesContext):
        helpcmd = ctx.create_help("tagih", desc="Melihat progres garapan untuk sebuah anime.")
        extra_info = self._showtimes_get_text("judul") + "\n"
        extra_info += "Jika tidak diberikan, akan dilist semua garapan"
        helpcmd.add_field(
            HelpField("tagih", options=[HelpOption("judul", extra_info)], examples=["hitori", "hitoribocchi"])
        )
        helpcmd.generate_aliases(["blame", "mana"])
        await ctx.send(embed=helpcmd.get())

    @_bbhelp.command("jadwal", aliases=["airing"])
    async def _bbhelp_showtimes_user_jadwal(self, ctx: naoTimesContext):
        helpcmd = ctx.create_help("jadwal", desc="Melihat jadwal untuk episode selanjutnya untuk musim ini")
        helpcmd.add_field(HelpField("jadwal"))
        helpcmd.generate_aliases(["airing"])
        await ctx.send(embed=helpcmd.get())

    @_bbhelp.command("staff", aliases=["tukangdelay", "pendelay", "staf"])
    async def _bbhelp_showtimes_user_staff(self, ctx: naoTimesContext):
        helpcmd = ctx.create_help("staff", desc="Melihat informasi staff untuk sebuah garapan")
        extra_info = self._showtimes_get_text("judul") + "\n"
        extra_info += "Jika tidak diberikan, akan dilist semua garapan"
        helpcmd.add_field(
            HelpField("staff", options=[HelpOption("judul", extra_info)], examples=["hitori", "hitoribocchi"])
        )
        helpcmd.generate_aliases(["tukangdelay", "pendelay", "staf"])
        await ctx.send(embed=helpcmd.get())

    # Showtimes staff extensions
    @_bbhelp_showtimes.command(name="staff")
    async def _bbhelp_showtimes_staff(self, ctx: naoTimesContext):
        helpcmd = ctx.create_help(
            "Showtimes Staff[*]", desc="Perintah-perintah yang dapat digunakan oleh staff."
        )

        helpcmd.add_field(
            HelpField(
                "beres",
                "Menandakan posisi garapan episode menjadi beres",
                [HelpOption("posisi", required=True), HelpOption("judul", required=True)],
            )
        )
        helpcmd.add_field(
            HelpField(
                "gakjadi",
                "Menandakan posisi garapan episode mejadi belum selesai",
                [HelpOption("posisi", required=True), HelpOption("judul", required=True)],
            )
        )
        helpcmd.add_field(
            HelpField(
                "tandakan",
                "Mengubah status posisi sebuah garapan menjadi beres atau belum beres",
                [
                    HelpOption("posisi", required=True),
                    HelpOption("episode", required=True),
                    HelpOption("judul", required=True),
                ],
            )
        )
        helpcmd.add_field(
            HelpField(
                "rilis",
                "Merilis garapan!\n*Hanya bisa dipakai oleh Admin atau QCer*",
                [HelpOption("...", required=True)],
            )
        )
        helpcmd.add_field(
            HelpField(
                "batalrilis",
                "Membatalkan rilisan garapan!\n*Hanya bisa dipakai oleh Admin atau QCer*",
                [HelpOption("judul", required=True)],
            )
        )
        await ctx.send(embed=helpcmd.get())

    @_bbhelp.command("beres", aliases=["done"])
    async def _bbhelp_showtimes_staff_beres(self, ctx: naoTimesContext):
        helpcmd = ctx.create_help("beres", desc="Menandakan posisi garapan episode menjadi beres")
        helpcmd.add_field(
            HelpField(
                "beres",
                options=[
                    HelpOption("posisi", self._showtimes_get_text("posisi"), required=True),
                    HelpOption("judul", self._showtimes_get_text("judul"), required=True),
                ],
                examples=["enc hitoribocchi", "ts hitoribocchi"],
            )
        )
        helpcmd.generate_aliases(["done"])
        await ctx.send(embed=helpcmd.get())

    @_bbhelp.command("gakjadi", aliases=["undone", "cancel"])
    async def _bbhelp_showtimes_staff_gakjadi(self, ctx: naoTimesContext):
        helpcmd = ctx.create_help("gakjadi", desc="Menandakan posisi garapan episode mejadi belum selesai")
        helpcmd.add_field(
            HelpField(
                "gakjadi",
                options=[
                    HelpOption("posisi", self._showtimes_get_text("posisi"), required=True),
                    HelpOption("judul", self._showtimes_get_text("judul"), required=True),
                ],
                examples=["enc hitoribocchi", "ts hitoribocchi"],
            )
        )
        helpcmd.generate_aliases(["undone", "cancel"])
        await ctx.send(embed=helpcmd.get())

    @_bbhelp.command("tandakan", aliases=["mark"])
    async def _bbhelp_showtimes_staff_tandakan(self, ctx: naoTimesContext):
        helpcmd = ctx.create_help(
            "tandakan", desc="Mengubah status posisi sebuah garapan menjadi beres atau belum beres"
        )
        helpcmd.add_field(
            HelpField(
                "tandakan",
                options=[
                    HelpOption("posisi", self._showtimes_get_text("posisi"), required=True),
                    HelpOption("episode", "Episode yang ingin ditandakan", required=True),
                    HelpOption("judul", self._showtimes_get_text("judul"), required=True),
                ],
                examples=["enc hitoribocchi", "ts hitoribocchi"],
            )
        )
        helpcmd.generate_aliases(["mark"])
        await ctx.send(embed=helpcmd.get())

    @_bbhelp.command("rilis", aliases=["release"])
    async def _bbhelp_showtimes_staff_rilis(self, ctx: naoTimesContext):
        helpcmd = ctx.create_help("rilis", desc="Merilis garapan!\n*Hanya bisa dipakai oleh Admin atau QCer*")
        helpcmd.add_field(
            HelpField(
                "rilis",
                "Merilis episode garapan yang sedang dikerjakan",
                [HelpOption("judul", self._showtimes_get_text("judul"), True)],
                ["hitoribocchi"],
            )
        )
        helpcmd.add_field(
            HelpField(
                "rilis batch",
                "Merilis beberapa episode sekaligus (dimulai dari episode yang dikerjakan)",
                [
                    HelpOption("jumlah", self._showtimes_get_text("jumlah"), True),
                    HelpOption("judul", self._showtimes_get_text("judul"), True),
                ],
                ["4 hitoribocchi"],
            )
        )
        helpcmd.add_field(
            HelpField(
                "rilis semua",
                "Merilis semua episode yang ada",
                [HelpOption("judul", self._showtimes_get_text("judul"), True)],
                ["hitoribocchi"],
            )
        )
        helpcmd.generate_aliases(["release"])
        await ctx.send(embed=helpcmd.get())

    @_bbhelp.command("batalrilis", aliases=["gakjadirilis", "revert"])
    async def _bbhelp_showtimes_staff_batalrilis(self, ctx: naoTimesContext):
        helpcmd = ctx.create_help(
            "batalrilis", desc="Membatalkan rilisan garapan!\n*Hanya bisa dipakai oleh Admin atau QCer*"
        )
        helpcmd.add_field(
            HelpField(
                "batalrilis",
                options=[HelpOption("judul", self._showtimes_get_text("judul"), required=True)],
                examples=["hitoribocchi"],
            )
        )
        helpcmd.generate_aliases(["gakjadirilis", "revert"])
        await ctx.send(embed=helpcmd.get())

    # Showtimes admin extension
    @_bbhelp_showtimes.command("admin")
    async def _bbhelp_showtimes_admin(self, ctx: naoTimesContext):
        helpcmd = ctx.create_help(
            "Showtimes Admin[*]", desc="Perintah-perintah yang dapat digunakan oleh admin."
        )
        helpcmd.add_field(
            HelpField("ubahdata", "Ubah berbagai macam informasi dan data garapan", [HelpOption("judul")])
        )
        helpcmd.add_field(HelpField("tambahutang", "Tambah garapan baru"))
        helpcmd.add_field(HelpField("showui", "Lihat informasi untuk ShowtimesUI atau naoTimesUI (WebUI)"))
        await ctx.send(embed=helpcmd.get())

    @_bbhelp.command("ubahdata")
    async def _bbhelp_showtimes_admin_ubahdata(self, ctx: naoTimesContext):
        helpcmd = ctx.create_help("ubahdata", desc="Ubah berbagai macam informasi dan data garapan")
        extra_info = self._showtimes_get_text("judul") + "\n"
        extra_info += "Jika tidak diberikan, akan dilist semua garapan"
        helpcmd.add_field(
            HelpField(
                "ubahdata",
                "Anda dapat menambah/menghapus episode, mengubah staff, atau drop garapan",
                [HelpOption("judul", extra_info)],
                ["hitoribocchi"],
            )
        )
        await ctx.send(embed=helpcmd.get())

    @_bbhelp.command("tambahutang", aliases=["addnew"])
    async def _bbhelp_showtimes_admin_tambahutang(self, ctx: naoTimesContext):
        helpcmd = ctx.create_help("tambahutang", desc="Tambah garapan baru ke database Showtimes!")
        helpcmd.add_field(HelpField("tambahutang"))
        helpcmd.add_aliases(["addnew"])
        await ctx.send(embed=helpcmd.get())

    @_bbhelp.command("showui")
    async def _bbhelp_showtimes_admin_showui(self, ctx: naoTimesContext):
        helpcmd = ctx.create_help("showui", desc="Tambah garapan baru ke database Showtimes!")
        help_info = "*Perintah ini akan memperlihatkan password untuk naoTimesUI, hati-hati!*\n"
        help_info += "Anda juga dapat menggunakan via DM bot"
        helpcmd.add_field(
            HelpField(
                "showui",
                help_info,
                [HelpOption("guild_id", "ID peladen, hanya dibutuhkan jika digunakan via DM bot")],
            )
        )
        await ctx.send(embed=helpcmd.get())

    # Showtimes alias extension
    @_bbhelp_showtimes.command("alias")
    async def _bbhelp_showtimes_alias(self, ctx: naoTimesContext):
        helpcmd = ctx.create_help(
            "alias", desc="Perintah-perintah yang digunakan untuk menambah/menghapus alias!"
        )
        helpcmd.add_field(HelpField("alias", "Tambah alias baru untuk sebuah garapan"))
        helpcmd.add_field(
            HelpField(
                "alias list",
                "Lihat alias yang terdaftar untuk garapan",
                [HelpOption("judul", self._showtimes_get_text("judul"), True)],
                ["hitoribocchi"],
            )
        )
        helpcmd.add_field(
            HelpField(
                "alias hapus",
                "Hapus alias untuk sebuah garapan",
                [HelpOption("judul", self._showtimes_get_text("judul"), True)],
                ["hitoribocchi"],
            )
        )
        helpcmd.add_aliases(["alias remove (alias hapus)"])
        await ctx.send(embed=helpcmd.get())

    # Showtimes alias extension
    @_bbhelp_showtimes.group("kolaborasi", aliases=["joint", "join", "koleb"])
    async def _bbhelp_showtimes_kolaborasi(self, ctx: naoTimesContext):
        helpcmd = ctx.create_help(
            "Showtimes Kolaborasi[*]", desc="Perintah-perintah untuk melakukan kolaborasi dengan peladen lain"
        )
        helpcmd.add_field(HelpField("kolaborasi", "Memunculkan bantuan perintah"))
        helpcmd.add_field(
            HelpField(
                "kolaborasi dengan",
                "Inisiasi kolaborasi dengan peladen lain",
                [HelpOption("server_id", required=True), HelpOption("judul", required=True)],
                use_fullquote=True,
            )
        )
        helpcmd.add_field(
            HelpField(
                "kolaborasi konfirmasi",
                "Konfirmasi sebuah ajakan kolaborasi",
                [HelpOption("kode", required=True)],
                use_fullquote=True,
            )
        )
        helpcmd.add_field(
            HelpField(
                "kolaborasi putus",
                "Putuskan kolaborasi yang sedang berlangsung",
                [HelpOption("judul", required=True)],
                use_fullquote=True,
            )
        )
        helpcmd.add_field(
            HelpField(
                "kolaborasi batalkan",
                "Batalkan ajakan konfirmasi",
                [HelpOption("server_id", required=True), HelpOption("kode", required=True)],
                use_fullquote=True,
            )
        )

        helpcmd.add_aliases(["joint", "join", "koleb"])
        await ctx.send(embed=helpcmd.get())

    @_bbhelp_showtimes_kolaborasi.command("dengan", aliases=["with"])
    async def _bbhelp_showtimes_kolaborasi_dengan(self, ctx: naoTimesContext):
        helpcmd = ctx.create_help(
            "kolaborasi dengan", desc="Inisiasi kolaborasi dengan peladen lain untuk sebuah garapan"
        )
        helpcmd.add_field(
            HelpField(
                "kolaborasi dengan",
                options=[
                    HelpOption("server_id", "ID peladen yang ingin anda ajak kolaborasi", True),
                    HelpOption("judul", self._showtimes_get_text("judul"), True),
                ],
                examples=["472705451117641729 hitoribocchi"],
            )
        )
        helpcmd.add_aliases(["kolaborasi with", "joint with", "join with", "koleb with"])
        await ctx.send(embed=helpcmd)

    @_bbhelp_showtimes_kolaborasi.command("konfirmasi", aliases=["confirm"])
    async def _bbhelp_showtimes_kolaborasi_konfirmasi(self, ctx: naoTimesContext):
        helpcmd = ctx.create_help(
            "kolaborasi konfirmasi", desc="Konfirmasi sebuah ajakan kolaborasi dari peladen lain"
        )
        helpcmd.add_field(
            HelpField(
                "kolaborasi konfirmasi",
                options=[HelpOption("kode", "Kode unik yang dibuat dengan `!kolaborasi dengan`", True)],
                examples=["abc123xyz"],
            )
        )
        helpcmd.add_aliases(["kolaborasi confirm", "joint confirm", "join confirm", "koleb confirm"])
        await ctx.send(embed=helpcmd)

    @_bbhelp_showtimes_kolaborasi.command("batalkan")
    async def _bbhelp_showtimes_kolaborasi_batalkan(self, ctx: naoTimesContext):
        helpcmd = ctx.create_help(
            "kolaborasi batalkan", desc="Batalkan sebuah ajakan kolaborasi sebuah garapan"
        )
        helpcmd.add_field(
            HelpField(
                "kolaborasi batalkan",
                options=[
                    HelpOption("server_id", "ID peladen yang ingin anda ajak kolaborasi", True),
                    HelpOption("kode", "Kode unik yang dibuat dengan `!kolaborasi dengan`", True),
                ],
                examples=["472705451117641729 abc123xyz"],
            )
        )
        await ctx.send(embed=helpcmd.get())

    @_bbhelp_showtimes_kolaborasi.command("putus")
    async def _bbhelp_showtimes_kolaborasi_putus(self, ctx: naoTimesContext):
        helpcmd = ctx.create_help("kolaborasi putus", desc="Putuskan kolaborasi sebuah garapan")
        helpcmd.add_field(
            HelpField(
                "kolaborasi putus",
                options=[HelpOption("judul", self._showtimes_get_text("judul"), True)],
                examples=["hitoribocchi"],
            )
        )
        await ctx.send(embed=helpcmd.get())

    """
    Weebs command
    """

    @_bbhelp.command(name="weebs", aliases=["ayaya"])
    async def _bbhelp_weebs(self, ctx: naoTimesContext):
        helpcmd = ctx.create_help("Weebs[*]", desc=f"Versi {self.bot.semver}")
        # animanga.py
        helpcmd.add_fields(
            [
                HelpField("anime", "Melihat informasi sebuah Anime", HelpOption("judul", required=True)),
                HelpField("manga", "Melihat informasi sebuah Manga", HelpOption("judul", required=True)),
                HelpField("tayang", "Melihat jadwal tayang Anime musim ini."),
            ]
        )
        # visualnovel.py
        helpcmd.add_fields(
            [
                HelpField("vn", "Melihat informasi sebuah Visual Novel", HelpOption("judul", required=True)),
                HelpField("randomvn", "Melihat informasi sebuah Visual Novel random"),
            ]
        )
        # vtuber.py
        helpcmd.add_fields(
            [
                HelpField("vtuber", "Melihat bantuan perintah VTuber"),
                HelpField("vtuber live", "Melihat VTuber yang sedang live"),
                HelpField("vtuber jadwal", "Melihat jadwal stream VTuber"),
                HelpField("vtuber channel", "Melihat informasi sebuah channel"),
                HelpField("vtuber grup", "Melihat list grup atau organisasi yang terdaftar"),
            ]
        )
        helpcmd.add_aliases(["ayaya"])
        await ctx.send(embed=helpcmd.get())

    @_bbhelp.command(name="anime", aliases=["animu", "kartun", "ani"])
    async def _bbhelp_anime(self, ctx: naoTimesContext):
        helpcmd = ctx.create_help("anime", "Cari informasi judul Anime melalui Anilist")
        helpcmd.add_field(
            HelpField(
                "anime",
                options=HelpOption(
                    "judul",
                    ANIMANGAVN_HELP,
                    True,
                ),
                examples=["hitoribocchi"],
            )
        )
        helpcmd.embed.add_field(
            name="*Tambahan*",
            value="⏪ **(Selanjutnya)** ⏩ **(Sebelumnya)** "
            "✅ **(Selesai melihat)**\n⏳ **(Waktu Episode selanjutnya)** "
            "👍 **(Melihat Info kembali)**\n"
            "📺 **(Melihat tempat streaming legal)**",
            inline=False,
        )
        helpcmd.add_aliases(["animu", "kartun", "ani"])
        await ctx.send(embed=helpcmd.get())

    @_bbhelp.command(name="manga", aliases=["komik", "mango"])
    async def _bbhelp_manga(self, ctx: naoTimesContext):
        helpcmd = ctx.create_help("manga", "Cari informasi judul Manga melalui Anilist")
        helpcmd.add_field(
            HelpField(
                "manga",
                options=HelpOption(
                    "judul",
                    ANIMANGAVN_HELP,
                    True,
                ),
                examples=["hitoribocchi"],
            )
        )
        helpcmd.embed.add_field(
            name="*Tambahan*",
            value="⏪ **(Selanjutnya)** ⏩ **(Sebelumnya)** "
            "✅ **(Selesai melihat)**\n"
            "👍 **(Melihat Info kembali)**",
            inline=False,
        )
        helpcmd.add_aliases(["komik", "mango"])
        await ctx.send(embed=helpcmd.get())

    @_bbhelp.command(name="tayang")
    async def _bbhelp_tayang(self, ctx: naoTimesContext):
        helpcmd = ctx.create_help("tayang", "Melihat informasi jadwal tayang untuk musim ini.")
        helpcmd.add_field(
            HelpField(
                "tayang",
                "Melihat jadwal tayang dengan listing per sisa hari menuju episode selanjutnya.",
                examples=[""],
            )
        )
        helpcmd.embed.add_field(
            name="*Tamabahan*",
            value="0️⃣ - 🇭 **(Melihat listing per sisa hari)**\n✅ **(Selesai melihat)**",
            inline=False,
        )
        await ctx.send(embed=helpcmd.get())

    @_bbhelp.command(name="vn", aliases=["visualnovel", "eroge", "vndb"])
    async def _bbhelp_vnmain(self, ctx: naoTimesContext):
        helpcmd = ctx.create_help("vn", "Melihat informasi sebuah VN melalui VNDB.")
        helpcmd.add_field(
            HelpField(
                "vn",
                options=HelpOption(
                    "judul",
                    ANIMANGAVN_HELP,
                    True,
                ),
                examples=["steins;gate", "ao no kana"],
            )
        )
        helpcmd.embed.add_field(
            name="*Tambahan*",
            value="⏪ **(Selanjutnya)** ⏩ **(Sebelumnya)** 📸 "
            "**(Melihat screenshot)**\n✅ **(Melihat Info kembali)**",
            inline=False,
        )
        helpcmd.add_aliases(["visualnovel", "eroge", "vndb"])
        await ctx.send(embed=helpcmd.get())

    @_bbhelp.command(name="randomvn", aliases=["randomvisualnovel", "randomeroge", "vnrandom"])
    async def _bbhelp_vnrandom(self, ctx: naoTimesContext):
        helpcmd = ctx.create_help("vn", "Melihat informasi sebuah VN random melalui VNDB.")
        helpcmd.add_field(HelpField("vn", "VN akan dicari dipilih secara random oleh bot menggunakan RNG."))
        helpcmd.embed.add_field(
            name="*Tambahan*",
            value="📸 **(Melihat screenshot)** ✅ **(Melihat Info kembali)**",
            inline=False,
        )
        helpcmd.add_aliases(["randomvisualnovel", "randomeroge", "vnrandom"])
        await ctx.send(embed=helpcmd.get())

    @_bbhelp.group(name="vtuber")
    async def _bbhelp_vtuber(self, ctx: naoTimesContext):
        if ctx.invoked_subcommand is None:
            if not ctx.empty_subcommand():
                return await ctx.send("Tidak dapat menemukan bantuan perintah tersebut.")
            # Return later


def setup(bot: naoTimesBot):
    bot.add_cog(BotBrainHelper(bot))
