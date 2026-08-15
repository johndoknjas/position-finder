from __future__ import annotations

import io
import os
import pickle
from array import array
from typing import Iterator, Optional

import chess.pgn

INDEX_DIR = 'pgn-index'

class PgnIndex:
    """A byte-offset index over the games of a pgn file, along with each game's date.

    This makes it possible to visit the games of a huge database in an arbitrary order
    (in particular, most recent games first), without having to parse the whole file
    every time.
    """

    def __init__(self, pgn_path: str, offsets: array, dates: array) -> None:
        assert len(offsets) == len(dates)
        self._pgn_path = pgn_path
        self._offsets = offsets  # byte offset of each game's first header line
        self._dates = dates      # date of each game, as an int like 20260714 (0 if unknown)

    def num_games(self) -> int:
        return len(self._offsets)

    def date_of(self, game_num: int) -> int:
        return self._dates[game_num]

    def pgn_path(self) -> str:
        return self._pgn_path

    def game_nums_by_date(self, newest_first: bool = True) -> list[int]:
        """Returns the game numbers, sorted by date (ties broken by the game's position in
           the file, so that games from one event stay together)."""
        return sorted(range(self.num_games()),
                      key=lambda i: (self._dates[i], i), reverse=newest_first)

    def read_game_text(self, game_num: int) -> str:
        """Returns the raw pgn text of the given game."""
        start = self._offsets[game_num]
        end = self._offsets[game_num + 1] if game_num + 1 < self.num_games() else -1
        with open(self._pgn_path, 'rb') as f:
            f.seek(start)
            raw = f.read(end - start) if end != -1 else f.read()
        return raw.decode('utf-8', errors='replace')

    def read_games(self, game_nums: list[int]) -> Iterator[tuple[int, chess.pgn.Game]]:
        """Yields (game_num, game) for each requested game, keeping one file handle open."""
        with open(self._pgn_path, 'rb') as f:
            for game_num in game_nums:
                start = self._offsets[game_num]
                end = (self._offsets[game_num + 1] if game_num + 1 < self.num_games()
                       else os.path.getsize(self._pgn_path))
                f.seek(start)
                text = f.read(end - start).decode('utf-8', errors='replace')
                game = chess.pgn.read_game(io.StringIO(text))
                if game is not None:
                    yield game_num, game

def _parse_date(value: bytes) -> int:
    """Turns a pgn date header value such as b'1997.06.??' into an int like 19970600."""
    parts = value.split(b'.')
    if not parts or not parts[0][:4].isdigit():
        return 0
    date_int = int(parts[0][:4]) * 10000
    if len(parts) >= 2 and parts[1][:2].isdigit():
        date_int += int(parts[1][:2]) * 100
    if len(parts) >= 3 and parts[2][:2].isdigit():
        date_int += int(parts[2][:2])
    return date_int

def _index_path(pgn_path: str) -> str:
    stats = os.stat(pgn_path)
    key = f"{os.path.basename(pgn_path)}-{stats.st_size}-{int(stats.st_mtime)}"
    return os.path.join(INDEX_DIR, f"{key}.index")

def build_index(pgn_path: str, verbose: bool = True) -> PgnIndex:
    """Scans the whole pgn once, recording where each game starts and when it was played."""
    offsets: array = array('q')
    dates: array = array('i')
    offset = 0
    in_headers = False  # so that only the first [Event of a game counts as a game start
    pending_date = 0
    pending_event_date = 0
    with open(pgn_path, 'rb') as f:
        for line in f:
            if line.startswith(b'['):
                if line.startswith(b'[Event '):
                    if not in_headers:
                        if offsets:
                            dates.append(pending_date or pending_event_date)
                        offsets.append(offset)
                        pending_date = pending_event_date = 0
                        in_headers = True
                elif line.startswith(b'[Date "'):
                    pending_date = _parse_date(line[7:-3])
                elif line.startswith(b'[EventDate "'):
                    pending_event_date = _parse_date(line[12:-3])
            elif line.strip():
                in_headers = False
                if verbose and len(offsets) % 500000 == 0 and len(offsets) == len(dates) + 1:
                    print(f"  indexed {len(offsets)} games ({offset / 1e9:.2f} GB)", flush=True)
            offset += len(line)
    if offsets:
        dates.append(pending_date or pending_event_date)
    if verbose:
        print(f"  indexed {len(offsets)} games", flush=True)
    return PgnIndex(pgn_path, offsets, dates)

def get_index(pgn_path: str, verbose: bool = True) -> PgnIndex:
    """Returns a (cached, if possible) index of the given pgn file."""
    os.makedirs(INDEX_DIR, exist_ok=True)
    cache_path = _index_path(pgn_path)
    if os.path.exists(cache_path):
        with open(cache_path, 'rb') as f:
            offsets, dates = pickle.load(f)
        return PgnIndex(pgn_path, offsets, dates)
    if verbose:
        print(f"Building a game index for {pgn_path} (one time only)...", flush=True)
    index = build_index(pgn_path, verbose)
    with open(cache_path, 'wb') as f:
        pickle.dump((index._offsets, index._dates), f)
    return index

if __name__ == '__main__':
    import sys
    for path in sys.argv[1:]:
        idx = get_index(path)
        nums = idx.game_nums_by_date()
        print(f"{path}: {idx.num_games()} games, "
              f"newest {idx.date_of(nums[0])}, oldest {idx.date_of(nums[-1])}")
