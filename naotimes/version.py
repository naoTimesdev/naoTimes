from typing import Literal, NamedTuple

__all__ = ("__version__", "version_info")


class VersionInfo(NamedTuple):
    major: int
    minor: int
    micro: int
    serial: int
    level: Literal["alpha", "beta", "candidate", "development", "final"]

    @property
    def text(self) -> str:
        fx = f"{self.major}.{self.minor}.{self.micro}"
        if self.level and self.level != "final":
            fx += f"-{self.level} {self.serial}"
        return fx

    @property
    def shorthand(self) -> str:
        shorthand = {"alpha": "a", "beta": "b", "candidate": "rc", "development": "dev", "final": ""}
        short = shorthand.get(self.level, "-" + self.level)
        if short:
            short += str(self.serial)
        return f"{self.major}.{self.minor}.{self.micro}-{short}"

    @classmethod
    def parse(cls, text: str) -> "VersionInfo":
        TOKENIZED = list(text)
        LEVEL_TOKEN = ["a", "b", "c", "d", "dev", "rc"]
        VERSION_TOKEN = []
        LEVEL = ""
        TOKEN_COMBINE = ""
        for T in TOKENIZED:
            if T.isdigit():
                TOKEN_COMBINE += T
            else:
                if T == "." and TOKEN_COMBINE:
                    VERSION_TOKEN.append(int(TOKEN_COMBINE))
                    TOKEN_COMBINE = ""
                elif T in LEVEL_TOKEN and not LEVEL:
                    LEVEL = T
                    if TOKEN_COMBINE:
                        VERSION_TOKEN.append(int(TOKEN_COMBINE))
                        TOKEN_COMBINE = ""
                else:
                    continue
        if TOKEN_COMBINE:
            VERSION_TOKEN.append(int(TOKEN_COMBINE))
        if len(VERSION_TOKEN) == 3:
            VERSION_TOKEN.append(0)

        TOKEN_LEVEL_LONG = {
            "a": "alpha",
            "b": "beta",
            "c": "candidate",
            "d": "development",
            "dev": "development",
            "rc": "candidate",
        }
        return cls(*VERSION_TOKEN, TOKEN_LEVEL_LONG.get(LEVEL, LEVEL))


__version__ = "3.1.0b1"
version_info = VersionInfo.parse(__version__)
