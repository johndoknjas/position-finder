import chess.pgn
from models import Stockfish
import time
from typing import Tuple, Optional, Union, List

PIECE_CHARS: List[str] = ["P", "p", "N", "n", "B", "b", "R", "r", "Q", "q", "K", "k"]
FILE_CHARS: List[str] = ['a', 'b', 'c', 'd', 'e', 'f', 'g', 'h', 'A', 'B', 'C', 'D', 'E', 'F', 'G', 'H']

def file_char_to_int(file_char: str) -> int:
    assert file_char in FILE_CHARS
    return 1 + ord(file_char.lower()) - ord('a')

def file_int_to_char(file_int: int) -> str:
    assert 1 <= file_int <= 8
    return chr(ord('a') + file_int - 1)

# continue here - to now use this class, you can (optionally) send requirements strings that are prepended with:
    # "row [1-8]:"
    # "file ['a'-'h']:"    either case fine
    # "['a'-'h'][1-8]:"    for a single square        either case fine
# To signify requirements that should be excluded, make the first char of the requirements string be either
# ~ or !.

# Note that for some other code in this file, you currently treat an end row/col by exclusion, not inclusion.
# This class treats with inclusion.
class Piece_Quantities:
    """Stores data representing piece chars that must be present, and (optionally) in exactly
       what quantities."""

    def __init__(self, requirements_string: str) -> None:
        self._requirements_string = ''.join(requirements_string.split())
        self._curr_index = 0
        self._start_row, self._start_file = 1, 1
        self._end_row, self._end_file = 8, 8
        self._should_exclude = self._requirements_string.startswith(('~', '!'))
        self._requirements_string = self._requirements_string.lstrip('~!')
        if len(substrings := self._requirements_string.split(':')) == 2:
            board_area = substrings[0].lower()
            self._requirements_string = substrings[1]
            if board_area.startswith('row'):
                self._start_row = self._end_row = int(board_area[-1])
            elif board_area.startswith('file'):
                self._start_file = self._end_file = file_char_to_int(board_area[-1])
            else:
                assert len(board_area) == 2
                self._start_file = self._end_file = file_char_to_int(board_area[0])
                self._start_row = self._end_row = int(board_area[1])

    def get_requirements(self) -> List[Tuple[str, Optional[int]]]:
        requirements: List[Tuple[str, Optional[int]]] = []
        while not self._are_all_read():
            requirements.append(self._consume_current_requirement())
        self._rollback_parsing()
        return requirements
    
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

    def _rollback_parsing(self) -> None:
        """Next requirement read after this will be the first one."""
        self._curr_index = 0

    def _are_all_read(self) -> bool:
        return self._curr_index >= len(self._requirements_string)
    
    def _consume_current_requirement(self) -> Tuple[str, Optional[int]]:
        """On each call, this function will increment self._curr_index."""
        assert not self._peek_curr_char().isdigit()
        piece_char = self._consume_curr_char()
        quantity: Optional[int] = None
        if not self._are_all_read() and self._peek_curr_char().isdigit():
            quantity = int(self._consume_curr_char())
        return (piece_char, quantity)
    
    def _peek_curr_char(self) -> str:
        assert not self._are_all_read()
        return self._requirements_string[self._curr_index]
    
    def _consume_curr_char(self) -> str:
        """On each call, this function will increment self._curr_index."""
        c = self._peek_curr_char()
        self._curr_index += 1
        return c

def get_endgame_specs_from_user() -> List[Piece_Quantities]:
    endgame_specs: List[Piece_Quantities] = []
    for i in range(18):
        pieces = ""
        if i == 0:
            pieces = input("Enter pieces which must exist, but can be anywhere: ")
        elif i <= 8:
            pieces = input("Enter what you want in row " + str(i) + ": ")
        elif i == 17:
            pieces = input("Enter pieces which mustn't exist in the position: ")
        else:
            pieces = input(
                "Enter what you want in column " + file_int_to_char(i - 8) + ": "
            )
        if not all(c in PIECE_CHARS or c.isdigit() for c in pieces):
            raise RuntimeError("Illegal chars entered for pieces")
        endgame_specs.append(Piece_Quantities(pieces))
    return endgame_specs

def num_pieces_in_fen(fen: str) -> int:
    counter = 0
    for c in fen:
        if c in PIECE_CHARS:
            counter += 1
        elif c == " ":
            break
    return counter

def is_piece_in_board(stockfish: Stockfish, piece_char: str, row_start: int, row_end_exclude: int, 
                      col_start: int, col_end_exclude: int, num_of_this_piece: Optional[int] = None) -> bool:
    """If the optional num_of_this_piece param is left as None, then the function returns true iff
       at least one of the specified piece char is in the board.
       Otherwise, exactly the specified number of the piece must be present."""
    
    hit_counter = 0
    for row in range(row_start, row_end_exclude):
        for col in range(col_start, col_end_exclude):
            square = file_int_to_char(col) + str(row)
            if ((square_contents := stockfish.get_what_is_on_square(square)) is not None and
                square_contents.value == piece_char):
                if num_of_this_piece is None:
                    return True
                hit_counter += 1
    return num_of_this_piece is not None and hit_counter == num_of_this_piece

def are_pieces_in_board(stockfish: Stockfish, pieces: Piece_Quantities, 
                        file: Optional[str] = None, row: Optional[int] = None, all: bool = True) -> bool:
    """
        - Pre-condition: the stockfish object must be set to the position in question.
        - `all` = True means the function returns true iff all pieces specified are present.
          If 'all' = False, the function returns true iff at least one of the specified pieces is present.
    """

    # If values aren't sent in for file or row, just check if each piece exists
    # anywhere on stockfish's current board.
    # Otherwise, check if the pieces exist in the specified file/row.

    initial_row_iterator = 1 if not row else row
    end_row_iterator = 9 if not row else initial_row_iterator + 1
    initial_col_iterator = 1 if not file else file_char_to_int(file)
    end_col_iterator = 9 if not file else initial_col_iterator + 1
    for requirement in pieces.get_requirements():
        piece_in_board = is_piece_in_board(stockfish, requirement[0], 
                                           initial_row_iterator, end_row_iterator, 
                                           initial_col_iterator, end_col_iterator,
                                           num_of_this_piece=requirement[1])
        if all and not piece_in_board:
            return False
        if not all and piece_in_board:
            return True
    return all

def does_position_satisfy_specs(stockfish: Stockfish, fen: str, position_specs: List[Piece_Quantities]) -> bool:
    # position_specs must be a list of 17 `Piece_Quantities` objects.
        # Index 0 is for pieces that have to exist, but can be placed anywhere.
        # Indices 1-8 for rows 1-8.
        # Indices 9-16 for columns a-h.
        # Index 17 is for pieces which mustn't exist in the position.
        # Each string will store all the piece(s) and pawn(s) the user wants in that particular row/column. 
        # E.g.: "PKp" means to have a white pawn, king, and black pawn in the column/row that the string represents.
    stockfish.set_fen_position(fen, send_ucinewgame_token = False)
    for i in range(18):
        if i == 0 or i == 17:
            file, row = None, None
        elif i <= 8:
            file = None
            row = i
        else:
            file = file_int_to_char(i - 8)
            row = None

        if i == 17 and are_pieces_in_board(stockfish, position_specs[i], file, row, all=False):
            return False
        if i != 17 and not are_pieces_in_board(stockfish, position_specs[i], file, row):
            return False

    return True

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
    # Returns False if so. Otherwise, returns the underpromotion move (e.g., e7e8r).

    stockfish.set_fen_position(fen, send_ucinewgame_token = False)
    depth_increments = [12, 15, 25]
    eval_multiplier = 1 if "w" in fen else -1
    # In order to work with evaluations that are relative to the player whose turn it is,
    # rather than positive being white and negative being black.

    if (("w" in fen and not are_pieces_in_board(stockfish, Piece_Quantities("P"), row=7)) or
        ("w" not in fen and not are_pieces_in_board(stockfish, Piece_Quantities("p"), row=2))):
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
    if "w" in fen:
        return fen.replace("w", "b")
    else:
        return fen.replace(" b ", " w ")
    
def print_output_data(type_of_position: str, output_string: str, secondary_output_string: str, 
                      hit_counter: int, secondary_hit_counter: int, num_games_parsed: int, 
                      output_filename: str):
    if type_of_position == "underpromotion":
        print("Games found where underpromotion best:\n" + secondary_output_string + "\n")
        print("Games found where underpromotion best and player missed it:\n" 
                + output_string)
        print("#Games where underpromotion is best move: " + str(secondary_hit_counter))
        print("#Games where underpromotion is best move and player missed it: " + str(hit_counter))
        print("#Games parsed: " + str(num_games_parsed))

        f = open(output_filename + "-games where underpromotion is best move.txt", "w")
        f.write(secondary_output_string + "#Games parsed: " + str(num_games_parsed) + 
                "\nHit counter: " + str(secondary_hit_counter) + "\n\n")
        f.close()

        f = open(output_filename + "-games where underpromotion is best and player missed it.txt", "w")
        f.write(output_string + "#Games parsed: " + str(num_games_parsed) + 
                "\nHit counter: " + str(hit_counter) + "\n\n")
        f.close()
    else:
        print("Games found matching requirements:\n" + output_string)
        print("#Games parsed: " + str(num_games_parsed))
        print("Hit_counter = " + str(hit_counter))
        f = open(output_filename + ".txt", "w")
        f.write(output_string + "#Games parsed: " + str(num_games_parsed) + 
                "\nHit counter: " + str(hit_counter) + "\n\n")
        f.close()

def main() -> None:
    output_filename = str(int(time.time()))
    
    type_of_position = input("""Enter 'endgame', 'top moves', 'skip move', or 'underpromotion' for the type of position to find: """)
    
    database_name = input("Enter the name of the pgn database you are using: ")
    if not database_name.endswith('.pgn'):
        database_name += '.pgn'

    game_to_start_search_after: Union[int,str] = input("""To start the search in the DB after a certain game, enter 
the last name of White, then a space, then the last name of Black, then a space, then the year. 
To not do this, just press enter: """)
    
    if game_to_start_search_after != "":
        assert type(game_to_start_search_after) is str
        name_of_player_as_white_in_first_game = game_to_start_search_after.split()[0]
        name_of_player_as_black_in_first_game = game_to_start_search_after.split()[1]
        date_of_first_game = game_to_start_search_after.split()[2]
    else:
        print()
        game_to_start_search_after = int(input("""To start the search after a particular game number in the database,
enter it here. Otherwise, just press enter: """) or "0")

    move_to_start_in_each_game = int(
        input("Enter the move to start searching for matching positions in each game: ")
        or "0"
    )
    
    if type_of_position == "endgame":
        num_pieces_desired_endgame = int(user_input) if (user_input := 
                                                         input("Exactly how many pieces in this endgame: ")
                                                        ) else None
        endgame_specs: List[Piece_Quantities] = get_endgame_specs_from_user()
        # list of 17 requirements for pieces present.
        # Index 0 is for pieces that have to exist, but can be placed anywhere.
        # Indices 1-8 for rows 1-8.
        # Indices 9-16 for columns a-h.
        # Index 17 is for pieces that mustn't exist in the position.
        # Each element will store all the piece(s) and pawn(s) the user wants
        # in that particular row/column, and in potentially what exact quantities. 
        # E.g.: "PK2p" (for the requirements) means to have a white pawn, white king, and 2 black pawns in the 
        # column/row that string represents.
        
    elif type_of_position == "top moves":
        bounds = get_bounds_from_user(["Enter the lower bound the top move's eval: ",
                                       "Upper bound for top move's eval: ",
                                       "Lower bound for the second top move's eval: ",
                                       "Upper bound for the second top move's eval: "])
        # bounds will be used later in the main while loop. This list will store 4 floats,
        # representing the info above (in that order). So, lower bound for the top move in the
        # first spot in the list, etc.
    
    elif type_of_position == "skip move":
        bounds = get_bounds_from_user(["Enter the lower bound eval for a position: ",
                                       "Upper bound for a position: ",
                                       "Lower bound eval (relative to opponent this time) for the position with move skipped : ",
                                       "Upper bound for the position with move skipped : "])
        # Again, like in the elif above, here bounds will be used later in the main loop.

    stockfish = Stockfish(path="stockfish")
    pgn = open(database_name, "r", errors="replace")
    num_games_parsed = 0
    hit_counter = 0
    output_string = ""
    # Will store the games which feature the desired type of endgame.
    secondary_hit_counter = 0 # used for underpromotion feature
    secondary_output_string = "" # used for underpromotion feature
    reached_first_game_for_search_in_DB = not game_to_start_search_after
    while True:
        if not reached_first_game_for_search_in_DB:
            headers = chess.pgn.read_headers(pgn)
            assert headers is not None
            game_date = headers.get("Date")
            assert type(game_date) is str
            reached_first_game_for_search_in_DB = (
                (   
                    name_of_player_as_white_in_first_game in headers.get("White", "?") and 
                    name_of_player_as_black_in_first_game in headers.get("Black", "?") and
                    date_of_first_game in game_date
                ) 
                if isinstance(game_to_start_search_after, str)
                else 
                (
                    num_games_parsed >= game_to_start_search_after
                )
            )
            if reached_first_game_for_search_in_DB:
                print("Done skipping games")
            if num_games_parsed % 20000 == 0:
                print("Skipped " + str(num_games_parsed))
            continue
        current_game = chess.pgn.read_game(pgn)
        if current_game is None:
            break
        current_game_as_str = str(current_game)
        num_games_parsed += 1

        board = current_game.board()
        move_counter = 0
        prev_move = None
        for move in current_game.mainline_moves():
            if type_of_position == "underpromotion":
                if prev_move is not None:
                    board.push(prev_move)
                prev_move = move # Note - prev_move is a misnomer for the rest of this loop iteration now.
            else:
                board.push(move)
            move_counter += 1
            if move_counter < move_to_start_in_each_game * 2:
                continue
            board_str_rep = (
                board.fen()
                + "\n"
                + str(board)
                + "\nfrom:\n"
                + current_game_as_str
            )

            if type_of_position == "endgame":
                num_pieces_in_current_fen = num_pieces_in_fen(board.fen())
                if (num_pieces_desired_endgame is not None and
                    num_pieces_in_current_fen < num_pieces_desired_endgame):
                    break  # Too few pieces to ever reach the desired endgame now.
                if (    (num_pieces_desired_endgame is None or
                         num_pieces_in_current_fen == num_pieces_desired_endgame)
                    and does_position_satisfy_specs(stockfish, board.fen(), endgame_specs)):
                    output_string += (board_str_rep + "\n\n----------\n\n")
                    hit_counter += 1
                    break  # On to the next game

            elif type_of_position == "top moves":
                if does_position_satisfy_bounds(stockfish, board.fen(), bounds):
                    output_string += (
                        board_str_rep
                        + "\nTop moves:\n"
                        + ', '.join(str(d) for d in stockfish.get_top_moves(2))
                        + "\n\n----------\n\n"
                    )
                    hit_counter += 1
            
            elif type_of_position == "skip move":
                if (does_position_satisfy_bounds(stockfish, board.fen(), bounds[0:2]) and
                    stockfish.is_fen_valid(switch_whose_turn(board.fen())) and
                    does_position_satisfy_bounds(stockfish, switch_whose_turn(board.fen()), 
                                                 bounds[2:4])):
                    output_string += (board_str_rep + "\n\n----------\n\n")
                    hit_counter += 1
            
            elif type_of_position == "underpromotion":
                underpromotion_move = is_underpromotion_best(stockfish, board.fen()) # returns False or str
                if underpromotion_move: # must be a move string
                    secondary_output_string += (board_str_rep + "\n\n----------\n\n")
                    secondary_hit_counter += 1
                    if underpromotion_move != move.uci():
                        output_string += (board_str_rep + "\n\n----------\n\n")
                        hit_counter += 1
        # End of for loop
        
        if num_games_parsed % 40 == 0:
            print_output_data(type_of_position, output_string, secondary_output_string,
                              hit_counter, secondary_hit_counter, num_games_parsed, output_filename)
    print_output_data(type_of_position, output_string, secondary_output_string,
                      hit_counter, secondary_hit_counter, num_games_parsed, output_filename)


if __name__ == "__main__":
    main()
