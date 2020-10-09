import asyncio
import logging
import os
import tempfile
import time

import aiofiles
from aiofiles.os import remove

from .utils import generate_custom_code


class CPPTestError(Exception):
    pass


class CPPTestSanitizeError(CPPTestError):
    def __init__(self, msg=None):
        super().__init__(msg or "Sanitization error occured, code contain non-allowed stuff.")


class CPPTestCompileError(CPPTestError):
    def __init__(self, err_out):
        super().__init__(err_out)


class CPPTestTimeoutError(CPPTestError):
    def __init__(self):
        super().__init__("Code took way too long to run. (Limit 20s)")


class CPPTestRuntimeError(CPPTestError):
    def __init__(self, msg):
        super().__init__(msg)


class CPPUnitTester:

    TEMP_FOLDER = tempfile.gettempdir()

    def __init__(self, code, input_data=[]):
        self._code = code
        self._in_data = input_data
        self._out_name = os.path.join(self.TEMP_FOLDER, "cu_" + generate_custom_code())  # nosec

        self._compiled = False
        self.logger = logging.getLogger("cpputest.CPPUnitTester")

    def is_compiled(self):
        return self._compiled

    def outputed(self):
        return self._out_name

    async def cleanup_data(self):
        self.logger.info("cleaning up junks...")
        if os.path.isfile(self._out_name + ".cpp"):
            await remove(self._out_name + ".cpp")
        if os.path.isfile(self._out_name):
            await remove(self._out_name)

    def _sanitize_code(self):
        self.logger.info("sanitizing code...")
        if "system(" in self._code or "system (" in self._code:
            self.logger.error("code contain system(), cancelling...")
            raise CPPTestSanitizeError("Code contained system() command, that's not allowed.")

    async def _run_in_async(self, args: list, is_compile=False):
        """Run subprocess in async env

        :param args: subprocess args to run
        :type args: list
        :param is_compile: is the args to compile code or not, defaults to False
        :type is_compile: bool, optional
        :raises CPPTestTimeoutError: If the code ran past 20 seconds marks
        :raises CPPTestTimeoutError: [description]
        :return: error code, stdot data, stderr data
        :rtype: Tuple[int, Union[str, List[str]], Union[str, List[str]]]
        """
        proc = await asyncio.create_subprocess_shell(
            " ".join(args),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            stdin=asyncio.subprocess.PIPE,
        )

        if is_compile:
            stdout, stderr = await proc.communicate()
            return proc.returncode, stdout.decode(), stderr.decode()
        elif self._in_data and not is_compile:
            try:
                idata = "\n".join(self._in_data)
                stdout, stderr = await asyncio.wait_for(proc.communicate(idata.encode("utf-8")), 20.0)
            except asyncio.TimeoutError:
                proc.kill()
                raise CPPTestTimeoutError()
            return proc.returncode, stdout.decode(), stderr.decode()
        elif not self._in_data and not is_compile:
            try:
                stdout, stderr = await asyncio.wait_for(proc.communicate(), 20.0)
            except asyncio.TimeoutError:
                proc.kill()
                raise CPPTestTimeoutError()
            return proc.returncode, stdout.decode(), stderr.decode()

    async def save_and_compile(self):
        self._sanitize_code()
        self.logger.info("saving to file...")
        async with aiofiles.open(self._out_name + ".cpp", "w", encoding="utf-8") as fp:
            await fp.write(self._code)

        self.logger.info("executing g++...")
        compile_code = ["g++", "-o", self._out_name, f"{self._out_name}.cpp"]
        err_code, _, err_shit = await self._run_in_async(compile_code, True)
        if err_code != 0:
            self.logger.error(err_shit)
            raise CPPTestCompileError(err_shit)
        self._compiled = True

    async def run_code(self):
        if not self._compiled:
            await self.save_and_compile()

        start_run = time.perf_counter()
        run_args = [self._out_name]
        self.logger.info("executing code...")
        err_code, out_shit, err_shit = await self._run_in_async(run_args)
        end_run = time.perf_counter()
        time_taken = round((end_run - start_run) * 1000, 2)
        if err_code != 0:
            self.logger.error(err_shit)
            raise CPPTestRuntimeError(err_shit)
        return err_code, out_shit, time_taken
