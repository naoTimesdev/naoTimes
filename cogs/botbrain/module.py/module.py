import fnmatch
import logging
from typing import List

from discord.ext import commands
from discord.ext.commands import ExtensionAlreadyLoaded, ExtensionError, ExtensionNotFound, ExtensionNotLoaded

from naotimes.bot import naoTimesBot, naoTimesContext


class BotBrainModuleFunction(commands.Cog):
    def __init__(self, bot: naoTimesBot):
        self.bot = bot
        self.logger = logging.getLogger("BotBrain.Module")

    def match_pattern(self, pattern: str, available_modules: List[str]) -> List[str]:
        if pattern.startswith("cogs."):
            return pattern.replace("cogs.", "")
        if not pattern:
            return []
        available_modules = list(map(lambda x: x.replace("cogs.", ""), available_modules))
        return list(filter(lambda x: fnmatch.fnmatch(x, pattern), available_modules))

    @commands.command(name="cogmatch")
    @commands.is_owner()
    async def _bbmod_cogmatch(self, ctx: naoTimesContext, *, cogs: str):
        matched = self.match_pattern(cogs, await self.bot.available_extensions())
        text = "Matching cogs:\n"
        if matched:
            text += "\n".join(matched)
        else:
            text += "No match!"
        await ctx.send(text)

    @commands.command(name="reload")
    @commands.is_owner()
    async def _bbmod_reload(self, ctx: naoTimesContext, *, cog_match: str = None):
        ALL_COGS = await self.bot.available_extensions()
        if not cog_match:
            helpcmd = self.bot.create_help(ctx, "Reload", desc="Reload a bot module")
            helpcmd.embed.add_field(
                name="Module/Cogs list", value="\n".join(["- " + cl for cl in ALL_COGS]), inline=False
            )
            return await ctx.send(embed=helpcmd.get())

        matched_cogs = self.match_pattern(cog_match, ALL_COGS)
        if not matched_cogs:
            return await ctx.send("No match found!")

        reloaded_module = []
        msg = await ctx.send(f"Please wait, reloading {len(matched_cogs)} module...")
        for cogs in matched_cogs:
            if not cogs.startswith("cogs."):
                cogs = "cogs." + cogs
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
                except (ExtensionNotFound, ModuleNotFoundError):
                    pass
                except ExtensionError as cer:
                    self.logger.error(f"Failed to load {cogs}")
                    self.bot.echo_error(cer)
            except ExtensionError as cef:
                self.logger.error(f"Failed to reload {cogs}")
                self.bot.echo_error(cef)

        if not reloaded_module:
            await msg.edit(content="No module reloaded, what the hell?")
        else:
            reloaded_module = list(map(lambda x: f"`{x}`", reloaded_module))
            await msg.edit(content=f"Successfully (re)loaded {', '.join(reloaded_module)} modules.")
            if len(reloaded_module) != len(matched_cogs):
                await msg.edit(content="But some modules failed to reload, check the logs.")

    @commands.command(name="load")
    @commands.is_owner()
    async def _bbmod_load(self, ctx: naoTimesContext, *, cogs: str = None):
        if not cogs:
            ALL_COGS = await self.bot.available_extensions()
            helpcmd = self.bot.create_help(ctx, "Load", desc="Load a bot module")
            helpcmd.embed.add_field(
                name="Module/Cogs list", value="\n".join(["- " + cl for cl in ALL_COGS]), inline=False
            )
            return await ctx.send(embed=helpcmd.get())

        if not cogs.startswith("cogs."):
            cogs = "cogs." + cogs
        self.logger.info(f"Trying to load {cogs}")
        msg = await ctx.send("Please wait, loading module...")

        try:
            await self.bot.load_extension(cogs)
        except ExtensionAlreadyLoaded:
            self.logger.warning(f"{cogs} already loaded")
            return await msg.edit(content="The module is already loaded!")
        except (ExtensionNotFound, ModuleNotFoundError):
            self.logger.warning(f"{cogs} doesn't exist")
            return await msg.edit(content="Unable to find that module!")
        except ExtensionError as cef:
            self.logger.error(f"Failed to load {cogs}")
            self.bot.echo_error(cef)
            return await msg.edit(content="Failed to load module, please check bot log!")

        await msg.edit(content=f"Successfully loaded `{cogs}` module.")

    @commands.command(name="unload")
    async def _bbmod_unload(self, ctx: naoTimesContext, *, cogs: str = None):
        if not cogs:
            ALL_COGS = await self.bot.available_extensions()
            helpcmd = self.bot.create_help(ctx, "Unload", desc="Unload a bot module")
            helpcmd.embed.add_field(
                name="Module/Cogs list", value="\n".join(["- " + cl for cl in ALL_COGS]), inline=False
            )
            return await ctx.send(embed=helpcmd.get())

        if not cogs.startswith("cogs."):
            cogs = "cogs." + cogs
        self.logger.info(f"Trying to load {cogs}")
        msg = await ctx.send("Please wait, unloading module...")

        try:
            await self.bot.unload_extension(cogs)
        except ExtensionNotLoaded:
            self.logger.warning(f"{cogs} already unloaded")
            return await msg.edit(content="The module is not yet loaded! (already unloaded)")
        except (ExtensionNotFound, ModuleNotFoundError):
            self.logger.warning(f"{cogs} doesn't exist")
            return await msg.edit(content="Unable to find that module!")
        except ExtensionError as cef:
            self.logger.error(f"Failed to reload {cogs}")
            self.bot.echo_error(cef)
            return await msg.edit(content="Failed to unload module, please check bot log!")

        await msg.edit(content=f"Successfully unloaded `{cogs}` module.")

    @commands.command(name="togglecmd")
    @commands.is_owner()
    async def _bbmod_toggle_command(self, ctx: naoTimesContext, *, command_name: str):
        """Toggle a command status (disable/enable)"""
        try:
            split_data = command_name.split("-", 1)
            command_name = split_data[0]
            reasoning = split_data[1]
        except ValueError:
            reasoning = None

        result, error_msg = self.bot.toggle_command(command_name, reasoning)
        if not result:
            error_msg = "Error: " + error_msg
        await ctx.send(error_msg)

    @commands.command(name="nappsync")
    @commands.is_owner()
    async def _bbmod_slashreload(self, ctx: naoTimesContext):
        msg = await ctx.send("Syncing naoTimes app...")
        await self.bot.tree.sync()
        await msg.edit(content="Sync naoTimes app done!")


async def setup(bot: naoTimesBot):
    await bot.add_cog(BotBrainModuleFunction(bot))
