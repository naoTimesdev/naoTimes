"""
MIT License

Copyright (c) 2019-2022 naoTimesdev

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

import asyncio
import logging
from enum import Enum
from typing import List, NamedTuple, Union

import arrow
import discord
from discord.ext import commands, tasks

from naotimes.bot import naoTimesBot
from naotimes.socket import ntevent

reactions_num = ["1⃣", "2⃣", "3⃣", "4⃣", "5⃣", "6⃣", "7⃣", "8⃣", "9⃣", "🔟"]
res2num = dict(zip(reactions_num, [0, 1, 2, 3, 4, 5, 6, 7, 8, 9]))
num2res = dict(zip([0, 1, 2, 3, 4, 5, 6, 7, 8, 9], reactions_num))


class UserVote(NamedTuple):
    id: int
    uuid: int
    choice: str
    removed: bool = False


class VoteType(Enum):
    # Multiple choice
    MULTIPLE = 0
    # Yes/no choice
    YESNO = 1
    # Kick/ban (use same format as Yes/no choice)
    USER = 2
    # Giveaway
    GIVEAWAY = 3


class VoteManager:
    def __init__(
        self, id: Union[str, int], name: Union[str, int], emote: str, limit: int = 0, voter: List[int] = []
    ):
        self.id = id
        self.name = name
        self.emote = emote
        self.limit = limit
        self._voter = voter

    def __eq__(self, other: Union[str, int, "VoteManager"]) -> bool:
        if isinstance(other, str) and isinstance(self.id, str):
            return self.id == other
        elif isinstance(other, int) and isinstance(self.id, int):
            return self.id == other
        elif isinstance(other, VoteManager):
            return self.id == other.id
        return False

    def __len__(self):
        return len(self._voter)

    def __repr__(self):
        __context = [
            f"id={self.id!r}",
            f"name={self.name!r}",
            f"emote={self.emote!r}",
            f"limit={self.limit!r}",
            f"voter={self._voter!r}",
        ]
        return f"<VoteManager {' '.join(__context)}>"

    @property
    def voter(self) -> List[int]:
        return self._voter

    @voter.setter
    def voter(self, new_voter: List[int]) -> List[int]:
        real_int_voter = []
        for voter in new_voter:
            if isinstance(voter, int):
                real_int_voter.append(voter)
        self._voter = real_int_voter

    @property
    def tally(self) -> int:
        return len(self._voter)

    def add_vote(self, user: int):
        if user not in self._voter:
            self._voter.append(user)

    def remove_vote(self, user: int):
        if user in self._voter:
            self._voter.remove(user)

    @classmethod
    def from_dict(cls, data: dict):
        return cls(data["id"], data["name"], data["emote"], data["limit"], data["voter"])

    def serialize(self):
        return {
            "id": self.id,
            "name": self.name,
            "emote": self.emote,
            "limit": self.limit,
            "voter": self._voter,
        }


class VoteResult(NamedTuple):
    data: VoteManager
    type: VoteType
    is_tied: bool = False
    is_timeout: bool = False


class VoteMetadata:
    def __init__(self, message_id: int, channel_id: int, author_id: int, title: str):
        self._mid = message_id
        self._cid = channel_id
        self._aid = author_id
        self.title = title

    def __eq__(self, other: Union[int, "VoteMetadata"]) -> bool:
        if isinstance(other, int):
            return self._mid == other
        elif isinstance(other, VoteMetadata):
            return self._mid == other.message
        return False

    def __repr__(self):
        __context = [
            f"id={self._mid!r}",
            f"channel={self._cid!r}",
            f"author={self._aid!r}",
            f"title={self.title!r}",
        ]
        return f"<VoteMetadata {' '.join(__context)}>"

    @property
    def message(self) -> int:
        return self._mid

    @property
    def channel(self) -> int:
        return self._cid

    @property
    def author(self) -> int:
        return self._aid

    def is_author(self, user: int) -> bool:
        return self._aid == user

    @classmethod
    def from_dict(cls, data: dict):
        return cls(data["message_id"], data["channel_id"], data["author_id"], data["title"])

    def serialize(self):
        return {"message_id": self._mid, "channel_id": self._cid, "author_id": self._aid, "title": self.title}


class VoteData:
    def __init__(
        self, metadata: VoteMetadata, choices: List[VoteManager], timeout: int, mode: VoteType = None
    ):
        self._meta = metadata
        self._choices = choices
        self._timeout = timeout

        if mode is None:
            self.__determine_mode()
        else:
            self._mode = mode

    def __determine_mode(self):
        first_choice = self._choices[0]
        if first_choice.id == "y":
            self._mode = VoteType.YESNO
        elif first_choice.id == "giveaway":
            self._mode = VoteType.GIVEAWAY
        elif first_choice.limit > 0:
            self._mode = VoteType.USER
        else:
            self._mode = VoteType.MULTIPLE

    @property
    def id(self):
        return self.metadata.message

    @property
    def metadata(self):
        return self._meta

    @property
    def choices(self):
        return self._choices

    @choices.setter
    def choices(self, new_choices: List[VoteManager]):
        self._choices = new_choices

    @property
    def timeout(self):
        return self._timeout

    @property
    def type(self):
        return self._mode

    def is_timeout(self):
        current_time = arrow.utcnow().int_timestamp
        return current_time > self._timeout

    def is_done(self):
        if self._mode == VoteType.USER:
            yes = self._choices[0].tally >= self._choices[0].limit
            no = self._choices[1].tally >= self._choices[1].limit
            if yes or no:
                return True
        return self.is_timeout()

    def get_vote(self, vote_id: Union[str, int]):
        for vote in self._choices:
            if vote == vote_id:
                return vote
        return None

    def update_vote(self, vote_choice: VoteManager):
        idx = -1
        for i, choice in enumerate(self._choices):
            if choice == vote_choice:
                idx = i
                break
        if idx >= 0:
            self._choices[idx] = vote_choice

    def has_voted(self, user: int) -> bool:
        for choice in self._choices:
            if user in choice.voter:
                return True
        return False

    def add_vote(self, vote_info: UserVote):
        if self._meta.is_author(vote_info.uuid):
            return
        if self.has_voted(vote_info.uuid):
            return
        if self.type == VoteType.YESNO or self.type == VoteType.USER:
            if vote_info.choice == "y":
                self._choices[0].add_vote(vote_info.uuid)
            elif vote_info.choice == "n":
                self._choices[1].add_vote(vote_info.uuid)
        else:
            exist_choice = self.get_vote(vote_info.choice)
            if exist_choice is not None:
                exist_choice.add_vote(vote_info.uuid)
                self.update_vote(exist_choice)

    def remove_vote(self, vote_info: UserVote):
        if self._meta.is_author(vote_info.uuid):
            return
        if self.type == VoteType.YESNO or self.type == VoteType.USER:
            if vote_info.choice == "y":
                self._choices[0].remove_vote(vote_info.uuid)
            elif vote_info.choice == "n":
                self._choices[1].remove_vote(vote_info.uuid)
        else:
            exist_choice = self.get_vote(vote_info.choice)
            if exist_choice is not None:
                exist_choice.remove_vote(vote_info.uuid)
                self.update_vote(exist_choice)

    def get_winner(self):
        if self._mode == VoteType.GIVEAWAY:
            return VoteResult(self._choices[0], VoteType.GIVEAWAY)
        elif self._mode == VoteType.YESNO:
            yes = self._choices[0]
            no = self._choices[1]
            is_tied = yes.tally == no.tally
            if is_tied:
                return VoteResult(yes, self._mode, True)
            elif yes.tally > no.tally:
                return VoteResult(yes, self._mode)
            else:
                return VoteResult(no, self._mode)
        elif self._mode == VoteType.USER:
            yes = self._choices[0]
            no = self._choices[1]
            if yes.tally >= yes.limit:
                return VoteResult(yes, self._mode)
            elif no.tally >= no.limit:
                return VoteResult(no, self._mode)
            else:
                return VoteResult(no, self._mode, is_timeout=True)
        winner = max(self._choices, key=lambda x: x.tally)
        if winner.tally == 0:
            return VoteResult(winner, VoteType.MULTIPLE, is_tied=True)
        return VoteResult(winner, VoteType.MULTIPLE)

    @classmethod
    def from_dict(cls, data: dict):
        metadata = VoteMetadata.from_dict(data["metadata"])
        choices = [VoteManager.from_dict(choice) for choice in data["choices"]]
        mode_meta = VoteType(data["type"])
        return cls(metadata, choices, data["timeout"], mode_meta)

    def serialize(self):
        metadata = self._meta.serialize()
        all_choices = []
        for choice in self._choices:
            all_choices.append(choice.serialize())
        return {
            "metadata": metadata,
            "choices": all_choices,
            "timeout": self._timeout,
            "type": self._mode.value,
        }


class VoteListener(commands.Cog):
    """The main loop for listening to vote data!"""

    PRE_KEY = "ntvotev2_"

    def __init__(self, bot: naoTimesBot):
        self.bot = bot
        self.logger = logging.getLogger("VoteSystem.ListenerV2")
        self._client = bot.redisdb
        self._is_ready = False

        self._is_unloding = False

        self._lock = asyncio.Lock()
        self._vote_queue = asyncio.Queue[UserVote](loop=self.bot.loop)
        self._vote_task = asyncio.Task(self._handle_new_vote())
        self._cached_vote_message: List[int] = []
        self._handle_existing_vote.start()
        self._temp_task = self.bot.loop.create_task(
            self._on_cog_loaded(), name="preload-vote-data-on-cog-load"
        )

    def cog_unload(self):
        self._is_unloding = True
        self._vote_task.cancel()
        self._handle_existing_vote.cancel()
        self._temp_task.cancel()

    async def _get_vote_data(self, message: int):
        """Get the vote information from redis"""
        vote_data = await self._client.get(f"{self.PRE_KEY}{message}")
        if vote_data is None:
            return None
        return VoteData.from_dict(vote_data)

    async def _get_all_votes(self):
        vote_data = await self._client.getall(f"{self.PRE_KEY}*")
        real_vote: List[VoteData] = []
        for vote in vote_data:
            real_vote.append(VoteData.from_dict(vote))
        return real_vote

    @ntevent()
    async def on_vote_creation(self, vote: VoteData):
        self._cached_vote_message.append(vote.id)

    async def _save_vote_data(self, vote_data: VoteData):
        """Save the vote data to redis"""
        mid = vote_data.metadata.message
        await self._client.set(f"{self.PRE_KEY}{mid}", vote_data.serialize())

    async def _delete_vote_data(self, vote_data: VoteData):
        """Delete the vote data from redis"""
        mid = vote_data.metadata.message
        await self._client.rm(f"{self.PRE_KEY}{mid}")
        try:
            self._cached_vote_message.remove(vote_data.id)
        except (ValueError, KeyError, AttributeError, IndexError):
            pass

    async def _tally_up_missing(self, vote_meta: VoteData):
        """Tally up the votes that are missing"""
        metadata = vote_meta.metadata
        message_id = metadata.message
        channel_id = metadata.channel
        channel_data: discord.TextChannel = self.bot.get_channel(channel_id)
        if channel_data is None:
            return None
        self.logger.info(f"Fetching message: {message_id} at #{channel_data}")
        try:
            message = await channel_data.fetch_message(message_id)
        except discord.NotFound:
            return None

        the_reactions = message.reactions

        IGNORED_AUTHOR = [
            metadata.author,
            self.bot.user.id,
        ]

        new_votes = []
        self.logger.info("Trying to accumulate reaction while bot is gone!")
        if vote_meta.type == VoteType.YESNO or vote_meta.type == VoteType.USER:
            self.logger.info("Detected y/n type or user type")
            choice_yes = vote_meta.choices[0]
            choice_no = vote_meta.choices[1]
            yes_emote = choice_yes.emote
            no_emote = choice_no.emote

            yes_react = None
            no_react = None
            for react in the_reactions:
                if react.emoji == yes_emote:
                    yes_react = react
                elif react.emoji == no_emote:
                    no_react = react

            if yes_react is not None:
                voter_yes = await yes_react.users().flatten()
                complete_voter = []
                for voter in voter_yes:
                    if voter.id not in IGNORED_AUTHOR and not voter.bot:
                        complete_voter.append(voter.id)
                choice_yes.voter = complete_voter
            if no_react is not None:
                voter_no = await no_react.users().flatten()
                complete_voter = []
                for voter in voter_no:
                    if voter.id not in IGNORED_AUTHOR and not voter.bot:
                        complete_voter.append(voter.id)
                choice_no.voter = complete_voter
            new_votes.append(choice_yes)
            new_votes.append(choice_no)
        elif vote_meta.type == VoteType.GIVEAWAY:
            choice_popper = vote_meta.choices[0]
            popper_emote = choice_popper.emote
            self.logger.info("Detected giveaway type, collecting popper 🎉 emote!")
            popper_react = None
            for react in the_reactions:
                if react.emoji == popper_emote:
                    popper_react = react

            if popper_react is not None:
                voter_give = await popper_react.users().flatten()
                complete_voter = []
                for voter in voter_give:
                    if voter.id not in IGNORED_AUTHOR and not voter.bot:
                        complete_voter.append(voter.id)
                choice_popper.voter = complete_voter
            new_votes.append(choice_popper)
        else:
            self.logger.info("Detected multi type, ignoring")
            reparsed_reaction: List[discord.Reaction] = []
            ALL_VALID_REACTION = [vote.emote for vote in vote_meta.choices]
            for react in the_reactions:
                if react.emoji in ALL_VALID_REACTION:
                    reparsed_reaction.append(react)
            all_reaction = [react.emoji for react in reparsed_reaction]
            concat_this_data = []
            for choice in vote_meta.choices:
                if choice.emote not in all_reaction:
                    concat_this_data.append(VoteManager(choice.id, choice.name, choice.emote, voter=[]))

            reparsed_count = vote_meta.choices[:]
            for react in reparsed_reaction:
                voter_user = await react.users().flatten()
                complete_voter = []
                for voter in voter_user:
                    if voter.id not in IGNORED_AUTHOR and not voter.bot:
                        complete_voter.append(voter.id)
                react_pos = res2num[str(react.emoji)]
                react_data = reparsed_count[react_pos]
                reparsed_count[react_pos] = VoteManager(
                    react_data.id, react_data.name, react_data.emote, voter=complete_voter
                )
            reparsed_count.extend(concat_this_data)
            reparsed_count.sort(key=lambda x: x.id)
            new_votes.extend(reparsed_count)

        vote_meta.choices = new_votes
        return vote_meta

    async def _on_cog_loaded(self):
        await self.bot.wait_until_ready()
        self.logger.info("Prechecking existing vote...")
        currently_running_votes = await self._get_all_votes()
        for vote in currently_running_votes:
            try:
                new_vote = await self._tally_up_missing(vote)
            except Exception:
                self.logger.exception("Failed to tally up vote, ignoring...")
                continue
            if new_vote is None:
                self.logger.warning(f"Vote {vote.id} message went missing!? ignoring...")
                continue
            if new_vote.is_done():
                self.logger.info(
                    f"Vote {vote.id} is done, collecting missing reaction and dispatching event..."
                )
                await self._delete_vote_data(new_vote)
                self.bot.ntevent.dispatch("vote finished", new_vote)
            else:
                await self._save_vote_data(new_vote)
                self._cached_vote_message.append(new_vote.id)
        self.logger.info("Precheck done, listener is now ready!")
        self._is_ready = True

    async def _handle_new_vote(self):
        while True:
            try:
                new_vote = await self._vote_queue.get()
                self.logger.debug(f"Got new vote: {new_vote}")
                vote_data = await self._get_vote_data(new_vote.id)
                if vote_data is not None:
                    self.logger.debug(f"Found vote data, updating with {new_vote.uuid}...")
                    if new_vote.removed:
                        vote_data.remove_vote(new_vote)
                    else:
                        vote_data.add_vote(new_vote)
                    if vote_data.is_done():
                        self.logger.debug(f"Vote {new_vote.id} is done, dispatching event...")
                        await self._delete_vote_data(vote_data)
                        self.bot.ntevent.dispatch("vote finished", vote_data)
                    else:
                        self.logger.debug(f"Vote {new_vote.id} is not done, saving...")
                        await self._save_vote_data(vote_data)
                        # Dispatch event to update embed :peepoSmile:
                        self.bot.ntevent.dispatch("vote updated", vote_data)
                self._vote_queue.task_done()
            except asyncio.CancelledError:
                break

    @tasks.loop(seconds=5)
    async def _handle_existing_vote(self):
        if not self._is_ready:
            self.logger.warning("Sleeping for another 5 seconds because it's not ready yet...")
            return
        if self._is_unloding:
            return
        try:
            async with self._lock:
                all_votes = await self._get_all_votes()
                for vote in all_votes:
                    if vote.is_done():
                        self.logger.warning(f"Vote {vote.metadata.message} is over!")
                        await self._delete_vote_data(vote)
                        self.bot.ntevent.dispatch("vote finished", vote)
        except asyncio.CancelledError:
            self.logger.warning("Got cancel signal, stopping process...")

    @_handle_existing_vote.before_loop
    async def _before_every_task(self):
        await self.bot.wait_until_ready()

    @commands.Cog.listener("on_reaction_add")
    async def _listen_new_vote(self, reaction: discord.Reaction, member: discord.Member):
        if member.bot:
            return
        if reaction.message.id not in self._cached_vote_message:
            return
        if reaction.is_custom_emoji():
            return
        emostr = str(reaction.emoji)
        if emostr in reactions_num:
            npos = res2num[emostr]
            user_vote = UserVote(reaction.message.id, member.id, f"mul_{npos}")
            await self._vote_queue.put(user_vote)
        elif emostr == "✅":
            user_vote = UserVote(reaction.message.id, member.id, "y")
            await self._vote_queue.put(user_vote)
        elif emostr == "❌":
            user_vote = UserVote(reaction.message.id, member.id, "n")
            await self._vote_queue.put(user_vote)
        elif emostr == "🎉":
            user_vote = UserVote(reaction.message.id, member.id, "giveaway")
            await self._vote_queue.put(user_vote)

    @commands.Cog.listener("on_reaction_remove")
    async def _listen_remove_vote(self, reaction: discord.Reaction, member: discord.Member):
        if member.bot:
            return
        if reaction.message.id not in self._cached_vote_message:
            return
        if reaction.is_custom_emoji():
            return
        emostr = str(reaction.emoji)
        if emostr in reactions_num:
            npos = res2num[emostr]
            user_vote = UserVote(reaction.message.id, member.id, f"mul_{npos}", True)
            await self._vote_queue.put(user_vote)
        elif emostr == "✅":
            user_vote = UserVote(reaction.message.id, member.id, "y", True)
            await self._vote_queue.put(user_vote)
        elif emostr == "❌":
            user_vote = UserVote(reaction.message.id, member.id, "n", True)
            await self._vote_queue.put(user_vote)
        elif emostr == "🎉":
            user_vote = UserVote(reaction.message.id, member.id, "giveaway", True)
            await self._vote_queue.put(user_vote)


async def setup(bot: naoTimesBot):
    await bot.add_cog(VoteListener(bot))
