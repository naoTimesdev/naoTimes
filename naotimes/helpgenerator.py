"""
A simple !help command generator.
This will help design how the help command will be generated.

---

MIT License

Copyright (c) 2019-2021 naoTimesdev

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
"""

import logging
from typing import Dict, List, NamedTuple, Union

import discord
from discord.ext import commands

from .utils import bold, quote

__all__ = ("HelpField", "HelpGenerator", "HelpOption")


class HelpOption(NamedTuple):
    name: str
    description: str = None
    required: bool = False

    @classmethod
    def from_dict(cls, data: dict):
        name = data["name"]
        description = data.get("desc")
        meta_type = data.get("type", "o")
        is_required = False
        if meta_type == "r":
            is_required = True
        return cls(name, description, is_required)


class HelpField:
    def __init__(
        self,
        name: str,
        description: str = None,
        options: Union[HelpOption, List[HelpOption]] = None,
        examples: List[str] = [],
        inline: bool = False,
        use_fullquote: bool = False,
    ):
        self.name = name
        self.description = description
        if options is None:
            options = []
        if isinstance(options, HelpOption):
            options = [options]
        self._options = options
        self.examples = examples
        self.inline = inline
        self.use_fullquote = use_fullquote

    @property
    def options(self) -> List[HelpOption]:
        return self._options

    @options.setter
    def options(self, option: Union[HelpOption, List[HelpOption]]):
        if isinstance(option, HelpOption):
            self._options.append(option)
        elif isinstance(option, list):
            self._options = option


class HelpGenerator:
    """A class to generate a help
    -----

    Example:
    ```
    # Assuming this is on a async function of a command
    helpcmd = HelpGenerator(bot, ctx, "add", desc="do an addition")
    await helpcmd.generate_field(
        "add"
        [
            {"name": "num1", "type": "r"},
            {"name": "num2", "type": "r"},
        ],
        desc="Do an addition between `num1` and `num2`",
        examples=["1 1", "2 4"],
        inline=True
    )
    await helpcmd.generate_aliases(["tambah", "plus"], False)
    await ctx.send(embed=helpcmd()) # or await ctx.send(embed=helpcmd.get())
    ```
    """

    def __init__(
        self, bot: commands.Bot, ctx: commands.Context, cmd_name: str = "", desc: str = "", color=None
    ):
        self.bot: commands.Bot = bot
        self.logger = logging.getLogger("naoTimes.HelpGen")

        self._ver = self.bot.semver
        commit = self.bot.commits
        if commit["hash"] is not None:
            self._ver += f" ({commit['hash']})"
        self._pre = self.bot.prefixes(ctx)
        self._no_pre = False

        if cmd_name.endswith("[*]"):
            cmd_name = cmd_name.replace("[*]", "").strip()
            self._no_pre = True
        self.cmd_name = cmd_name
        self.color = color
        if self.color is None:
            self.color = 0xCEBDBD  # rgb(206, 189, 189) / HEX #CEBDBD
        self.desc_cmd = desc

        self.embed: discord.Embed = None
        self._added_count = 0
        self._alias_gen = False
        self.__init_generate()

    def __call__(self) -> discord.Embed:
        return self.get()

    def get(self) -> discord.Embed:
        """Return the final embed.
        -----

        :raises ValueError: If the embed attrs is empty
        :return: Final embed
        :rtype: discord.Embed
        """
        if not isinstance(self.embed, discord.Embed):
            self.logger.warning("Embed are not generated yet.")
            raise ValueError("Embed are not generated yet.")
        if not self._alias_gen:
            self.generate_aliases()
        self.logger.info("sending embed results")
        return self.embed

    @staticmethod
    def __encapsulate(option: HelpOption) -> str:
        """Encapsulate the command name with <> or []
        -----

        Internal use only

        :param option: The option to be encapsulated
        :type option: HelpOption
        :return: Encapsulated command name
        :rtype: str
        """
        if option.required:
            return f"`[{option.name}]`"
        return f"`<{option.name}>`"

    @staticmethod
    def __encapsule(name: str, t: str) -> str:
        """Encapsulate the command name with <> or []
        -----

        This is for internal use only

        :param name: command name
        :type name: str
        :param t: command type (`r` or `o`, or `c`)
                  `r` for required command.
                  `o` for optional command.
        :type t: str
        :return: encapsuled command name
        :rtype: str
        """
        tt = {"r": ["`<", ">`"], "o": ["`[", "]`"], "c": ["`[", "]`"]}
        pre, end = tt.get(t, ["`", "`"])
        return pre + name + end

    def __init_generate(self):
        """Start generating embed"""
        self.logger.info(f"Start generating embed for: {self.cmd_name}")
        embed = discord.Embed(color=self.color)
        embed.set_author(name=self.bot.user.display_name, icon_url=self.bot.user.avatar)
        embed.set_footer(text=f"@author N4O#8868 | Versi {self._ver}")
        title = "Bantuan Perintah"
        if self.cmd_name != "":
            title += " ("
            if not self._no_pre:
                title += self._pre
            title += f"{self.cmd_name})"
        embed.title = title
        if self.desc_cmd != "":
            embed.description = self.desc_cmd
        self.embed = embed

    def __generate_example(self, cmd_name: str, examples: List[str]):
        """Start generating example"""
        generated_examples = []
        for example in examples:
            generated_examples.append(f"- {bold(self._pre + cmd_name)} {example}")
        return "\n".join(generated_examples)

    def add_field(self, field: HelpField):
        """Generate a help fields
        ---

        :param field: the field data
        :type field: HelpField
        """
        if self._added_count >= 21:
            raise ValueError("Unable to generate more field since it reach maximum field count!")
        self.logger.debug(f"Generating field: {field.name}")
        gen_name = self._pre + field.name
        final_desc = ""
        if field.description:
            final_desc += field.description
            final_desc += "\n"
        opts_list = []
        for opt in field.options:
            capsuled = self.__encapsulate(opt)
            opts_list.append(capsuled)
            if opt.description:
                if not opt.required:
                    if final_desc != "":
                        final_desc += "\n"
                    final_desc += " itu **`[OPSIONAL]`**"
                final_desc += f"\n{opt.description}"
        if final_desc == "":
            final_desc = "Cukup jalankan perintah ini tanpa opsi apapun"

        if len(opts_list) > 0:
            opts_final = " ".join(opts_list)
            gen_name += f" {opts_final}"
        if field.use_fullquote:
            final_desc = quote(final_desc)

        self.embed.add_field(name=gen_name, value=final_desc, inline=field.inline)
        if len(field.examples) > 0:
            self.embed.add_field(
                name="Contoh", value=self.__generate_example(field.name, field.examples), inline=False
            )
        self._added_count += 1

    def add_fields(self, fields: List[HelpField] = []):
        """Add multiple help field"""
        for field in fields:
            try:
                self.add_field(field)
            except ValueError:
                # Silence error
                pass

    async def generate_field(
        self,
        cmd_name: str,
        opts: List[Dict[str, str]] = [],
        desc: str = "",
        examples: List[str] = [],
        inline: bool = False,
        use_fullquote: bool = False,
    ):
        """Generate a help fields
        ---

        :param cmd_name: command name
        :type cmd_name: str
        :param opts: command options, defaults to []
        :type opts: List[Dict[str, str]], optional
        :param desc: command description, defaults to ""
        :type desc: str, optional
        :param examples: command example, defaults to []
        :type examples: List[str], optional
        :param inline: put field inline with previous field, defaults to False
        :type inline: bool, optional
        :param use_fullquote: Use block quote, defaults to False
        :type use_fullquote: bool, optional
        """
        self.logger.debug(f"generating field: {cmd_name}")
        gen_name = self._pre + cmd_name
        final_desc = ""
        if desc:
            final_desc += desc
            final_desc += "\n"
        opts_list = []
        if opts:
            for opt in opts:
                a_t = opt["type"]
                a_n = opt["name"]
                try:
                    a_d = opt["desc"]
                except KeyError:
                    a_d = ""
                capsuled = self.__encapsule(a_n, a_t)
                opts_list.append(capsuled)

                if a_d:
                    if a_t == "o":
                        if final_desc != "":
                            final_desc += "\n"
                        final_desc += capsuled
                        final_desc += " itu **`[OPSIONAL]`**"
                    final_desc += f"\n{a_d}"
        if final_desc == "":
            final_desc = cmd_name

        if opts_list:
            opts_final = " ".join(opts_list)
            gen_name += f" {opts_final}"

        if use_fullquote:
            final_desc = "```\n" + final_desc + "\n```"

        self.embed.add_field(
            name=gen_name,
            value=final_desc,
            inline=inline,
        )
        if examples:
            examples = [f"- **{self._pre}{cmd_name}** {ex}" for ex in examples]
            self.embed.add_field(
                name="Contoh",
                value="\n".join(examples),
                inline=False,
            )

    def add_aliases(self, aliases: List[str] = [], add_note: bool = True):
        """Generate the end part and aliases
        ---

        :param aliases: aliases to add, defaults to []
        :type aliases: List[str], optional
        :param add_note: add note to help, defaults to True
        :type add_note: bool, optional
        """
        if self._alias_gen:
            return
        self.logger.debug(f"Generating aliases for {self.cmd_name}")
        parsed_aliases = []
        for alias in aliases:
            if alias == self.cmd_name:
                continue
            parsed_aliases.append(self._pre + alias)
        if len(parsed_aliases) > 0:
            self.embed.add_field(name="Aliases", value=", ".join(parsed_aliases), inline=False)
        if add_note:
            NOTE_ADD = "Semua perintah memiliki bagian bantuannya sendiri!\n"
            NOTE_ADD += f"Gunakan `{self._pre}oldhelp [nama perintah]` untuk melihatnya!"
            self.embed.add_field(name="*Note*", value=NOTE_ADD, inline=False)
        self._alias_gen = True

    generate_aliases = add_aliases
