import logging

import discord
from discord.ext import commands

from naotimes.bot import naoTimesBot
from naotimes.modlog import ModLog, ModLogAction, ModLogFeature


class ModLogChannel(commands.Cog):
    def __init__(self, bot: naoTimesBot) -> None:
        self.bot = bot
        self.logger = logging.getLogger("modlog.ChannelLog")

    def _generate_log(self, action: ModLogAction, data: dict) -> ModLog:
        current_time = self.bot.now()
        mod_log = ModLog(action=action, timestamp=current_time)
        guild_info = data.get("guild", None)

        if action == ModLogAction.CHANNEL_CREATE:
            embed = discord.Embed(
                title="#️⃣ Kanal dibuat",
                color=discord.Color.from_rgb(63, 154, 115),
                timestamp=current_time.datetime,
            )
            description = []
            description.append(f"**• Nama**: #{data['name']}")
            description.append(f"**• ID Kanal**: {data['id']} (<#{data['id']}>)")
            description.append(f"**• Tipe**: {data['type']}")
            description.append(f"**• Posisi**: {data['position'] +1}")
            description.append(f"**• Di kategori**: {data['category']}")
            embed.description = "\n".join(description)
            embed.set_footer(text="🏗 Kanal baru")
            if guild_info is not None:
                if guild_info["icon"] is not None:
                    embed.set_thumbnail(url=guild_info["icon"])
                embed.set_author(name=guild_info["name"], icon_url=guild_info["icon"])
            mod_log.embed = embed
        elif action == ModLogAction.CHANNEL_DELETE:
            embed = discord.Embed(
                title="#️⃣ Kanal dihapus",
                color=discord.Color.from_rgb(163, 68, 54),
                timestamp=current_time.datetime,
            )
            description = []
            description.append(f"**• Nama**: #{data['name']}")
            description.append(f"**• ID Kanal**: {data['id']}")
            description.append(f"**• Tipe**: {data['type']}")
            description.append(f"**• Posisi**: {data['position'] +1}")
            description.append(f"**• Di kategori**: {data['category']}")
            embed.description = "\n".join(description)
            embed.set_footer(text="💣 Kanal dihapus")
            if guild_info is not None:
                if guild_info["icon"] is not None:
                    embed.set_thumbnail(url=guild_info["icon"])
                embed.set_author(name=guild_info["name"], icon_url=guild_info["icon"])
            mod_log.embed = embed
        return mod_log

    @staticmethod
    def _determine_channel_type(channel: discord.abc.GuildChannel):
        if isinstance(channel, discord.TextChannel):
            if channel.is_news():
                return "📢 Kanal berita/pengumuman"
            return "💬 Kanal teks"
        elif isinstance(channel, discord.VoiceChannel):
            return "🔉 Kanal suara"
        elif isinstance(channel, discord.StageChannel):
            return "🎬 Kanal panggung"
        return None

    @commands.Cog.listener("on_guild_channel_create")
    async def _modlog_channel_create(self, channel: discord.abc.GuildChannel) -> None:
        should_log, server_setting = self.bot.should_modlog(channel, features=[ModLogFeature.CHANNEL_CREATE])
        if not should_log:
            return

        determine = self._determine_channel_type(channel)
        if determine is None:
            return
        guild: discord.Guild = channel.guild

        ikon_guild = guild.icon
        if ikon_guild is not None:
            ikon_guild = str(ikon_guild)

        details = {
            "type": determine,
            "name": channel.name,
            "id": channel.id,
            "position": channel.position,
            "category": channel.category.name if channel.category is not None else "*Tidak ada*",
            "guild": {"name": guild.name, "icon": ikon_guild},
        }

        modlog = self._generate_log(ModLogAction.CHANNEL_CREATE, details)
        await self.bot.add_modlog(modlog, server_setting)

    @commands.Cog.listener("on_guild_channel_delete")
    async def _modlog_channel_delete(self, channel: discord.abc.GuildChannel) -> None:
        should_log, server_setting = self.bot.should_modlog(channel, features=[ModLogFeature.CHANNEL_DELETE])
        if not should_log:
            return

        determine = self._determine_channel_type(channel)
        if determine is None:
            return
        guild: discord.Guild = channel.guild

        ikon_guild = guild.icon
        if ikon_guild is not None:
            ikon_guild = str(ikon_guild)

        details = {
            "type": determine,
            "name": channel.name,
            "id": channel.id,
            "position": channel.position,
            "category": channel.category.name if channel.category is not None else "*Tidak ada*",
            "guild": {"name": guild.name, "icon": ikon_guild},
        }

        modlog = self._generate_log(ModLogAction.CHANNEL_DELETE, details)
        await self.bot.add_modlog(modlog, server_setting)


async def setup(bot: naoTimesBot):
    await bot.add_cog(ModLogChannel(bot))
