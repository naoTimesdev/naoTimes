import logging
from typing import Any, List, Mapping, NamedTuple, Union

import discord
from discord.ext import commands, tasks

from naotimes.bot import naoTimesBot
from naotimes.context import naoTimesContext


class Reaction(NamedTuple):
    id: str
    srv_id: int
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


class ReactionServer:
    def __init__(self, server: int) -> None:
        self._guild = server
        self._reactions: List[Reaction] = []

    def __eq__(self, other: Union[int, "ReactionServer"]):
        if isinstance(other, ReactionServer):
            if other.id == self._guild:
                return True
        elif isinstance(other, int):
            if other == self._guild:
                return True
        return False

    def __iter__(self):
        for reaction in self._reactions:
            yield reaction

    @property
    def id(self):
        return self._guild

    def has_reaction(self, action: str):
        for reaction in self._reactions:
            if reaction.is_reaction(action):
                return reaction
        return None

    def add_reaction(self, reaction: Reaction):
        self._reactions.append(reaction)

    def remove_reaction(self, reaction: Reaction):
        try:
            self._reactions.remove(reaction)
        except ValueError:
            pass

    def bulk_add_reaction(self, reactions: Reaction):
        self._reactions.extend(reactions)


class ReactionManager:
    def __init__(self):
        self._manager: List[ReactionServer] = []

    def __len__(self):
        return len(self._manager)

    def __iter__(self):
        for manager in self._manager:
            yield manager

    def add_child(self, child: Union[int, ReactionServer]):
        if isinstance(child, int):
            react_srv = ReactionServer(child)
            self._manager.append(react_srv)
            return react_srv
        elif isinstance(child, ReactionServer):
            self._manager.append(child)
            return child

    def get_child(self, server: int) -> ReactionServer:
        for child in self._manager:
            if child == server:
                return child
        return self.add_child(server)

    def has_child(self, server: int):
        for child in self._manager:
            if child == server:
                return True
        return False

    def remove_child(self, server: int):
        idx = -1
        for i, child in enumerate(self._manager):
            if child == server:
                idx = i
                break
        if idx >= 0:
            self._manager.pop(idx)

    def add_to_child(self, server: int, reaction: Reaction):
        react_srv = self.get_child(server)
        react_srv.add_reaction(reaction)

    def remove_from_child(self, server: int, reaction: Reaction):
        react_srv = self.get_child(server)
        react_srv.remove_reaction(reaction)

    def bulk_add_to_child(self, server: int, reactions: Reaction):
        react_srv = self.get_child(server)
        react_srv.bulk_add_reaction(reactions)

    def child_has_reaction(self, guild: int, action: str):
        react_srv = self.get_child(guild)
        return react_srv.has_reaction(action)


class FunCustomReactions(commands.Cog):
    def __init__(self, bot: naoTimesBot):
        self.bot = bot
        self.logger = logging.getLogger("Fun.CustomReaction")
        self._MANAGER = ReactionManager()

        self._precheck_reactions.start()

    def cog_unload(self):
        self._precheck_reactions.stop()

    @staticmethod
    def snowflake_to_timestamp(snowflakes: int) -> int:
        return int(round((snowflakes / 4194304 + 1420070400000) / 1000))

    @staticmethod
    def _parse_react_json(data: Mapping[str, Any]) -> Reaction:
        react_id = data["id"]
        server_id = int(data["srv_id"])
        action = data["action"]
        response = data["response"]
        react_andy = Reaction(react_id, server_id, action, response)
        return react_andy

    @tasks.loop(seconds=1.0, count=1)
    async def _precheck_reactions(self):
        self.logger.info("Checking Preexisting custom reaction...")

        reaction_datas = await self.bot.redisdb.getall("ntreact_*")
        for reaction in reaction_datas:
            server_id = int(reaction["srv_id"])
            react_andy = self._parse_react_json(reaction)
            self._MANAGER.add_to_child(server_id, react_andy)
        self.logger.info(f"Appended {len(self._MANAGER)} manager!")

    @commands.Cog.listener("on_message")
    async def _answer_custom_reaction(self, message: discord.Message):
        # Check if the message from a bot
        if message.author.bot:
            return
        # Guild only
        if message.guild is None:
            return
        channel = message.channel
        if not isinstance(channel, discord.abc.Messageable):
            return

        # Check if we have the reaction
        reaction = self._MANAGER.child_has_reaction(message.guild.id, message.clean_content)
        if reaction is not None:
            self.logger.info(f"{message.guild.id}: sending reaction ID no {reaction.id}")
            await channel.send(content=reaction.response)

    @commands.command(name="trk", aliases=["addcustomreaction", "acr", "tambahreaksikustom"])
    @commands.guild_only()
    async def _fun_reaction_add(self, ctx: naoTimesContext, aksi: str, *, reaksi: str):
        guild_id = ctx.guild.id
        timestamp = int(self.snowflake_to_timestamp(ctx.message.id))

        preact = Reaction(str(timestamp), guild_id, aksi, reaksi)
        await self.bot.redisdb.set(f"ntreact_{guild_id}_{timestamp}", preact.to_dict())
        self._MANAGER.add_to_child(guild_id, preact)

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
    async def _fun_reaction_delete(self, ctx: naoTimesContext, *, preact_id: str):
        guild_id = ctx.guild.id
        if not preact_id.startswith("#"):
            return await ctx.send(
                "ID harus mulai dengan `#`, untuk memeriksa list reaksi "
                f"gunakan `{self.bot.prefixes(ctx)}lrk`"
            )

        preact_id = preact_id.strip("#")
        from_rdb = await self.bot.redisdb.get(f"ntreact_{guild_id}_{preact_id}")
        if from_rdb is None:
            return await ctx.send("Tidak dapat menemukan ID reaksi tersebut.")

        parsed_react = self._parse_react_json(from_rdb)
        await self.bot.redisdb.rm(f"ntreact_{guild_id}_{preact_id}")
        self._MANAGER.remove_from_child(guild_id, parsed_react)

        await ctx.send(f"Berhasil menghapus reaksi kustom #{preact_id} (Aksi: `{parsed_react.action}`)")

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
        first_data = f"**Reaksi Kustom Server __{guild_name}__**:\n" + "\n".join(finalized_sets[0])
        other_data = list(map(lambda x: "\n".join(x), finalized_sets[1:]))
        return [first_data] + other_data

    @commands.command(
        name="lrk", aliases=["lihatreaksikustom", "liatreaksikustom", "lcr", "listcustomreaction"]
    )
    @commands.guild_only()
    async def _fun_reaction_listall(self, ctx: naoTimesContext):
        guild_id = ctx.guild.id
        if not self._MANAGER.has_child(guild_id):
            rdb_get = await self.bot.redisdb.getall(f"ntreact_{guild_id}_*")
            if not rdb_get:
                return await ctx.send("Tidak ada reaksi kustom yang terdaftar")
            for gg in rdb_get:
                server_id = int(gg["srv_id"])
                react_andy = self._parse_react_json(gg)
                self._MANAGER.add_to_child(server_id, react_andy)

        guild_name = ctx.guild.name
        all_reactions = self._MANAGER.get_child(guild_id)
        reactions_text = []
        for n, react in enumerate(all_reactions, 1):
            reactions_text.append(f"**{n}.** #{react.id} (`{react.action}`)")
        if len(reactions_text) < 1:
            return await ctx.send("Tidak ada reaksi kustom yang terdaftar")
        splitted_send = self.split_until_less_than(guild_name, reactions_text)
        for chunk in splitted_send:
            await ctx.send(chunk)


def setup(bot: naoTimesBot):
    bot.add_cog(FunCustomReactions(bot))
