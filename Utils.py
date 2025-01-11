from __future__ import annotations

import shlex
import os

def remove_lines_starting_with(multline_str: str, starting_substr: str) -> str:
    as_lst = multline_str.splitlines()
    return '\n'.join(line for line in as_lst if not line.startswith(starting_substr))

def get_aliases() -> dict[str, str]:
    with open('aliases.txt', mode='r') as f:
        return {k.lower(): v for k,v in (line.strip().split(maxsplit=1) for line in f)}

def refers_to_db(s: str) -> bool:
    """Returns true if s likely refers to an alias, pgn path, or study"""
    return (
        s.endswith('.pgn') or
        s in get_aliases().keys() or
        s.count('/') >= 3 or
        s.count('\\') >= 3 or
        any(s in shlex.split(l) for l in get_aliases().values())
    )

def most_recent_file(dir: str) -> str:
    """Returns the filename of the most recent file in the directory."""
    return max((os.path.join(dir, basename) for basename in os.listdir(dir)), key=os.path.getmtime)