import asyncio
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Union

from nthelper.redis import RedisBridge


def utc_time() -> int:
    t = datetime.now(tz=timezone.utc).timestamp()
    return int(round(t))


class VotingBase:
    def __init__(
        self,
        requester_id: int,
        message_data: Dict[str, int],
        vote_question: Union[str, int],
        vote_answers: List[dict],
        timeout: Union[int, float],
        limit: int = 0,
        vote_type: str = "mul",
    ):
        self._requester = requester_id
        self._mid = message_data["id"]
        self._cid = message_data["channel"]
        self._question = vote_question
        self._answers = vote_answers
        self._timeout = timeout
        self._type = vote_type
        self._vote_limit = limit
        self._voter: List[int] = []

        for ans in self._answers:
            self._voter.extend(ans["voter"])

        self.logger = logging.getLogger("nthelper.votebackend.VotingBase")

        self._is_done = False

        if self._type not in ("yn", "mul", "kickban", "giveaway"):
            raise ValueError(f"Unknown '{self._type}' value in vote_type.")

    def export_data(self):
        raise NotImplementedError()

    def get_id(self) -> int:
        """Get message ID

        :return: Message ID
        :rtype: int
        """
        return self._mid

    def get_timeout(self) -> Union[int, float]:
        """Get max wait time or timeout

        :return: Timeout
        :rtype: int
        """
        return self._timeout

    def is_timeout(self) -> bool:
        """Has the timeout limit reached or the vote limit reached

        :return: is it done
        :rtype: bool
        """
        return self._is_done

    def refresh(self):
        raise NotImplementedError()

    def add_vote(self, user_id: int, choice_index: int):
        """Add user vote to the voting data

        :param user_id: User ID that voted
        :type user_id: int
        :param choice_index: Choice that picked (Index from zero/0)
        :type choice_index: int
        :raises IndexError: If choice_index is out of range.
        :raises ValueError: If user already voted.
        """
        self.logger.info(f"{self._mid}: tallying to index {choice_index}")
        if choice_index > len(self._answers):
            self.logger.error(f"{self._mid}: failed to tally index {choice_index}")
            raise IndexError("choice_index are way out of range of answer.")
        if user_id in self._voter:
            raise ValueError("Cannot vote twice.")
        if user_id == self._requester:
            raise KeyError("Requester cannot add vote.")
        self._answers[choice_index]["voter"].append(user_id)
        self._answers[choice_index]["tally"] = len(self._answers[choice_index]["voter"])
        self._voter.append(user_id)

    def remove_vote(self, user_id: int, choice_index: int):
        """Remove user vote from the voting data

        :param user_id: User ID that want their vote to be removed.
        :type user_id: int
        :param choice_index: Choice that picked (Index from zero/0)
        :type choice_index: int
        :raises IndexError: If choice_index is out of range.
        :raises ValueError: If user haven't voted this for some unknown reason.
        """
        self.logger.info(f"{self._mid}: remove tally from index {choice_index}")
        if choice_index > len(self._answers):
            self.logger.error(f"{self._mid}: failed to tally index {choice_index}")
            raise IndexError("choice_index are way out of range of answer.")
        if user_id not in self._voter:
            raise ValueError("Cannot remove vote.")
        if user_id not in self._answers[choice_index]["voter"]:
            raise ValueError("Cannot remove vote.")
        if user_id == self._requester:
            raise KeyError("Requester cannot remove vote.")
        self._answers[choice_index]["voter"].remove(user_id)
        self._answers[choice_index]["tally"] = len(self._answers[choice_index]["voter"])
        self._voter.remove(user_id)

    def tally_all(self):
        raise NotImplementedError()


class VotingData(VotingBase):
    def __init__(
        self,
        requester_id: int,
        message_data: Dict[str, int],
        vote_question: str,
        vote_answers: List[dict],
        timeout: Union[int, float],
    ):
        vtype = "mul"
        if str(vote_answers[0]["id"]) == "y":
            vtype = "yn"
        super().__init__(requester_id, message_data, vote_question, vote_answers, timeout, vote_type=vtype)

    def export_data(self) -> dict:
        """Get Voting Data as dict

        :return: Vote data
        :rtype: dict
        """
        return {
            "id": self._mid,
            "channel_id": self._cid,
            "requester": self._requester,
            "question": self._question,
            "answers": self._answers,
            "timeout": self._timeout,
            "type": self._type,
        }

    def refresh(self):
        """Refresh voting data, check with the timeout limit.
        """
        current = utc_time()
        if current >= self._timeout:
            self._is_done = True

    def tally_all(self) -> Dict[str, int]:
        """Tally all answers

        :return: tallied answers
        :rtype: Dict[str, int]
        """
        if self._type == "yn":
            vote_results = {"y": 0, "n": 0}
            vote_results["y"] = self._answers[0]["tally"]
            vote_results["n"] = self._answers[1]["tally"]
        else:
            vote_results = {}
            for vote in self._answers:
                vote_results[str(vote["id"])] = vote["tally"]
        return vote_results


class VotingKickBan(VotingBase):
    def __init__(
        self,
        requester_id: int,
        message_data: Dict[str, int],
        user_target: int,
        vote_answers: List[dict],
        timeout: Union[int, float],
        limit: int,
        type_vote: str,
    ):
        super().__init__(
            requester_id, message_data, user_target, vote_answers, timeout, limit, vote_type="kickban"
        )
        self._kickban_type = type_vote

    def export_data(self) -> dict:
        """Get Voting Data as dict

        :return: Vote data
        :rtype: dict
        """
        return {
            "id": self._mid,
            "channel_id": self._cid,
            "requester": self._requester,
            "user_target": self._question,
            "vote_data": self._answers,
            "timeout": self._timeout,
            "limit": self._vote_limit,
            "type": "kickban",
            "kickban_type": self._kickban_type,
        }

    def refresh(self):
        """Refresh voting data, check with the timeout limit.
        and also check the tally limit.
        """
        current = utc_time()
        final_tally = self.tally_all()
        if (
            current >= self._timeout
            or final_tally["y"] >= self._vote_limit
            or final_tally["n"] >= self._vote_limit
        ):
            self._is_done = True

    def tally_all(self) -> Dict[str, int]:
        """Tally all answers

        :return: tallied answers
        :rtype: Dict[str, int]
        """
        vote_results = {"y": 0, "n": 0}
        for vote in self._answers:
            vote_results[vote["id"]] = vote["tally"]
        return vote_results


class VotingGiveaway(VotingBase):
    def __init__(
        self,
        requester_id: int,
        message_data: Dict[str, int],
        vote_question: Union[str, int],
        vote_answers: List[dict],
        timeout: Union[int, float],
    ):
        super().__init__(
            requester_id, message_data, vote_question, vote_answers, timeout, vote_type="giveaway"
        )

    def refresh(self):
        """Refresh voting data, check with the timeout limit."""
        current = utc_time()
        if current >= self._timeout:
            self._is_done = True

    def export_data(self) -> Dict[str, Any]:
        """Get the giveaway information

        :return: Giveaway information
        :rtype: dict
        """
        return {
            "id": self._mid,
            "channel_id": self._cid,
            "initiator": self._requester,
            "item": self._question,
            "participants": self._answers,
            "timeout": self._timeout,
            "type": self._type,
        }

    def tally_all(self) -> List[int]:
        """Tally or get the list of participants of the giveaway.

        :return: the participants
        :rtype: List[int]
        """
        return self._answers[0]["voter"]


class UserVote:
    """
    UserVote holding data.
    """

    def __init__(self, message_id: int, user_id: int, choice: int, is_remove: bool = False):
        self.msg_id = message_id
        self.user_id = user_id
        self.choice = choice
        self.is_remove = is_remove


class VoteWatcher:
    """
    Main Vote Watcher process.
    this is poggers bois.
    """

    def __init__(self, fcwd: str, redis_client: RedisBridge, loop=None):
        self.logger = logging.getLogger("nthelper.votebackend.VoteWatcher")
        if loop is None:
            self._loop = asyncio.get_event_loop()
        else:
            self._loop = loop
        self._fcwd = fcwd

        self.vote_holding: Dict[str, Union[VotingData, VotingKickBan]] = {}
        self._vote_lock: List[int] = []
        self._db = redis_client

        self.done_queue: asyncio.Queue = asyncio.Queue()
        self._voter_queue: asyncio.Queue = asyncio.Queue()

        self._clock_task: asyncio.Task = asyncio.Task(self._clock_tick())
        self._voter_task: asyncio.Task = asyncio.Task(self._handle_voter())

    def exist(self, message_id: Union[str, int]):
        msg_id = str(message_id)
        if msg_id in list(self.vote_holding.keys()):
            return True
        return False

    async def stop_and_flush(self):
        """
        This will halt every process and wait for everything to finish tallying,
        then stop it, and then clean everything.
        """
        self.logger.info("stopping all tasks...")
        self._clock_task.cancel()
        self._voter_task.cancel()
        self.logger.info("saving all vote data to file...")
        all_vote_data = [int(msg_id) for msg_id in self.vote_holding]
        self._vote_lock.extend(all_vote_data)

        for msg_id, vote_handler in self.vote_holding.items():
            await self._db.set("ntvote_" + str(msg_id), vote_handler.export_data())

    @staticmethod
    def generate_answers(answers_options: list, two_choice_type=False):
        final_data = []
        if not two_choice_type:
            for n, opts in enumerate(answers_options):
                data_internal = {
                    "id": n,
                    "tally": 0,
                    "voter": [],
                    "name": opts,
                }
                final_data.append(data_internal)
        else:
            final_data.append({"id": "y", "tally": 0, "voter": [], "name": "Ya"})
            final_data.append({"id": "n", "tally": 0, "voter": [], "name": "Tidak"})
        return final_data

    async def stop_watching_vote(self, message_id: int):
        if str(message_id) not in self.vote_holding:
            raise KeyError("Message doesn't exists")
        self._vote_lock.append(message_id)

        self.logger.info(f"removing {message_id} from voting data...")
        vote_handler = self.vote_holding[str(message_id)]
        await self.done_queue.put(vote_handler)
        del self.vote_holding[str(message_id)]
        await self._db.rm("ntvote_" + str(message_id))
        self._vote_lock.remove(message_id)

    async def start_watching_vote(
        self,
        requester_id: int,
        message_data: Dict[str, int],
        question: str,
        answers: List[dict],
        timeout: Union[int, float],
    ):
        vote_handler = VotingData(requester_id, message_data, question, answers, timeout)
        self.vote_holding[str(message_data["id"])] = vote_handler

        await self._db.set("ntvote_" + str(message_data["id"]), vote_handler.export_data())

    async def start_watching_vote_kickban(
        self,
        hammer_type: str,
        requester_id: int,
        message_data: Dict[str, int],
        user_target: int,
        timeout: Union[int, float],
        limit: int,
        override_answers=None,
    ):
        yn_watcher = [
            {"id": "y", "tally": 0, "voter": [], "name": "Ya"},
            {"id": "n", "tally": 0, "voter": [], "name": "Tidak"},
        ]
        if override_answers is not None:
            yn_watcher = override_answers
        vote_handler = VotingKickBan(
            requester_id, message_data, user_target, yn_watcher, timeout, limit, hammer_type
        )
        self.vote_holding[str(message_data["id"])] = vote_handler

        await self._db.set("ntvote_" + str(message_data["id"]), vote_handler.export_data())

    async def start_watching_giveaway(
        self,
        initiator_id: int,
        message_data: Dict[str, int],
        item: str,
        timeout: Union[int, float],
        override_result=None,
    ):
        giveaway_vote = [{"id": "join", "tally": 0, "voter": [], "name": "Join"}]
        if override_result is not None:
            giveaway_vote = override_result
        vote_handler = VotingGiveaway(initiator_id, message_data, item, giveaway_vote, timeout)
        self.vote_holding[str(message_data["id"])] = vote_handler

        await self._db.set("ntvote_" + str(message_data["id"]), vote_handler.export_data())

    async def add_vote(self, message_id: int, user_id: int, choice_index: int):
        msg_str_id = str(message_id)
        if msg_str_id not in self.vote_holding:
            raise KeyError("Unknown message_id")
        await self._voter_queue.put(UserVote(message_id, user_id, choice_index))

    async def remove_vote(self, message_id: int, user_id: int, choice_index: int):
        msg_str_id = str(message_id)
        if msg_str_id not in self.vote_holding:
            raise KeyError("Unknown message_id")
        await self._voter_queue.put(UserVote(message_id, user_id, choice_index, True))

    async def _clock_tick(self):
        while True:
            try:
                to_remove = []
                current_time = utc_time()
                for n, vote_handler in enumerate(self.vote_holding.values()):
                    if vote_handler.get_id() in self._vote_lock:
                        continue
                    vote_handler.refresh()
                    if vote_handler.is_timeout():
                        await self.stop_watching_vote(str(vote_handler.get_id()))
                    if current_time > vote_handler.get_timeout():
                        await self.stop_watching_vote(str(vote_handler.get_id()))

                for rem in to_remove:
                    del self.vote_holding[rem]

                await asyncio.sleep(1.0)
            except asyncio.CancelledError:
                return

    async def _handle_voter(self):
        while True:
            try:
                handle_vote: UserVote = await self._voter_queue.get()
                self.logger.info(f"Handling incoming vote data for {handle_vote.msg_id}")
                if str(handle_vote.msg_id) in self.vote_holding:
                    try:
                        if handle_vote.is_remove:
                            self.logger.info(f"{handle_vote.msg_id}: handling vote removal...")
                            self.vote_holding[str(handle_vote.msg_id)].remove_vote(
                                handle_vote.user_id, handle_vote.choice
                            )
                        else:
                            self.logger.info(f"{handle_vote.msg_id}: handling vote addition...")
                            self.vote_holding[str(handle_vote.msg_id)].add_vote(
                                handle_vote.user_id, handle_vote.choice
                            )
                        self.logger.info(f"{handle_vote.msg_id}: saving vote...")
                        await self._db.set(
                            "ntvote_" + str(handle_vote.msg_id),
                            self.vote_holding[str(handle_vote.msg_id)].export_data(),
                        )
                    except IndexError:
                        self.logger.error("failed to handle vote, choice index is out of range.")
                    except ValueError:
                        self.logger.error(
                            "failed to remove/add vote, user vote already exist or non-existant."
                        )
                    except KeyError:
                        self.logger.error("failed to remove/add vote, user vote are requester.")
                else:
                    pass
                try:
                    self._vote_lock.remove(handle_vote.msg_id)
                except ValueError:
                    pass
                self._voter_queue.task_done()
            except asyncio.CancelledError:
                return
