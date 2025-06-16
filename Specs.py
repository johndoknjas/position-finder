from __future__ import annotations
from typing import List, Tuple, Optional
from copy import copy

def file_char_to_int(file_char: str) -> int:
    file_char = file_char.lower()
    assert 'a' <= file_char <= 'h'
    return 1 + ord(file_char) - ord('a')

class Piece_Quantities:
    """Stores data representing piece chars that must be present, and (optionally) in exactly
       what quantities."""

    def __init__(self, requirements_string: str) -> None:
        requirements_string = ''.join(requirements_string.split())
        self._start_row, self._start_file = 1, 1
        self._end_row, self._end_file = 8, 8
        self._requirements: List[Tuple[str, Optional[int]]] = []
        self._should_exclude = requirements_string.startswith(('~', '!'))
        requirements_string = requirements_string.lstrip('~!')

        if len(substrings := requirements_string.split(':')) == 2:
            board_area = substrings[0].lower()
            requirements_string = substrings[1]
            if board_area.startswith('row'):
                self._start_row = self._end_row = int(board_area[-1])
            elif board_area.startswith('file'):
                self._start_file = self._end_file = file_char_to_int(board_area[-1])
            else:
                assert len(board_area) == 2
                self._start_file = self._end_file = file_char_to_int(board_area[0])
                self._start_row = self._end_row = int(board_area[1])

        for i, c in enumerate(requirements_string):
            if c.isdigit():
                continue
            quantity = None
            if i+1 < len(requirements_string) and requirements_string[i+1].isdigit():
                quantity = int(requirements_string[i+1])
            self._requirements.append((c, quantity))

    def get_requirements(self) -> List[Tuple[str, Optional[int]]]:
        return self._requirements

    def start_row(self) -> int:
        """Returns the first row to consider."""
        return self._start_row

    def end_row(self) -> int:
        """Returns the last row to consider."""
        return self._end_row

    def start_file(self) -> int:
        """Returns the first file to consider, as an int (1-8)."""
        return self._start_file

    def end_file(self) -> int:
        """Returns the last file to consider, as an int (1-8)."""
        return self._end_file

    def should_exclude(self) -> bool:
        """Returns whether the pieces specified by this object must not be present in the specified area."""
        return self._should_exclude

class GameToSearchAfter:
    def __init__(self, start_at_0: bool = False) -> None:
        self._game_details: Optional[tuple[str,str,str]] = None
        self._game_num: Optional[int] = None
        if start_at_0:
            self._game_num = 0
            return
        user_input = input("To start the search after a particular game number in the database, enter it here. " +
                           "\nOr, to start the search in the DB after a certain game, enter the last name of " +
                           "White, then a space, then the last name of Black, then a space, then the year. " +
                           "\nOtherwise to not skip any games, just press enter: ")
        try:
            self._game_num = int(user_input or '0')
        except ValueError:
            assert len(words := user_input.split()) == 3
            self._game_details = (words[0], words[1], words[2]) # doing it this way to satisfy mypy
        assert (self.game_num() is None) != (self.game_details() is None)

    def game_num(self) -> Optional[int]:
        return self._game_num

    def game_details(self) -> Optional[Tuple[str,str,str]]:
        """Returns either None, or a tuple with white's name, black's name, and the date."""
        return self._game_details

class Specs:
    def __init__(self, type_of_position: Optional[str] = None) -> None:
        self._output_filename: Optional[str] = None
        self._pgn: Optional[str] = None
        feat_options = ('endgame', 'top moves', 'skip move', 'underpromotion', 'name')
        options_quotes = tuple(f"'{x}'" for x in feat_options)
        self._type_of_position = (
            type_of_position or
            input(f"Enter {', '.join(options_quotes[:-1])}, or {options_quotes[-1]}: ")
        ).lower()
        assert self._type_of_position in feat_options
        self._game_to_search_after = GameToSearchAfter(self._type_of_position == 'name')
        self._move_to_begin_at = int(
            input("Enter the move to start searching for matching positions in each game: ") or "0"
        ) if self._type_of_position != 'name' else 0
        self._substrings_if_name_feature: Optional[List[str]] = None
        self._verbose_name_feature: Optional[bool] = None

    def filename_of_output(self) -> str:
        assert self._output_filename is not None
        return self._output_filename

    def set_output_filename(self, name: str) -> None:
        self._output_filename = name

    def type_of_position(self) -> str:
        return self._type_of_position

    def set_pgn(self, pgn: str) -> None:
        self._pgn = pgn

    def pgn(self) -> str:
        assert self._pgn is not None
        return self._pgn

    def game_num_to_search_after(self) -> Optional[int]:
        return self._game_to_search_after.game_num()

    def game_details_to_search_after(self) -> Optional[Tuple[str,str,str]]:
        """If not None, returns a tuple for the name of white, name of black, and date."""
        return self._game_to_search_after.game_details()

    def do_not_skip_any_games(self) -> bool:
        return self._game_to_search_after.game_details() is None and self._game_to_search_after.game_num() == 0

    def move_to_begin_at(self) -> int:
        return self._move_to_begin_at

    def default_output_interval(self) -> int:
        return {'endgame': 200, 'name': 40000}.get(self.type_of_position(), 40)

    def set_substrs_name_feature(self, substrs: List[str]) -> None:
        assert self.type_of_position() == 'name'
        self._substrings_if_name_feature = copy(substrs)

    def get_substrs_name_feature(self) -> List[str]:
        assert self.type_of_position() == 'name' and self._substrings_if_name_feature
        return copy(self._substrings_if_name_feature)

    def set_verbose_name_feature(self, verbose: bool) -> None:
        assert self.type_of_position() == 'name'
        self._verbose_name_feature = verbose

    def verbose_for_name_feature(self) -> bool:
        assert self.type_of_position() == 'name' and self._verbose_name_feature is not None
        return self._verbose_name_feature