import logging

import discord
from discord import app_commands
from discord.ext import commands

from naotimes.bot import naoTimesBot
from naotimes.showtimes import Showtimes
from naotimes.showtimes.slash import load_server, project_autocomplete, resolve_project


class ShowtimesAlias(commands.Cog):
    alias = app_commands.Group(
        name="alias",
        description=app_commands.locale_str("Atur alias garapan fansub", key="showtimes.alias.description"),
        guild_only=True,
    )

    def __init__(self, bot: naoTimesBot):
        self.bot = bot
        self.logger = logging.getLogger("Showtimes.Alias")

    async def _project_auto(self, inter: discord.Interaction, current: str):
        return await project_autocomplete(self.bot, inter, current)

    async def _commit(self, srv_data: Showtimes):
        if self.bot.showqueue is None or self.bot.ntdb is None:
            raise RuntimeError("Showtimes services are unavailable")
        await self.bot.showqueue.add_job(srv_data)
        success, msg = await self.bot.ntdb.update_server(srv_data)
        if not success:
            self.logger.error(f"{srv_data.id}: failed to save to main database: {msg}")
            if srv_data.id not in self.bot.showtimes_resync:
                self.bot.showtimes_resync.append(str(srv_data.id))

    @alias.command(
        name="tambah",
        description=app_commands.locale_str("Tambah alias untuk sebuah garapan (admin)", key="showtimes.alias.tambah"),
    )
    @app_commands.describe(
        judul=app_commands.locale_str("Judul proyek", key="showtimes.options.judul"),
        alias=app_commands.locale_str("Alias yang ingin ditambahkan", key="showtimes.alias.option_alias"),
    )
    async def _showalias_tambah(self, inter: discord.Interaction, judul: str, alias: app_commands.Range[str, 1, 100]):
        ctx = await self.bot.get_context(inter)
        srv_data = await load_server(self.bot, inter)
        if srv_data is None:
            return
        if not srv_data.is_admin(inter.user):
            return await inter.response.send_message(ctx.t("alias.admin_only"), ephemeral=True)
        project, error = await resolve_project(self.bot, srv_data, judul)
        if project is None:
            return await inter.response.send_message(error, ephemeral=True)
        alias = alias.strip()
        if alias.lower() in (a.lower() for a in project.aliases) or alias.lower() == project.title.lower():
            return await inter.response.send_message(ctx.t("alias.exists"), ephemeral=True)

        project.add_alias(alias)
        srv_data.update_project(project)
        await inter.response.send_message(
            ctx.t("alias.added", alias=alias, title=project.title),
            allowed_mentions=discord.AllowedMentions.none(),
        )
        await self._commit(srv_data)

    @alias.command(
        name="list",
        description=app_commands.locale_str("Lihat alias sebuah garapan", key="showtimes.alias.list"),
    )
    @app_commands.describe(judul=app_commands.locale_str("Judul proyek", key="showtimes.options.judul"))
    async def _showalias_list(self, inter: discord.Interaction, judul: str):
        ctx = await self.bot.get_context(inter)
        srv_data = await load_server(self.bot, inter)
        if srv_data is None:
            return
        project, error = await resolve_project(self.bot, srv_data, judul)
        if project is None:
            return await inter.response.send_message(error, ephemeral=True)

        aliases = project.aliases
        value = "\n".join(f"**{i}**. {a}" for i, a in enumerate(aliases, 1)) if aliases else ctx.t("alias.empty")
        embed = discord.Embed(title=ctx.t("alias.list_title"), color=0x47E0A7)
        embed.add_field(name=project.title, value=value[:1024], inline=False)
        embed.set_footer(text=ctx.t("footer.credit"), icon_url="https://p.n4o.xyz/i/nao250px.png")
        await inter.response.send_message(embed=embed)

    @alias.command(
        name="hapus",
        description=app_commands.locale_str("Hapus alias sebuah garapan (admin)", key="showtimes.alias.hapus"),
    )
    @app_commands.describe(
        judul=app_commands.locale_str("Judul proyek", key="showtimes.options.judul"),
        alias=app_commands.locale_str("Alias yang ingin dihapus", key="showtimes.alias.option_alias_hapus"),
    )
    async def _showalias_hapus(self, inter: discord.Interaction, judul: str, alias: str):
        ctx = await self.bot.get_context(inter)
        srv_data = await load_server(self.bot, inter)
        if srv_data is None:
            return
        if not srv_data.is_admin(inter.user):
            return await inter.response.send_message(ctx.t("alias.admin_only"), ephemeral=True)
        project, error = await resolve_project(self.bot, srv_data, judul)
        if project is None:
            return await inter.response.send_message(error, ephemeral=True)
        if not project.aliases:
            return await inter.response.send_message(
                ctx.t("alias.none_for_project", title=project.title), ephemeral=True
            )
        target = next((a for a in project.aliases if a == alias), None)
        if target is None:
            target = next((a for a in project.aliases if a.lower() == alias.lower()), None)
        if target is None:
            return await inter.response.send_message(ctx.t("alias.not_found"), ephemeral=True)

        project.remove_alias(target)
        srv_data.update_project(project)
        await inter.response.send_message(
            ctx.t("alias.deleted", alias=target, title=project.title),
            allowed_mentions=discord.AllowedMentions.none(),
        )
        await self._commit(srv_data)

    @_showalias_hapus.autocomplete("alias")
    async def _showalias_hapus_alias_auto(self, inter: discord.Interaction, current: str):
        judul = getattr(inter.namespace, "judul", None)
        if self.bot.showqueue is None or inter.guild is None:
            return []
        server = await self.bot.showqueue.fetch_database(str(inter.guild.id))
        if server is None or not judul:
            return []
        project = server.get_project(judul) or server.exact_match(judul)
        if project is None:
            return []
        return [
            app_commands.Choice(name=a[:100], value=a[:100]) for a in project.aliases if current.lower() in a.lower()
        ][:25]

    for _cmd in (_showalias_tambah, _showalias_list, _showalias_hapus):
        _cmd.autocomplete("judul")(_project_auto)
    del _cmd


async def setup(bot: naoTimesBot):
    if bot.ntdb is None:
        bot.logger.warning("Owner hasn't enabled naoTimesDB yet, will not load this cogs")
        return
    await bot.add_cog(ShowtimesAlias(bot))
