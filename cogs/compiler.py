import logging
import random
import re
from datetime import datetime, timezone
from string import ascii_lowercase

import aiohttp
import discord
from discord.ext import commands

from nthelper.bot import naoTimesBot
from nthelper.cpputest import (
    CPPTestCompileError,
    CPPTestRuntimeError,
    CPPTestSanitizeError,
    CPPTestTimeoutError,
    CPPUnitTester,
)


def setup(bot):
    bot.add_cog(CPPCompiler(bot))


class CPPCompiler(commands.Cog):
    def __init__(self, bot: naoTimesBot):
        self.bot = bot
        self.reblocks = re.compile(r"```[a-zA-Z0-9+\-]*\n(?P<codes>[\s\S]*?)\n```")
        self.logger = logging.getLogger("cogs.compiler.CPPCompiler")

    async def paste_to_ihacdn(self, text_to_send: str) -> str:
        async with aiohttp.ClientSession(
            headers={"User-Agent": f"naoTimes/v{self.bot.semver} (https://github.com/noaione/naoTimes)"}
        ) as session:
            current = str(datetime.now(tz=timezone.utc).timestamp())
            form_data = aiohttp.FormData()
            form_data.add_field(
                name="file",
                value=text_to_send.encode("utf-8"),
                content_type="text/x-c",
                filename=f"naoTimes_CPP_Unit_Test{current}.cpp",
            )
            async with session.post("https://p.ihateani.me/upload", data=form_data) as resp:
                if resp.status == 200:
                    res = await resp.text()
                    return res

    @commands.command(name="compile")
    async def compile_code(self, ctx):
        server_message = str(ctx.message.guild.id)
        self.logger.info(f"requested at {server_message}")

        embed = discord.Embed(title="C++ Compiler", color=0x82B5F1)
        embed.description = "Compile C++ code at your own comfy discord server."
        embed.add_field(name="Enter Code", value="Please enter your code (with code blocks/not", inline=False)
        embed.add_field(name="Limitation", value="20s max, no system() support.", inline=False)
        embed.set_footer(text="C++@Discord")
        emb_msg = await ctx.send(embed=embed)

        c_table = {"code_blocks": "", "code_input": []}

        msg_author = ctx.message.author

        def check_if_author(m):
            return m.author == msg_author

        async def process_code_blocks(table, emb_msg):
            self.logger.info(f"{server_message}: processing code blocks...")
            embed = discord.Embed(title="C++ Compiler", color=0x82B5F1)
            embed.description = "Compile C++ code at your own comfy discord server."
            embed.add_field(
                name="Enter Code", value="Please enter your code (with code blocks/not", inline=False
            )
            embed.add_field(name="Limitation", value="20s max, no system() support.", inline=False)
            embed.set_footer(text="C++@Discord")
            await emb_msg.edit(embed=embed)

            while True:
                await_msg = await self.bot.wait_for("message", check=check_if_author)

                code_blocks = await_msg.clean_content

                if "```" in code_blocks:
                    code_blocked = re.match(self.reblocks, code_blocks)
                    if code_blocked:
                        code_blocks_temp = code_blocked.group("codes")
                        if code_blocks_temp:
                            code_blocks = code_blocks_temp
                await await_msg.delete()
                break

            embed = discord.Embed(title="C++ Compiler", color=0x82B5F1)
            embed.description = "Compile C++ code at your own comfy discord server."
            embed.add_field(
                name="Is this correct?", value=f"```cpp\n{code_blocks}\n```", inline=False,
            )
            embed.set_footer(text="C++@Discord")

            await emb_msg.edit(embed=embed)

            to_react = ["✅", "❌"]
            for reaction in to_react:
                await emb_msg.add_reaction(reaction)

            def check_react(reaction, user):
                if reaction.message.id != emb_msg.id:
                    return False
                if user != ctx.message.author:
                    return False
                if str(reaction.emoji) not in to_react:
                    return False
                return True

            while True:
                res, user = await self.bot.wait_for("reaction_add", check=check_react)
                if user != ctx.message.author:
                    pass
                elif "✅" in str(res.emoji):
                    table["code_blocks"] = code_blocks
                    await emb_msg.clear_reactions()
                    return table, emb_msg
                elif "❌" in str(res.emoji):
                    await emb_msg.clear_reactions()
                    return False, "Dibatalkan oleh user."

        async def give_input(table, emb_msg):
            self.logger.info(f"{server_message}: processing input data...")
            rand_exit_code = "".join([random.choice(ascii_lowercase) for _ in range(8)])  # nosec
            embed = discord.Embed(title="C++ Compiler", color=0xF182CA)
            embed.description = "Compile C++ code at your own comfy discord server."
            embed.add_field(
                name="Enter Input",
                value=f"Enter: `blank_{rand_exit_code}` to set input to blank.",
                inline=False,
            )
            embed.set_footer(text="C++@Discord")
            await emb_msg.edit(embed=embed)

            while True:
                await_msg = await self.bot.wait_for("message", check=check_if_author)

                input_data = await_msg.content
                if input_data == f"blank_{rand_exit_code}":
                    table["code_input"] = []
                    await await_msg.delete()
                    break
                input_data = [ind.rstrip() for ind in input_data.split("\n") if ind]
                table["code_input"] = input_data
                await await_msg.delete()
                break
            return table, emb_msg

        c_table, emb_msg = await process_code_blocks(c_table, emb_msg)
        if not c_table:
            self.logger.warning(f"{server_message}: process cancelled")
            return await ctx.send(emb_msg)
        c_table, emb_msg = await give_input(c_table, emb_msg)

        self.logger.info(f"{server_message}: checkpoint before doing shit")
        first_time = True
        cancel_toggled = False
        while True:
            embed = discord.Embed(
                title="C++ Compiler", description="Periksa data!\nReact jika ingin diubah.", color=0xCB82F1,
            )
            embed.add_field(
                name="1⃣ Codes", value="```cpp\n{}\n```".format(c_table["code_blocks"]), inline=False,
            )
            embed.add_field(
                name="2⃣ Input Data",
                value="```\n{}\n```".format("\n".join(c_table["code_input"]))
                if c_table["code_input"]
                else "Tidak ada.",
                inline=False,
            )
            embed.set_footer(text="C++@Discord")

            if first_time:
                await emb_msg.delete()
                emb_msg = await ctx.send(embed=embed)
                first_time = False
            else:
                await emb_msg.edit(embed=embed)

            to_react = [
                "1⃣",
                "2⃣",
                "✅",
                "❌",
            ]
            for reaction in to_react:
                await emb_msg.add_reaction(reaction)

            def check_react(reaction, user):
                if reaction.message.id != emb_msg.id:
                    return False
                if user != ctx.message.author:
                    return False
                if str(reaction.emoji) not in to_react:
                    return False
                return True

            res, user = await self.bot.wait_for("reaction_add", check=check_react)
            if user != ctx.message.author:
                pass
            elif to_react[0] in str(res.emoji):
                await emb_msg.clear_reactions()
                c_table, emb_msg = await process_code_blocks(c_table, emb_msg)
            elif to_react[1] in str(res.emoji):
                await emb_msg.clear_reactions()
                c_table, emb_msg = await give_input(c_table, emb_msg)
            elif "✅" in str(res.emoji):
                await emb_msg.clear_reactions()
                break
            elif "❌" in str(res.emoji):
                self.logger.warning(f"{server_message}: process cancelled")
                cancel_toggled = True
                await emb_msg.clear_reactions()
                break

        if cancel_toggled:
            return await ctx.send("**Dibatalkan!**")

        self.logger.info(f"{server_message}: compiling code...")
        embed = discord.Embed(title="C++ Compiler", color=0xCFD453)
        embed.description = "Compiling code..."
        embed.set_footer(text="C++@Discord")
        await emb_msg.edit(embed=embed)
        cpp_tc = CPPUnitTester(c_table["code_blocks"], c_table["code_input"])
        try:
            await cpp_tc.save_and_compile()
        except CPPTestSanitizeError as ctserr:
            await cpp_tc.cleanup_data()
            embed = discord.Embed(title="C++ Compiler", color=0xB62626)
            embed.add_field(name="Sanitization Error!", value="```cpp\n{}\n```".format(ctserr))
            embed.set_footer(text="C++@Discord")
            await emb_msg.edit(embed=embed)
            return
        except CPPTestCompileError as ctcerr:
            await cpp_tc.cleanup_data()
            embed = discord.Embed(title="C++ Compiler", color=0xB62626)
            if len(str(ctcerr)) > 1000:
                hasted = await self.paste_to_ihacdn(str(ctcerr))
                embed.add_field(
                    name="Failed to compile!",
                    value="Since the error log is way too long, " f"here's Hastebin dump\n{hasted}",
                )
            else:
                embed.add_field(name="Failed to compile!", value="```cpp\n{}\n```".format(ctcerr))
            embed.set_footer(text="C++@Discord")
            await emb_msg.edit(embed=embed)
            return

        embed = discord.Embed(title="C++ Compiler", color=0xCFD453)
        embed.description = "Running code..."
        embed.set_footer(text="C++@Discord")
        await emb_msg.edit(embed=embed)

        self.logger.info(f"{server_message}: running code...")
        try:
            err_code, out_shit, time_taken = await cpp_tc.run_code()
            if isinstance(out_shit, list):
                out_shit = "\n".join(out_shit)
            embed = discord.Embed(title="C++ Compiler", color=0x7BD453)
            embed.description = f"Time taken: {time_taken}ms"
            if len(out_shit) > 1000:
                hasted = await self.paste_to_ihacdn(out_shit)
                embed.add_field(
                    name="Output",
                    value="Since the output is way too long, " f"here's Hastebin dump\n{hasted}",
                )
            else:
                embed.add_field(name="Output", value="```\n{}\n```".format(out_shit))
            embed.set_footer(text=f"C++@Discord (Code: {err_code})")
            await emb_msg.edit(embed=embed)
            await cpp_tc.cleanup_data()
            return
        except CPPTestRuntimeError as ctrerr:
            await cpp_tc.cleanup_data()
            embed = discord.Embed(title="C++ Compiler", color=0xB62626)
            if len(str(ctrerr)) > 1000:
                hasted = await self.paste_to_ihacdn(str(ctrerr))
                embed.add_field(
                    name="Runtime Error!",
                    value="Since the error log is way too long, " f"here's Hastebin dump\n{hasted}",
                )
            else:
                embed.add_field(name="Runtime Error!", value="```cpp\n{}\n```".format(ctrerr))
            embed.set_footer(text="C++@Discord")
            await emb_msg.edit(embed=embed)
            return
        except CPPTestTimeoutError as ctterr:
            await cpp_tc.cleanup_data()
            embed = discord.Embed(title="C++ Compiler", color=0xB62626)
            embed.add_field(name="Timeout Error!", value="{}".format(ctterr))
            embed.set_footer(text="C++@Discord")
            await emb_msg.edit(embed=embed)
            return
