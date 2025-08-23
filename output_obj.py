from __future__ import annotations
import os
from typing import Optional

import rich.console
from rich.style import Style

from Specs import Specs

console = rich.console.Console()

class Output:
    """Represents a number of variables used in outputting results to the user on games found."""

    def __init__(self) -> None:
        self._output_str = self._secondary_output_str = ''
        self._hits = self._secondary_hits = self._num_games_parsed = 0
        self._newest_hit: Optional[str] = None

    def increment_hits(self, secondary_one: bool = False) -> None:
        if secondary_one:
            self._secondary_hits += 1
        else:
            self._hits += 1

    def prep_for_new_game(self) -> None:
        """Increments the counter for #games, and clears the newest hit."""
        self._num_games_parsed += 1
        self.clear_newest_hit()

    def append_to_output_str(self, append: str, secondary_one: bool = False) -> None:
        if secondary_one:
            self._secondary_output_str += append
        else:
            self._output_str += append

    def add_newest_hit(self, newest_hit: str, update_primary_vars: bool = True,
                       update_secondary_vars: bool = False) -> None:
        assert self._newest_hit is None
        self._newest_hit = f"{newest_hit}\n\n\n"
        if update_primary_vars:
            self.append_to_output_str(self._newest_hit)
            self.increment_hits()
        if update_secondary_vars:
            self.append_to_output_str(self._newest_hit, True)
            self.increment_hits(True)

    def clear_newest_hit(self) -> None:
        self._newest_hit = None

    def output_str(self, secondary_one: bool = False) -> str:
        return self._secondary_output_str if secondary_one else self._output_str

    def num_games(self) -> int:
        return self._num_games_parsed

    def num_hits(self, secondary_one: bool = False) -> int:
        return self._secondary_hits if secondary_one else self._hits

    def newest_hit(self) -> str:
        assert self._newest_hit is not None
        return self._newest_hit

    def newest_hit_exists(self) -> bool:
        return self._newest_hit is not None

    def print_newest_hit(self, specs: Specs) -> None:
        if specs.type_of_position() != 'name' or specs.verbose_for_name_feature():
            print(self.newest_hit())
            return
        line, rem_lines = self.newest_hit().split('\n', 1)
        texts = {
            'players': line.split(', opening: ')[0],
            'opening': line.split('opening: ', 1)[1].split(', event: ')[0],
            'event': line.split('event: ', 1)[1].split(', source: ')[0],
            'source': line.split('source: ', 1)[1]
        }
        red_key = next(
            (
                k for k in ('event', 'players', 'opening') if any(
                    x.lower() in texts[k].lower() for x in specs.get_substrs_name_feature()
                )
            ),
            None
        )
        for k, text in texts.items():
            if k != 'players':
                print(f", {k}: ", end='')
            color = "#ff5555" if k == red_key else "#0000ee" if 'https' in text else "#ffffff"
            console.print(text, end='', highlight=False, style=Style(color=color))
        print('\n' + rem_lines)

    def print_and_write_data(self, specs: Specs) -> None:
        """Prints the data and writes it to a file."""
        os.makedirs((folder_name := 'results'), exist_ok=True)
        output_filename = os.path.join(folder_name, specs.filename_of_output())
        if specs.type_of_position() == "underpromotion":
            print("\n\nGames found where underpromotion best:\n" + self.output_str(True))
            print("Games found where underpromotion best and player missed it:\n"
                    + self.output_str())
            print(f"#Games where underpromotion is best move: {self.num_hits(True)}")
            print(f"#Games where underpromotion is best move and player missed it: {self.num_hits()}")
            print(f"#Games parsed: {self.num_games()}")

            f = open(f"{output_filename}-games where underpromotion is best move.pgn", "w")
            f.write(f"{self.output_str(True)}#Games parsed: {self.num_games()}\nHit counter: " +
                    f"{self.num_hits(True)}\n\n")
            f.close()

            f = open(f"{output_filename}-games where underpromotion is best and player missed it.pgn", "w")
            f.write(f"{self.output_str()}#Games parsed: {self.num_games()}\nHit counter: " +
                    f"{self.num_hits()}\n\n")
            f.close()
        else:
            print(f"#Games parsed: {self.num_games()}")
            print(f"Hit_counter = {self.num_hits()}\n")
            if self.newest_hit_exists():
                if specs.pgn().endswith('.pgn'):
                    source_name = specs.pgn().replace('/', '\\').split('\\')[-1]
                else:
                    source_name = 'lichess study'
                print(f"Hit from {source_name}:")
                self.print_newest_hit(specs)
            f = open(f"{output_filename}.pgn", "w")
            f.write(f"{self.output_str()}#Games parsed: {self.num_games()}\nHit counter: " +
                    f"{self.num_hits()}\n\n")
            f.close()
