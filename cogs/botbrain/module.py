import fnmatch
import logging

import discord
from discord import app_commands
from discord.ext import commands
from discord.ext.commands import (
    ExtensionAlreadyLoaded,
    ExtensionError,
    ExtensionNotFound,
    ExtensionNotLoaded,
)

from naotimes.bot import naoTimesBot
from naotimes.context import OwnerGroup


class BotBrainModuleFunction(commands.Cog):
    modul = OwnerGroup(
        name="modul",
        description=app_commands.locale_str("Kelola modul/cogs bot (owner)", key="botbrain.module.group_description"),
        default_permissions=discord.Permissions(administrator=True),
    )

    def __init__(self, bot: naoTimesBot):
        self.bot = bot
        self.logger = logging.getLogger("BotBrain.Module")

    @staticmethod
    def _full_name(name: str) -> str:
        return name if name.startswith("cogs.") else "cogs." + name

    def match_pattern(self, pattern: str, available_modules: list[str]) -> list[str]:
        if not pattern:
            return []
        available_modules = [m.replace("cogs.", "", 1) for m in available_modules]
        return [m for m in available_modules if fnmatch.fnmatch(m, pattern.replace("cogs.", "", 1))]

    async def _module_autocomplete(self, inter: discord.Interaction, current: str) -> list[app_commands.Choice[str]]:
        all_cogs = [m.replace("cogs.", "", 1) for m in await self.bot.available_extensions()]
        matches = [c for c in all_cogs if current.lower() in c.lower()]
        return [app_commands.Choice(name=m, value=m) for m in matches[:25]]

    @modul.command(
        name="cogmatch",
        description=app_commands.locale_str(
            "Lihat modul yang cocok dengan pola", key="botbrain.module.cogmatch_description"
        ),
    )
    @app_commands.describe(
        pola=app_commands.locale_str(
            "Pola modul, mendukung wildcard (contoh: kutubuku.*)", key="botbrain.module.cogmatch_option"
        )
    )
    async def _bbmod_cogmatch(self, inter: discord.Interaction, pola: str):
        ctx = await self.bot.get_context(inter)
        matched = self.match_pattern(pola, await self.bot.available_extensions())
        text = ctx.t("module.matching") + "\n" + ("\n".join(matched) if matched else ctx.t("module.no_match"))
        await inter.response.send_message(text, ephemeral=True)

    @modul.command(
        name="reload",
        description=app_commands.locale_str(
            "Reload satu atau beberapa modul", key="botbrain.module.reload_description"
        ),
    )
    @app_commands.describe(
        pola=app_commands.locale_str("Nama/pola modul (contoh: kutubuku.*)", key="botbrain.module.reload_option")
    )
    @app_commands.autocomplete(pola=_module_autocomplete)
    async def _bbmod_reload(self, inter: discord.Interaction, pola: str):
        ctx = await self.bot.get_context(inter)
        matched_cogs = self.match_pattern(pola, await self.bot.available_extensions())
        if not matched_cogs:
            return await inter.response.send_message(ctx.t("module.reload_no_match"), ephemeral=True)

        await inter.response.defer(ephemeral=True)
        reloaded_module = []
        for cogs in matched_cogs:
            cogs = self._full_name(cogs)
            self.logger.info(f"Trying to reload {cogs}")
            try:
                await self.bot.reload_extension(cogs)
                reloaded_module.append(cogs)
            except (ExtensionNotFound, ModuleNotFoundError):
                self.logger.warning(f"{cogs} doesn't exist")
            except ExtensionNotLoaded:
                self.logger.warning(f"{cogs} is not loaded yet, trying to load it...")
                try:
                    await self.bot.load_extension(cogs)
                    reloaded_module.append(cogs)
                except (ExtensionNotFound, ModuleNotFoundError):
                    pass
                except ExtensionError as cer:
                    self.logger.error(f"Failed to load {cogs}")
                    self.bot.echo_error(cer)
            except ExtensionError as cef:
                self.logger.error(f"Failed to reload {cogs}")
                self.bot.echo_error(cef)

        if not reloaded_module:
            return await inter.followup.send(ctx.t("module.reload_none"))
        names = ", ".join(f"`{x}`" for x in reloaded_module)
        msg = ctx.t("module.reload_success", names=names)
        if len(reloaded_module) != len(matched_cogs):
            msg += ctx.t("module.reload_partial")
        await inter.followup.send(msg + ctx.t("module.reload_sync_hint"))

    @modul.command(
        name="load",
        description=app_commands.locale_str("Load sebuah modul", key="botbrain.module.load_description"),
    )
    @app_commands.describe(nama=app_commands.locale_str("Nama modul", key="botbrain.module.load_option"))
    @app_commands.autocomplete(nama=_module_autocomplete)
    async def _bbmod_load(self, inter: discord.Interaction, nama: str):
        ctx = await self.bot.get_context(inter)
        cogs = self._full_name(nama)
        self.logger.info(f"Trying to load {cogs}")
        try:
            await self.bot.load_extension(cogs)
        except ExtensionAlreadyLoaded:
            return await inter.response.send_message(ctx.t("module.load_already"), ephemeral=True)
        except (ExtensionNotFound, ModuleNotFoundError):
            return await inter.response.send_message(ctx.t("module.not_found"), ephemeral=True)
        except ExtensionError as cef:
            self.logger.error(f"Failed to load {cogs}")
            self.bot.echo_error(cef)
            return await inter.response.send_message(ctx.t("module.load_failed"), ephemeral=True)
        await inter.response.send_message(ctx.t("module.load_success", name=cogs), ephemeral=True)

    @modul.command(
        name="unload",
        description=app_commands.locale_str("Unload sebuah modul", key="botbrain.module.unload_description"),
    )
    @app_commands.describe(nama=app_commands.locale_str("Nama modul", key="botbrain.module.unload_option"))
    @app_commands.autocomplete(nama=_module_autocomplete)
    async def _bbmod_unload(self, inter: discord.Interaction, nama: str):
        ctx = await self.bot.get_context(inter)
        cogs = self._full_name(nama)
        if cogs == "cogs.botbrain.module":
            return await inter.response.send_message(ctx.t("module.unload_required"), ephemeral=True)
        self.logger.info(f"Trying to unload {cogs}")
        try:
            await self.bot.unload_extension(cogs)
        except ExtensionNotLoaded:
            return await inter.response.send_message(ctx.t("module.unload_not_loaded"), ephemeral=True)
        except (ExtensionNotFound, ModuleNotFoundError):
            return await inter.response.send_message(ctx.t("module.not_found"), ephemeral=True)
        except ExtensionError as cef:
            self.logger.error(f"Failed to unload {cogs}")
            self.bot.echo_error(cef)
            return await inter.response.send_message(ctx.t("module.unload_failed"), ephemeral=True)
        await inter.response.send_message(ctx.t("module.unload_success", name=cogs), ephemeral=True)

    @modul.command(
        name="togglecmd",
        description=app_commands.locale_str(
            "Aktifkan/nonaktifkan sebuah slash command", key="botbrain.module.togglecmd_description"
        ),
    )
    @app_commands.describe(
        perintah=app_commands.locale_str(
            "Nama command (contoh: kbbi atau musik)", key="botbrain.module.togglecmd_option_command"
        ),
        alasan=app_commands.locale_str("Alasan penonaktifan", key="botbrain.module.togglecmd_option_reason"),
    )
    async def _bbmod_toggle_command(self, inter: discord.Interaction, perintah: str, alasan: str | None = None):
        _, message = self.bot.toggle_command(perintah, alasan)
        await inter.response.send_message(message, ephemeral=True)

    @modul.command(
        name="sync",
        description=app_commands.locale_str(
            "Sinkronisasi slash command ke Discord", key="botbrain.module.sync_description"
        ),
    )
    async def _bbmod_slashreload(self, inter: discord.Interaction):
        ctx = await self.bot.get_context(inter)
        await inter.response.defer(ephemeral=True)
        synced = await self.bot.tree.sync()
        await inter.followup.send(ctx.t("module.sync_success", count=len(synced)))


async def setup(bot: naoTimesBot):
    await bot.add_cog(BotBrainModuleFunction(bot))
