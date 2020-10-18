import argparse
import shlex
from typing import Any, Dict

from discord.ext import commands


class ArgumentParserError(Exception):
    def __init__(self, message):
        self.message = message

    def __repr__(self):
        return self.message


class HelpException(Exception):
    def __init__(self, message):
        self.message = message

    def __repr__(self):
        return self.message


class BotArgumentParser(argparse.ArgumentParser):
    def print_help(self, file=None):
        raise HelpException(self.format_help())

    def exit(self, status=0, message=None):
        raise HelpException(message)

    def error(self, message=None):
        raise ArgumentParserError(message)


bot_parser = BotArgumentParser(prog="!", usage="!", formatter_class=argparse.ArgumentDefaultsHelpFormatter)
subparser = bot_parser.add_subparsers(dest="command")


class Arguments:
    def __init__(self, name):
        self._cmd_args = []
        self._cmd_name = name

    def add_args(self, *args, **kwargs):
        self._cmd_args.insert(0, (args, kwargs))


class CommandArgParse(commands.Converter):
    def __init__(self, args: Arguments):
        self._args: Arguments = args
        self._defaults_map: Dict[str, Any] = {}
        self._any_kw = False
        self._init_args()

    @staticmethod
    def _parse_error(err_str: str) -> str:
        if err_str.startswith("unrecognized arguments"):
            err_str = err_str.replace("unrecognized arguments", "Argumen tidak diketahui")
        elif err_str.startswith("the following arguments are required"):
            err_str = err_str.replace(
                "the following arguments are required",
                "Argumen berikut wajib diberikan",
            )
        if "usage" in err_str:
            err_str = (
                err_str.replace("usage", "Gunakan")
                .replace("positional arguments", "Argumen yang diwajibkan")
                .replace("optional arguments", "Argumen opsional")
                .replace(
                    "show this help message and exit",
                    "Perlihatkan bantuan perintah",
                )
            )
            err_str = err_str.replace("Gunakan: ! ", "Gunakan: !")
        return err_str

    def _init_args(self):
        parser = subparser.add_parser(self._args._cmd_name)
        if self._args._cmd_args:
            for arg_args, arg_kwargs in self._args._cmd_args:
                get_args_path = arg_args[0]
                default = arg_kwargs.get("default")
                if default is not None:
                    if get_args_path.startswith("-"):
                        self._defaults_map[get_args_path] = default
                if not get_args_path.startswith("-") and not self._any_kw:
                    self._any_kw = True
                parser.add_argument(*arg_args, **arg_kwargs)

        self._parser = parser

    def _parse_args(self, argument: str):
        try:
            return self._parser.parse_args(shlex.split(argument))
        except ArgumentParserError as argserror:
            return self._parse_error(str(argserror))
        except HelpException as help_:
            return self._parse_error(str(help_))

    async def convert(self, ctx, argument):
        return self._parse_args(argument)

    def show_help(self):
        return self._parse_args("-h")
