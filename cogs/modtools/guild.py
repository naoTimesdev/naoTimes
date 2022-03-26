import logging

import disnake
from disnake.ext import commands

from naotimes.bot import naoTimesBot, naoTimesContext
from naotimes.modlog import ModLogFeature, ModLogSetting


class ModToolsGuildControl(commands.Cog):
    def __init__(self, bot: naoTimesBot) -> None:
        self.bot = bot
        self.logger = logging.getLogger("ModTools.GuildControl")

    @commands.command(name="serverlog", aliases=["modlog", "pemantau"])
    @commands.guild_only()
    @commands.has_guild_permissions(manage_guild=True)
    async def _modtools_modlog_feature(self, ctx: naoTimesContext):
        server_data: disnake.Guild = ctx.message.guild
        server_id = server_data.id
        channel_id = ctx.message.channel.id
        original_author = ctx.message.author.id

        self.logger.info(f"{server_id}: initiated server logging...")

        def check_if_author(message: disnake.Message):
            self.logger.info(f"Checking if {original_author} is the same as {message.author.id}")
            return message.author.id == original_author and message.channel.id == channel_id

        def bool_to_stat(tf: bool) -> str:
            return "Aktif" if tf else "Nonaktif"

        metadata_srvlog = {"channel_id": 0, "server_id": server_id, "features": []}
        if not self.bot.has_modlog(server_id):
            channel_msg = await ctx.send(
                "Ketik ID Kanal atau mention Kanal yang ingin dijadikan tempat *logging* peladen.\n"
                "Ketik `cancel` untuk membatalkan."
            )
            self.logger.info(f"{server_id}: no channel set, asking user...")
            while True:
                channel_input: disnake.Message = await self.bot.wait_for("message", check=check_if_author)
                channel_text_data = channel_input.content
                channel_mentions_data = channel_input.channel_mentions
                if channel_text_data == ("cancel"):
                    return await ctx.send("Dibatalkan.")
                if channel_mentions_data:
                    new_channel_id = channel_mentions_data[0].id
                    metadata_srvlog["channel_id"] = new_channel_id
                    await ctx.send_timed(f"Channel berhasil diubah ke: <#{new_channel_id}>", 2)
                    break
                if channel_text_data.isdigit():
                    new_channel_id = int(channel_text_data)
                    if self.bot.get_channel(new_channel_id) is not None:
                        metadata_srvlog["channel_id"] = new_channel_id
                        await ctx.send_timed(f"Channel berhasil diubah ke: <#{new_channel_id}>", 2)
                        await channel_input.delete(no_log=True)
                        break
                    await ctx.send_timed("Tidak dapat menemukan channel tersebut.", 2)
                else:
                    await ctx.send_timed("Channel yang diberikan tidak valid.", 2)
                await channel_input.delete(no_log=True)
            await channel_msg.delete(no_log=True)
        else:
            metadata_srvlog = self.bot.get_modlog(server_id).serialize()

        number_reactions = [
            "1️⃣",
            "2️⃣",
            "3️⃣",
            "4️⃣",
            "5️⃣",
            "6️⃣",
            "7️⃣",
            "🗑️",
            "📜",
            "✅",
            "❌",
        ]

        self.logger.info(f"{server_id}: preparing data...")

        async def _generate_embed(modlog_srv: ModLogSetting) -> disnake.Embed:
            embed = disnake.Embed(title="Pencatatan Peladen", color=0x2D8339)
            embed.description = f"Kanal pencatatan: <#{modlog_srv.channel}>\n`[{modlog_srv.channel}]`"
            embed.add_field(
                name="1️⃣ Pesan (Diubah/Dihapus)",
                value=bool_to_stat(modlog_srv.has_features(ModLogFeature.messages())),
                inline=False,
            )
            embed.add_field(
                name="2️⃣ Pengguna (Gabung/Keluar)",
                value=bool_to_stat(modlog_srv.has_features(ModLogFeature.joinleave())),
                inline=False,
            )
            embed.add_field(
                name="3️⃣ Ban (Ban/Unban/Shadowban/Unshadowban)",
                value=bool_to_stat(modlog_srv.has_features(ModLogFeature.bans())),
                inline=False,
            )
            embed.add_field(
                name="4️⃣ Nickname (Diubah)",
                value=bool_to_stat(modlog_srv.has_features(ModLogFeature.NICK_MEMUPDATE)),
                inline=False,
            )
            embed.add_field(
                name="5️⃣ Roles (Diubah)",
                value=bool_to_stat(modlog_srv.has_features(ModLogFeature.ROLE_MEMUPDATE)),
                inline=False,
            )
            embed.add_field(
                name="6️⃣ Kanal (Buat/Hapus)",
                value=bool_to_stat(modlog_srv.has_features(ModLogFeature.channels())),
                inline=False,
            )
            embed.add_field(
                name="7️⃣ Thread (Buat/Hapus/Perubahan)",
                value=bool_to_stat(modlog_srv.has_features(ModLogFeature.threads())),
                inline=False,
            )
            server_ikon = None
            if server_data.icon:
                server_ikon = str(server_data.icon)
            embed.add_field(name="🗑️ Matikan", value="Matikan Pencatatan Peladen", inline=False)
            embed.add_field(name="📜 Aktifkan Semua", value="Aktifkan Semua Pencatatan Peladen", inline=True)
            embed.add_field(name="✅ Simpan", value="Simpan perubahan.", inline=False)
            embed.add_field(name="❌ Batalkan", value="Batalkan perubahan.", inline=True)
            embed.set_author(name=server_data.name, icon_url=server_ikon)
            if server_ikon is not None:
                embed.set_thumbnail(url=server_ikon)
            return embed

        first_run = True
        cancelled = False
        deletion_from_data = False
        emb_msg: disnake.Message
        self.logger.info(f"{server_id}: starting data modifying...")
        while True:
            embed = await _generate_embed(ModLogSetting.from_dict(metadata_srvlog))
            if first_run:
                first_run = False
                emb_msg = await ctx.send(embed=embed)
            else:
                await emb_msg.edit(embed=embed)

            def base_check_react(reaction: disnake.Reaction, user: disnake.Member):
                if reaction.message.id != emb_msg.id:
                    return False
                if user != ctx.message.author:
                    return False
                if str(reaction.emoji) not in number_reactions:
                    return False
                return True

            for react in number_reactions:
                await emb_msg.add_reaction(react)

            res: disnake.Reaction
            user: disnake.Member
            res, user = await self.bot.wait_for("reaction_add", check=base_check_react)
            if user != ctx.message.author:
                pass
            elif "✅" in str(res.emoji):
                await emb_msg.clear_reactions()
                break
            elif "❌" in str(res.emoji):
                await emb_msg.clear_reactions()
                cancelled = True
                break
            elif "🗑️" in str(res.emoji):
                await emb_msg.clear_reactions()
                deletion_from_data = True
                break
            elif "📜" in str(res.emoji):
                await emb_msg.clear_reactions()
                metadata_srvlog["features"] = list(map(lambda x: x.value, ModLogFeature.all()))
            else:
                index_n = number_reactions.index(str(res.emoji))
                if index_n == 0:
                    new_features = list(map(lambda x: x.value, ModLogFeature.messages()))
                    exist = False
                    features_sets = metadata_srvlog["features"]
                    for feature in features_sets:
                        if feature in new_features:
                            exist = True
                    if exist:
                        features_sets = list(filter(lambda x: x not in new_features, features_sets))
                    else:
                        features_sets = list(filter(lambda x: x not in new_features, features_sets))
                        features_sets.extend(new_features)
                    metadata_srvlog["features"] = features_sets
                elif index_n == 1:
                    new_features = list(map(lambda x: x.value, ModLogFeature.joinleave()))
                    exist = False
                    features_sets = metadata_srvlog["features"]
                    for feature in features_sets:
                        if feature in new_features:
                            exist = True
                    if exist:
                        features_sets = list(filter(lambda x: x not in new_features, features_sets))
                    else:
                        features_sets = list(filter(lambda x: x not in new_features, features_sets))
                        features_sets.extend(new_features)
                    metadata_srvlog["features"] = features_sets
                elif index_n == 2:
                    new_features = list(map(lambda x: x.value, ModLogFeature.bans()))
                    exist = False
                    features_sets = metadata_srvlog["features"]
                    for feature in features_sets:
                        if feature in new_features:
                            exist = True
                    if exist:
                        features_sets = list(filter(lambda x: x not in new_features, features_sets))
                    else:
                        features_sets = list(filter(lambda x: x not in new_features, features_sets))
                        features_sets.extend(new_features)
                    metadata_srvlog["features"] = features_sets
                elif index_n == 3:
                    features_sets = metadata_srvlog["features"]
                    if ModLogFeature.NICK_MEMUPDATE.value in features_sets:
                        features_sets.remove(ModLogFeature.NICK_MEMUPDATE.value)
                    else:
                        features_sets.append(ModLogFeature.NICK_MEMUPDATE.value)
                    metadata_srvlog["features"] = features_sets
                elif index_n == 4:
                    features_sets = metadata_srvlog["features"]
                    if ModLogFeature.ROLE_MEMUPDATE.value in features_sets:
                        features_sets.remove(ModLogFeature.ROLE_MEMUPDATE.value)
                    else:
                        features_sets.append(ModLogFeature.ROLE_MEMUPDATE.value)
                    metadata_srvlog["features"] = features_sets
                elif index_n == 5:
                    new_features = list(map(lambda x: x.value, ModLogFeature.channels()))
                    exist = False
                    features_sets = metadata_srvlog["features"]
                    for feature in features_sets:
                        if feature in new_features:
                            exist = True
                    if exist:
                        features_sets = list(filter(lambda x: x not in new_features, features_sets))
                    else:
                        features_sets = list(filter(lambda x: x not in new_features, features_sets))
                        features_sets.extend(new_features)
                    metadata_srvlog["features"] = features_sets
                elif index_n == 6:
                    new_features = list(map(lambda x: x.value, ModLogFeature.threads()))
                    exist = False
                    features_sets = metadata_srvlog["features"]
                    for feature in features_sets:
                        if feature in new_features:
                            exist = True
                    if exist:
                        features_sets = list(filter(lambda x: x not in new_features, features_sets))
                    else:
                        features_sets = list(filter(lambda x: x not in new_features, features_sets))
                        features_sets.extend(new_features)
                    metadata_srvlog["features"] = features_sets
                await emb_msg.clear_reactions()

        if cancelled:
            return await ctx.send("Dibatalkan.")
        if deletion_from_data:
            self.logger.warning(f"{server_id}: removing from server logging.")
            await self.bot.remove_modlog(server_id)
            return await ctx.send("Berhasil menghapus peladen ini dari fitur pencatatan.")

        await emb_msg.delete()

        modlog_ft = ModLogSetting.from_dict(metadata_srvlog)
        self.logger.info(f"{server_id}: saving data...")
        await self.bot.update_modlog(server_id, modlog_ft)
        await ctx.send("Pencatatan peladen berhasil diatur.")

        bot_data: disnake.Member = server_data.get_member(self.bot.user.id)
        bot_perms: disnake.Permissions = bot_data.guild_permissions
        if not bot_perms.view_audit_log and modlog_ft.has_features(ModLogFeature.DELETE_MSG):
            await ctx.send(
                "Bot tidak ada akses `View Audit Log` sementara fitur pencatatan pesan diaktifkan.\n"
                "Mohon berikan bot akses `View Audit Log` agar fitur dapat bekerja dengan normal."
            )


def setup(bot: naoTimesBot):
    bot.add_cog(ModToolsGuildControl(bot))
