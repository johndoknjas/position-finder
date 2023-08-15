import chess.pgn
from stockfish import Stockfish
import time
from typing import *

piece_chars = ["P", "p", "N", "n", "B", "b", "R", "r", "Q", "q", "K", "k"]

def all_legal_pieces(str_of_pieces):
    global piece_chars
    for c in str_of_pieces:
        if c not in piece_chars:
            return False
    return True

def get_endgame_specs_from_user():
    endgame_specs = []
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
                "Enter what you want in column " + chr(ord("a") + (i - 9)) + ": "
            )
        if not all_legal_pieces(pieces):
            raise RuntimeError("Illegal chars entered for pieces")
        endgame_specs.append(pieces)
    return endgame_specs

def num_pieces_in_fen(fen):
    counter = 0
    global piece_chars
    for c in fen:
        if c in piece_chars:
            counter += 1
        elif c == " ":
            break
    return counter

def are_pieces_in_board(stockfish: Stockfish, pieces, file=None, row=None, all=True):
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
    initial_col_iterator = 1 if not file else (1 + ord(file) - ord("a"))
    end_col_iterator = 9 if not file else initial_col_iterator + 1

    for piece in pieces:
        found_piece = False

        for row in range(initial_row_iterator, end_row_iterator):
            for col in range(initial_col_iterator, end_col_iterator):
                square = chr(ord("a") + col - 1) + str(row)
                try:
                    if stockfish.get_what_is_on_square(square) is not None:
                        if stockfish.get_what_is_on_square(square).value == piece:
                            found_piece = True
                            break
                except:
                    print("PROBLEM: " + square)
                    print("File: " + file)
            if found_piece:
                break

        if all and not found_piece:
            return False
        if not all and found_piece:
            return True
    return all

def does_position_satisfy_specs(stockfish, fen, position_specs):
    # position_specs must be a list of 17 strings.
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
            file = chr(ord("a") + (i - 9))
            row = None

        if i == 17 and are_pieces_in_board(stockfish, position_specs[i], file, row, all=False):
            return False
        if i != 17 and not are_pieces_in_board(stockfish, position_specs[i], file, row):
            return False

    return True

def satisfies_bound(move_dict, bound, is_lower_bound):
    # bound is in centipawn evaluation, as a decimal (e.g., 2.17). Or None.
    # For move_dict, if the "Centipawn" key has a value, it will already have been
    # converted to decimal form (so nothing like 37 for a 0.37 evaluation).
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

def does_position_satisfy_bounds(stockfish, fen, bounds):
    # bounds is a list, where the 0th element is the lower bound for the first move,
    # the 1st element is the upper bound for the first move, etc (for however many
    # top moves). It may just be the one top move, or it could be 1 more, 2 more, etc.
    # len(bounds) will be even.
    
    # Also allow for if it's Black to move (so if the evals are negative, in Black's favour).
    stockfish.set_fen_position(fen, send_ucinewgame_token = False)
    depth_increments = [8, 12, 15]
    eval_multiplier = 1 if "w" in fen else -1
    # In order to work with evaluations that are relative to the player whose turn it is,
    # rather than positive being white and negative being black.
    for depth in depth_increments:
        stockfish.set_depth(depth)
        top_moves = stockfish.get_top_moves(len(bounds) / 2)
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

def is_underpromotion_best(stockfish, fen) -> Union[bool, str]:
    # Returns False if so. Otherwise, returns the underpromotion move (e.g., e7e8r).

    stockfish.set_fen_position(fen, send_ucinewgame_token = False)
    depth_increments = [12, 15, 25]
    eval_multiplier = 1 if "w" in fen else -1
    # In order to work with evaluations that are relative to the player whose turn it is,
    # rather than positive being white and negative being black.

    if ("w" in fen and not are_pieces_in_board(stockfish, ["P"], row=7) or
        "w" not in fen and not are_pieces_in_board(stockfish, ["p"], row=2)):
        return False # Since a promotion is not even possible.

    for depth in depth_increments:
        stockfish.set_depth(depth)
        top_moves = stockfish.get_top_moves(2)
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

def get_bounds_from_user(input_messages):
    bounds_as_strings = []
    print("For each of the following, type 'None' or just press enter if you don't want a bound.")
    for message in input_messages:
        bounds_as_strings.append(input(message))
    bounds = []
    for current_bound_as_string in bounds_as_strings:
        if current_bound_as_string in ["", "None"]:
            bounds.append(None)
        else:
            bounds.append(float(current_bound_as_string))
    return bounds

def switch_whose_turn(fen):
    if "w" in fen:
        return fen.replace("w", "b")
    else:
        return fen.replace(" b ", " w ")
    
def print_output_data(type_of_position, output_string, secondary_output_string, hit_counter,
                      secondary_hit_counter, num_games_parsed, output_filename):
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

def main():
    output_filename = str(int(time.time()))
    
    type_of_position = input("""Enter 'endgame', 'top moves', 'skip move', or 'underpromotion' for the type of position to find: """)
    
    database_name = input("Enter the name of the pgn database you are using: ")
    if not database_name.endswith('.pgn'):
        database_name += '.pgn'

    game_to_start_search_after: Union[int,str] = input("""To start the search in the DB after a certain game, enter 
the last name of White, then a space, then the last name of Black, then a space, then the year. 
To not do this, just press enter: """)
    
    if game_to_start_search_after != "":
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
        endgame_specs = get_endgame_specs_from_user()
        # list of 17 strings.
        # Index 0 is for pieces that have to exist, but can be placed anywhere.
        # Indices 1-8 for rows 1-8.
        # Indices 9-16 for columns a-h.
        # Index 17 is for pieces that mustn't exist in the position.
        # Each string will store all the piece(s) and pawn(s) the user wants
        # in that particular row/column. E.g.: "PKp" means to have a white pawn,
        # white king, and black pawn in the column/row that string represents.
        
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
            reached_first_game_for_search_in_DB = (
                (   
                    name_of_player_as_white_in_first_game in headers.get("White", "?") and 
                    name_of_player_as_black_in_first_game in headers.get("Black", "?") and
                    date_of_first_game in headers.get("Date")
                ) 
                if type(game_to_start_search_after) is str
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
