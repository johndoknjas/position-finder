from copy import copy, deepcopy
from typing import Optional

import Utils

class Args:
    def __init__(self, args: list[str]) -> None:
        self._args: list[str] = copy(args)
        if self._args and self._args[0].endswith('.py'):
            self._args = self._args[1:]
        if self.feature() == 'name':
            assert self.num_args() <= 2 or not Utils.refers_to_db(self._args[2])
        elif isinstance(self.feature(), str):
            assert self.num_args() == 1
        else:
            assert not self._args

    def num_args(self) -> int:
        return len(self._args)

    def feature(self) -> Optional[str]:
        return self._args[0].lower() if self._args else None

    def dbs_aliases(self) -> list[str]:
        """Returns either an empty list, or a list of size 1"""
        return [self._args[1]] if self.num_args() >= 2 else []

    def additional_args(self) -> list[str]:
        """Returns a list of any additional cli args (all lowercased) entered for the `name` feature."""
        return [x.lower() for x in self._args[2:]]

_args: Optional[Args] = None

def set_args(args: list[str]) -> None:
    global _args
    assert not _args
    _args = Args(args)

def args() -> Args:
    assert _args
    return deepcopy(_args)