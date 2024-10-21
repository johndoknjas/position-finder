from __future__ import annotations
from typing import Optional, Union, List
import itertools
from copy import deepcopy
import time
import os
import shlex

import chess.pgn
from models import Stockfish
from output_obj import Output
from Specs import Piece_Quantities, Specs
import studies
import Utils

PIECE_CHARS: List[str] = ["P", "p", "N", "n", "B", "b", "R", "r", "Q", "q", "K", "k"]

def get_endgame_specs_from_user() -> List[Piece_Quantities]:
    endgame_specs: List[Piece_Quantities] = []
    while True:
        piece_requirements = input("Enter a piece requirement string, or just press enter to stop: ")
        if piece_requirements == "":
            return endgame_specs
        endgame_specs.append(Piece_Quantities(piece_requirements))

def num_pieces_in_fen(fen: str) -> int:
    return sum(1 for c in fen.split(' ')[0] if c in PIECE_CHARS)

def file_int_to_char(file_int: int) -> str:
    assert 1 <= file_int <= 8
    return chr(ord('a') + file_int - 1)

def is_piece_in_board(stockfish: Stockfish, piece_char: str, row_start: int, row_end: int,
                      col_start: int, col_end: int, num_of_this_piece: Optional[int] = None) -> bool:
    """If the optional num_of_this_piece param is left as None, then the function returns true iff
       at least one of the specified piece char is in the board.
       Otherwise, exactly the specified number of the piece must be present."""

    hit_counter = 0
    for row in range(row_start, row_end+1):
        for col in range(col_start, col_end+1):
            square = file_int_to_char(col) + str(row)
            if ((square_contents := stockfish.get_what_is_on_square(square)) is not None and
                square_contents.value == piece_char):
                if num_of_this_piece is None:
                    return True
                hit_counter += 1
    return num_of_this_piece is not None and hit_counter == num_of_this_piece

def does_board_meet_piece_reqs(stockfish: Stockfish, pieces: Piece_Quantities) -> bool:
    """Pre-condition: the stockfish object must be set to the position in question."""
    init_row, end_row = pieces.start_row(), pieces.end_row()
    init_file, end_file = pieces.start_file(), pieces.end_file()
    should_exclude = pieces.should_exclude()
    return all(should_exclude != is_piece_in_board(stockfish, requirement[0], init_row, end_row,
                                                   init_file, end_file, num_of_this_piece=requirement[1])
               for requirement in pieces.get_requirements())

def does_position_satisfy_specs(stockfish: Stockfish, fen: str, position_specs: List[Piece_Quantities]) -> bool:
    stockfish.set_fen_position(fen, send_ucinewgame_token = False)
    return all(does_board_meet_piece_reqs(stockfish, spec) for spec in position_specs)

def satisfies_bound(move_dict: dict, bound: Optional[float], is_lower_bound: bool) -> bool:
    """bound is in centipawn evaluation, as a float (e.g., 2.17) or None.
       For move_dict, if the "Centipawn" key has a value, it will already have been
       converted to decimal form (so nothing like 37 for a 0.37 evaluation)."""
    if bound is None:
        return True
    if is_lower_bound:
        if move_dict["Mate"] is not None:
            return move_dict["Mate"] > 0
        else:
            return move_dict["Centipawn"] >= bound
    else:
        if move_dict["Mate"] is not None:
            return move_dict["Mate"] < 0
        else:
            return move_dict["Centipawn"] <= bound

def does_position_satisfy_bounds(stockfish: Stockfish, fen: str, bounds: List[Optional[float]]) -> bool:
    """bounds is a list, where the 0th element is the lower bound for the first move,
       the 1st element is the upper bound for the first move, etc (for however many
       top moves). It may just be the one top move, or it could be 1 more, 2 more, etc.
       len(bounds) will be even."""

    # Also allow for if it's Black to move (so if the evals are negative, in Black's favour).
    stockfish.set_fen_position(fen, send_ucinewgame_token = False)
    depth_increments = [8, 12, 15]
    eval_multiplier = 1 if "w" in fen else -1
    # In order to work with evaluations that are relative to the player whose turn it is,
    # rather than positive being white and negative being black.
    for depth in depth_increments:
        stockfish.set_depth(depth)
        top_moves: List[dict] = stockfish.get_top_moves(int(len(bounds) / 2))
        if len(top_moves) != len(bounds) / 2:
            return False
        for i in range(len(top_moves)):
            if top_moves[i]["Centipawn"] is not None:
                top_moves[i]["Centipawn"] *= (eval_multiplier * 0.01)
            if top_moves[i]["Mate"] is not None:
                top_moves[i]["Mate"] *= eval_multiplier

        # Now see if each of the bounds is satisfied:
        for i in range(len(bounds)):
            is_lower_bound = (i % 2) == 0
            if not satisfies_bound(top_moves[int(i/2)], bounds[i], is_lower_bound):
                return False
    # End of outer for loop - if control makes it here, return True.
    return True

def is_underpromotion_best(stockfish: Stockfish, fen: str) -> Union[bool, str]:
    """Returns False if not. Otherwise, returns the underpromotion move (e.g., e7e8r)."""

    stockfish.set_fen_position(fen, send_ucinewgame_token = False)
    depth_increments = [12, 15, 25]
    eval_multiplier = 1 if "w" in fen else -1
    # In order to work with evaluations that are relative to the player whose turn it is,
    # rather than positive being white and negative being black.

    if (("w" in fen and not does_board_meet_piece_reqs(stockfish, Piece_Quantities("row 7: P"))) or
        ("w" not in fen and not does_board_meet_piece_reqs(stockfish, Piece_Quantities("row 2: p")))):
        return False # Since a promotion is not even possible.

    for depth in depth_increments:
        stockfish.set_depth(depth)
        top_moves: List[dict] = stockfish.get_top_moves(2)
        if len(top_moves) != 2:
            return False
        for i in range(len(top_moves)):
            assert (top_moves[i]["Centipawn"] is None) != (top_moves[i]["Mate"] is None)
            if top_moves[i]["Centipawn"] is not None:
                top_moves[i]["Centipawn"] *= (eval_multiplier * 0.01)
            if top_moves[i]["Mate"] is not None:
                top_moves[i]["Mate"] *= eval_multiplier

        if len(top_moves[0]["Move"]) != 5 or top_moves[0]["Move"][4] not in ('n', 'b', 'r'):
            return False # top move isn't an underpromotion
        if top_moves[1]["Mate"] is not None:
            if top_moves[1]["Mate"] > 0:
                return False # Second best move would lead to mate for the player anyway.
        if top_moves[0]["Mate"] is not None:
            if top_moves[0]["Mate"] < 0:
                return False # Even the best move gets the player mated.
        if top_moves[1]["Centipawn"] is not None:
            if top_moves[1]["Centipawn"] > 3:
                return False # Second best move would be winning anyway.
        if top_moves[0]["Centipawn"] is not None:
            if top_moves[0]["Centipawn"] < -3:
                return False # Even the best move is losing.
            if top_moves[1]["Centipawn"] is not None:
                if top_moves[0]["Centipawn"] - top_moves[1]["Centipawn"] < 0.5:
                    return False # Underpromoting is not significantly better.
                else:
                    print("top move centipawn for player: " + str(top_moves[0]["Centipawn"]))
                    print("second top move centipawn for player: " + str(top_moves[1]["Centipawn"]))
                    print(fen + "   depth: " + str(depth))
    # End of outer for loop

    return top_moves[0]["Move"]

def get_bounds_from_user(input_messages: List[str]) -> List[Optional[float]]:
    bounds_as_strings = []
    print("For each of the following, type 'None' or just press enter if you don't want a bound.")
    for message in input_messages:
        bounds_as_strings.append(input(message))
    bounds: List[Optional[float]] = []
    for current_bound_as_string in bounds_as_strings:
        if current_bound_as_string in ["", "None"]:
            bounds.append(None)
        else:
            bounds.append(float(current_bound_as_string))
    return bounds

def switch_whose_turn(fen: str) -> str:
    return fen.replace("w", "b") if "w" in fen else fen.replace(" b ", " w ")

def try_apply_aliases(text: str) -> str:
    """If `text` is an alias, return what it stands for. Otherwise, return `text`."""
    with open('aliases.txt', mode='r') as f:
        lines = [line.strip().split(maxsplit=1) for line in f]
        return next((line[1] for line in lines if line[0].lower() == text.lower()), text)

def pgn_name_not_study(name: str) -> bool:
    """Returns True if probably a pgn name, False if probably a study."""
    return name.endswith('.pgn') or len(name) != 8

def main() -> None:
    if not __debug__:
        raise RuntimeError("Python isn't running in the default debug mode.")
    specs = Specs()
    database_names = try_apply_aliases(
        input("Enter the names (or aliases) of your databases/studies: ")
    )
    endgame_specs = bounds = num_pieces_desired_endgame = name_contains = None

    pgns = []
    for name in shlex.split(database_names):
        if pgn_name_not_study(name) and not name.endswith('.pgn'):
            name += '.pgn'
        pgns.append(name)

    if specs.type_of_position() == "endgame":
        num_pieces_desired_endgame = int(user_input) if (
            user_input := input("Exactly how many pieces in this endgame: ")
        ) else None
        endgame_specs = get_endgame_specs_from_user()
        # Each element will store all the piece(s) and pawn(s) the user does/doesn't want,
        # optionally in a particular row and/or column, and optionally in what exact quantities.
        # E.g.: "~row 2: PK2p" (for a requirement) means to not have any of a white pawn, white king, or
        # 2 black pawns in row 2.

    elif specs.type_of_position() == "top moves":
        bounds = get_bounds_from_user(["Enter the lower bound the top move's eval: ",
                                       "Upper bound for top move's eval: ",
                                       "Lower bound for the second top move's eval: ",
                                       "Upper bound for the second top move's eval: "])
        # bounds will be used later in the main while loop. This list will store 4 floats,
        # representing the info above (in that order). So, lower bound for the top move in the
        # first spot in the list, etc.

    elif specs.type_of_position() == "skip move":
        bounds = get_bounds_from_user(["Enter the lower bound eval for a position: ",
                                       "Upper bound for a position: ",
                                       "Lower bound eval (relative to opponent this time) for the position with move skipped : ",
                                       "Upper bound for the position with move skipped : "])
        # Again, like in the elif above, here bounds will be used later in the main loop.

    elif specs.type_of_position() == 'name':
        name_contains = shlex.split(input('Enter substrings to check for in some game headers: ').lower())
        print(f"Checking for these substrings: {name_contains}")

    for pgn in pgns:
        specs_copy = deepcopy(specs)
        specs_copy.set_output_filename(str(int(time.time_ns())))
        specs_copy.set_pgn(pgn)
        process_pgn(specs_copy, name_contains, num_pieces_desired_endgame, endgame_specs, bounds)
        print("****===================================****\n\n\n\n")

def process_pgn(specs: Specs, name_contains: Optional[list[str]],
                num_pieces_desired_endgame: Optional[int], endgame_specs, bounds) -> None:
    stockfish = Stockfish(path="stockfish")
    temp_pgn_file = None
    if specs.pgn().endswith('.pgn'):
        pgn = open(specs.pgn(), "r", errors="replace", encoding="utf-8-sig")
    else:
        pgn_data = studies.get_study_pgn(specs.pgn())
        os.makedirs((folder_name := 'results'), exist_ok=True)
        temp_pgn_file = os.path.join(folder_name, f"{time.time_ns()}.txt")
        f = open(temp_pgn_file, "w")
        f.write(pgn_data)
        f.close()
        pgn = open(temp_pgn_file, "r")
    output_data = Output()
    reached_first_game_for_search = specs.do_not_skip_any_games()
    while True:
        output_data.prep_for_new_game()
        if not reached_first_game_for_search:
            headers = chess.pgn.read_headers(pgn)
            if (game_num := specs.game_num_to_search_after()) is not None:
                reached_first_game_for_search = output_data.num_games() >= game_num
            else:
                assert (game_details := specs.game_details_to_search_after()) is not None
                white, black, date = game_details
                reached_first_game_for_search = (
                    headers is not None and white in headers.get("White", "?") and
                    black in headers.get("Black", "?") and date in headers.get("Date", "?")
                )
            if reached_first_game_for_search:
                print("Done skipping games")
            if output_data.num_games() % 20000 == 0:
                print("Skipped " + str(output_data.num_games()))
            continue

        if specs.type_of_position() == 'name':
            if (headers := chess.pgn.read_headers(pgn)) is None:
                break
            white, black, opening, event, source = (
                headers.get(x, '?') for x in ("White", "Black", "Opening", "Event", "Source")
            )
            assert name_contains is not None
            if any(x.lower() in y.lower() for x, y in itertools.product(
                name_contains, (white, black, opening, event)
            )):
                output_data.add_newest_hit(
                    f"{white}-{black}, opening: {opening}, event: {event}, source: {source}"
                )
        else:
            if (current_game := chess.pgn.read_game(pgn)) is None:
                break
            current_game_as_str = Utils.remove_lines_starting_with(
                str(current_game), '[Site "https://lichess.org/'
            )

            board = current_game.board()
            move_counter = 0
            prev_move = None
            for move in current_game.mainline_moves():
                if output_data.newest_hit_exists():
                    output_data.print_and_write_data(specs)
                    output_data.clear_newest_hit()

                if specs.type_of_position() == "underpromotion":
                    if prev_move is not None:
                        board.push(prev_move)
                    prev_move = move # Note - prev_move is a misnomer for the rest of this loop iteration now.
                else:
                    board.push(move)
                move_counter += 1
                if move_counter < specs.move_to_begin_at() * 2:
                    continue
                board_str_rep = board.fen() + "\n" + str(board) + "\nfrom:\n" + current_game_as_str

                if specs.type_of_position() == "endgame":
                    num_pieces_in_current_fen = num_pieces_in_fen(board.fen())
                    if (num_pieces_desired_endgame is not None and
                        num_pieces_in_current_fen < num_pieces_desired_endgame):
                        break  # Too few pieces to ever reach the desired endgame now.
                    if (    (num_pieces_desired_endgame is None or
                            num_pieces_in_current_fen == num_pieces_desired_endgame)
                        and does_position_satisfy_specs(stockfish, board.fen(), endgame_specs)):
                        output_data.add_newest_hit(board_str_rep)
                        break  # On to the next game

                elif specs.type_of_position() == "top moves":
                    if does_position_satisfy_bounds(stockfish, board.fen(), bounds):
                        output_data.add_newest_hit(board_str_rep + "\nTop moves:\n" +
                                                   ', '.join(str(d) for d in stockfish.get_top_moves(2)))

                elif specs.type_of_position() == "skip move":
                    if (does_position_satisfy_bounds(stockfish, board.fen(), bounds[0:2]) and
                        stockfish.is_fen_valid(switch_whose_turn(board.fen())) and
                        does_position_satisfy_bounds(stockfish, switch_whose_turn(board.fen()),
                                                    bounds[2:4])):
                        output_data.add_newest_hit(board_str_rep)

                elif specs.type_of_position() == "underpromotion":
                    underpromotion_move = is_underpromotion_best(stockfish, board.fen())
                    if underpromotion_move:
                        assert isinstance(underpromotion_move, str)
                        output_data.add_newest_hit(board_str_rep, underpromotion_move != move.uci(), True)

                # End of for loop for iterating over the moves of the current game

        if output_data.newest_hit_exists() or output_data.num_games() % specs.default_output_interval() == 0:
            output_data.print_and_write_data(specs)
    # End of the while loop for iterating over all the games.
    pgn.close()
    if temp_pgn_file is not None:
        os.remove(temp_pgn_file)

if __name__ == "__main__":
    main()
