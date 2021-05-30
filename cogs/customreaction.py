import logging
from typing import Any, List, Mapping, NamedTuple, Union

import discord
from discord.ext import commands, tasks

from nthelper.bot import naoTimesBot


class Reactions(NamedTuple):
    id: str
    srv_id: str
    action: str
    response: str

    def __str__(self) -> str:
        return f"<Reactions id={self.id} guild={self.srv_id} aksi={self.action} />"

    def __repr__(self) -> str:
        return f"<Reactions id={self.id} guild={self.srv_id} aksi={self.action} />"

    def to_dict(self):
        return {"id": self.id, "srv_id": self.srv_id, "action": self.action, "response": self.response}

    def is_reaction(self, user_text: str):
        if user_text == self.action:
            return True
        return False


class CustomReaction(commands.Cog):
    def __init__(self, bot: naoTimesBot):
        self.bot = bot
        self.logger = logging.getLogger("cogs.CustomReaction")
        self._react_maps: Mapping[str, List[Reactions]] = {}
        self._precheck_existing_data.start()

    def cog_unload(self):
        self._precheck_existing_data.stop()

    @staticmethod
    def snowflake_to_timestamp(snowflakes: int) -> int:
        return int(round((snowflakes / 4194304 + 1420070400000) / 1000))

    def add_reaction(self, reaction: Reactions):
        if reaction.srv_id not in self._react_maps:
            self._react_maps[reaction.srv_id] = []
        self.logger.info(f"Adding reaction ID #{reaction.id} for guild {reaction.srv_id}")
        self._react_maps[reaction.srv_id].append(reaction)

    @tasks.loop(seconds=1, count=1)
    async def _precheck_existing_data(self):
        self.logger.info("checking preexisting custom reaction")

        reaction_datas = await self.bot.redisdb.getall("ntreact_*")
        srv_total = 0
        for reaction in reaction_datas:
            preact = Reactions(**reaction)
            if preact.srv_id not in self._react_maps:
                srv_total += 1
            self.add_reaction(preact)
        self.logger.info(f"Appended {len(reaction_datas)} on {srv_total} servers")

    @commands.Cog.listener("on_message")
    async def answer_custom_reactions(self, message: discord.Message):
        # Server only
        if not isinstance(message.guild, discord.Guild):
            return
        channel: Union[discord.TextChannel, Any] = message.channel
        # Check if text channel
        if not isinstance(channel, discord.TextChannel):
            return

        guild_id = str(message.guild.id)
        # Check the react maps
        if guild_id not in self._react_maps:
            return

        reactions_list = self._react_maps[guild_id]
        for reaction in reactions_list:
            if reaction.is_reaction(message.clean_content):
                self.logger.info(f"{guild_id}: sending reaction ID no {reaction.id}")
                return await channel.send(content=reaction.response)

    @commands.command(name="trk", aliases=["addcustomreaction", "acr", "tambahreaksikustom"])
    @commands.guild_only()
    async def _custom_reaction_cmd(self, ctx: commands.Context, aksi: str, *, reaksi: str):
        guild_id = str(ctx.guild.id)
        timestamp = self.snowflake_to_timestamp(ctx.message.id)

        preact = Reactions(str(timestamp), guild_id, aksi, reaksi)
        await self.bot.redisdb.set(f"ntreact_{guild_id}_{timestamp}", preact.to_dict())
        self.add_reaction(preact)

        embed = discord.Embed(title="Reaksi Kustom", color=discord.Colour.random())
        embed.description = f"#{preact.id}"
        embed.add_field(name="Aksi", value=preact.action, inline=False)
        embed.add_field(name="Reaksi", value=preact.response, inline=False)
        embed.add_field(
            name="*Info*", value=f"Untuk menghapus, gunakan `{self.bot.prefixes(ctx)}hrk #{preact.id}`"
        )
        return await ctx.send(embed=embed)

    @commands.command(name="hrk", aliases=["hapusreaksikustom", "dcr", "deletecustomreaction"])
    @commands.guild_only()
    async def _custom_reaction_delete(self, ctx: commands.Context, *, preact_id: str):
        guild_id = str(ctx.guild.id)
        if not preact_id.startswith("#"):
            return await ctx.send(
                "ID harus mulai dengan `#`, untuk memeriksa list reaksi "
                f"gunakan `{self.bot.prefixes(ctx)}lrk`"
            )
        preact_id = preact_id.strip("#")

        if guild_id not in self._react_maps:
            rdb_get = await self.bot.redisdb.get(f"ntreact_{guild_id}_{preact_id}")
            if rdb_get is None:
                return await ctx.send("Tidak dapat menemukan ID reaksi tersebut.")

        reactions_lists = self._react_maps[guild_id]
        found = False
        reaction_act = ""
        for idx, reaction in enumerate(reactions_lists[:]):
            if reaction.id == preact_id:
                reaction_act = reaction.action
                self.logger.info(f"Found on index {idx} ({str(reaction)})")
                reactions_lists.pop(idx)
                found = True
                break
        self._react_maps[guild_id] = reactions_lists
        if not found:
            rdb_get = await self.bot.redisdb.get(f"ntreact_{guild_id}_{preact_id}")
            if rdb_get is not None:
                found = True

        if not found:
            return await ctx.send("Tidak dapat menemukan ID reaksi tersebut.")
        await self.bot.redisdb.rm(f"ntreact_{guild_id}_{preact_id}")
        await ctx.send(f"Berhasil menghapus reaksi kustom #{preact_id} (Aksi: `{reaction_act}`)")

    @staticmethod
    def split_until_less_than(guild_name: str, dataset: list) -> List[List[str]]:
        """
        Split the !lcr shit into chunked text because discord
        max 2000 characters limit
        """

        text_format = f"**Reaksi Kustom Server __{guild_name}__**:\n"
        concat_set = []
        finalized_sets = []
        first_run = True
        for data in dataset:
            if first_run:
                concat_set.append(data)
                check = text_format + "\n".join(concat_set)
                if len(check) >= 1995:
                    last_occured = concat_set.pop()
                    finalized_sets.append(concat_set)
                    concat_set = [last_occured]
                    first_run = False
            else:
                concat_set.append(data)
                if len("\n".join(concat_set)) >= 1995:
                    last_occured = concat_set.pop()
                    finalized_sets.append(concat_set)
                    concat_set = [last_occured]

        new_sets = []
        while True:
            if len("\n".join(concat_set)) >= 1995:
                new_sets.append(concat_set.pop())
            else:
                break
        if concat_set:
            finalized_sets.append(concat_set)
        if new_sets:
            finalized_sets.append(new_sets)

        return finalized_sets

    @commands.command(
        name="lrk", aliases=["lihatreaksikustom", "liatreaksikustom", "lcr", "listcustomreaction"]
    )
    @commands.guild_only()
    async def _custom_reaction_list(self, ctx: commands.Context):
        guild_id = str(ctx.guild.id)
        if guild_id not in self._react_maps:
            rdb_get = await self.bot.redisdb.getall(f"ntreact_{guild_id}_*")
            if rdb_get is None:
                return await ctx.send("Tidak ada reaksi kustom yang terdaftar")

        guild_name = ctx.guild.name
        all_reactions = self._react_maps[guild_id]
        reaction_texts = []
        for n, react in enumerate(all_reactions, 1):
            reaction_texts.append(f"**{n}.** #{react.id} (`{react.action}`)")
        splitted_send = self.split_until_less_than(guild_name, reaction_texts)
        for n, split in enumerate(splitted_send):
            if n == 0:
                await ctx.send(f"**Reaksi Kustom Server __{guild_name}__**:\n" + "\n".join(split))
            else:
                await ctx.send("\n".join(split))


def setup(bot: naoTimesBot):
    bot.add_cog(CustomReaction(bot))
