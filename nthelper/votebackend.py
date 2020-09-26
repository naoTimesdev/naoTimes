import asyncio
import logging
import os
from datetime import datetime, timezone
from typing import Dict, List, Union

from .utils import blocking_write_files, write_files


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

        if self._type not in ("yn", "mul", "kickban"):
            raise ValueError(f"Unknown '{self._type}' value in vote_type.")

    def export_data(self):
        raise NotImplementedError()

    def get_id(self) -> int:
        """Get message ID

        :return: Message ID
        :rtype: int
        """
        return self._mid

    def get_tiemout(self) -> Union[int, float]:
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
        super().__init__(requester_id, message_data, vote_question, vote_answers, timeout, vote_type="mul")

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
            for vote in self._answers:
                vote_results[vote["name"]] = vote["tally"]
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

    def __init__(self, fcwd: str):
        self.logger = logging.getLogger("nthelper.votebackend.VoteWatcher")
        self._fcwd = fcwd

        self.vote_holding: Dict[str, Union[VotingData, VotingKickBan]] = {}
        self._vote_lock: List[int] = []

        self.done_queue: asyncio.Queue = asyncio.Queue()
        self._voter_queue: asyncio.Queue = asyncio.Queue()

        self._clock_task: asyncio.Task = asyncio.Task(self._clock_tick())
        self._voter_task: asyncio.Task = asyncio.Task(self._handle_voter())

    def stop_and_flush(self):
        """
        This will halt every process and wait for everything to finish tallying,
        then stop it, and then clean everything.
        """
        self.logger.info("stopping all tasks...")
        self._clock_task.cancel()
        self._voter_task.cancel()
        self.logger.info("saving all vote data to file...")
        all_vote_data = [int(msg_id) for msg_id in self.vote_holding.keys()]
        self._vote_lock.extend(all_vote_data)

        for msg_id, vote_handler in self.vote_holding.items():
            save_path = os.path.join(self._fcwd, "vote_data", f"{msg_id}.votedata")
            blocking_write_files(vote_handler.export_data(), save_path)

    def generate_answers(self, answers_options: list):
        final_data = []
        for n, opts in enumerate(answers_options):
            data_internal = {
                "id": n,
                "tally": 0,
                "voter": [],
                "name": opts,
            }
            final_data.append(data_internal)
        return final_data

    async def stop_watching_vote(self, message_id: int):
        if str(message_id) not in self.vote_holding:
            raise KeyError("Message doesn't exists")
        self._vote_lock.append(message_id)

        self.logger.info(f"removing {message_id} from voting data...")
        vote_handler = self.vote_holding[str(message_id)]
        await self.done_queue.put(vote_handler)
        del self.vote_holding[str(message_id)]
        save_path = os.path.join(self._fcwd, "vote_data", f"{message_id}.votedata")
        os.remove(save_path)
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

        save_path = os.path.join(self._fcwd, "vote_data", f"{message_data['id']}.votedata")
        await write_files(vote_handler.export_data(), save_path)

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
            {"id": "y", "tally": 0, "voter": [], "name": "Yes"},
            {"id": "n", "tally": 0, "voter": [], "name": "No"},
        ]
        if override_answers is not None:
            yn_watcher = override_answers
        vote_handler = VotingKickBan(
            requester_id, message_data, user_target, yn_watcher, timeout, limit, hammer_type
        )
        self.vote_holding[str(message_data["id"])] = vote_handler

        save_path = os.path.join(self._fcwd, "vote_data", f"{message_data['id']}.votedata")
        await write_files(vote_handler.export_data(), save_path)

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
                for n, vote_handler in enumerate(self.vote_holding.values()):
                    if vote_handler.get_id() in self._vote_lock:
                        continue
                    vote_handler.refresh()
                    if vote_handler.is_timeout():
                        await self.done_queue.put(vote_handler)
                        to_remove.append(str(vote_handler.get_id()))

                for rem in to_remove:
                    del self.vote_holding[rem]

                await asyncio.sleep(1.0)
            except asyncio.CancelledError:
                return

    async def _handle_voter(self):
        while True:
            try:
                handle_vote: UserVote = await self._voter_queue.get()
                self._vote_lock.append(handle_vote.msg_id)
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
                        save_path = os.path.join(self._fcwd, "vote_data", f"{handle_vote.msg_id}.votedata")
                        await write_files(self.vote_holding[str(handle_vote.msg_id)].export_data(), save_path)
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
