import chess.pgn
from stockfish import Stockfish
import time

piece_chars = ["P", "p", "N", "n", "B", "b", "R", "r", "Q", "q", "K", "k"]


def all_legal_pieces(str_of_pieces):
    global piece_chars
    for c in str_of_pieces:
        if c not in piece_chars:
            return False
    return True


def get_endgame_specs_from_user():
    endgame_specs = []
    for i in range(17):
        pieces = ""
        if i == 0:
            pieces = input("Enter pieces which must exist, but can be anywhere: ")
        elif i <= 8:
            pieces = input("Enter what you want in row " + str(i) + ": ")
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


def are_pieces_in_board(stockfish, pieces, file=None, row=None):
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
        if not found_piece:
            return False
    return True


def does_endgame_satisfy_specs(stockfish, fen, endgame_specs):
    stockfish.set_fen_position(fen)
    for i in range(17):
        if i == 0:
            file = None
            row = None
        elif i <= 8:
            file = None
            row = i
        else:
            file = chr(ord("a") + (i - 9))
            row = None
        if not are_pieces_in_board(stockfish, endgame_specs[i], file, row):
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

def does_position_satisfy_top_moves_specs(stockfish, fen, bounds):
    # Also allow for if it's Black to move (so if the evals are negative, in Black's favour).
    stockfish.set_fen_position(fen)
    depth_increments = [8, 13, 16]
    eval_multiplier = 1 if "w" in fen else -1
    # In order to work with evaluations that are relative to the player whose turn it is,
    # rather than positive being white and negative being black.
    for depth in depth_increments:
        stockfish.set_depth(depth)
        top_moves = stockfish.get_top_moves(2)
        if len(top_moves) != 2:
            return False     
        for i in range(len(top_moves)):
            if top_moves[i]["Centipawn"] is not None:
                top_moves[i]["Centipawn"] *= (eval_multiplier * 0.01)
            if top_moves[i]["Mate"] is not None:
                top_moves[i]["Mate"] *= eval_multiplier

        # Now see if each of the bounds is satisfied:
        if (not satisfies_bound(top_moves[0], bounds[0], True) or
            not satisfies_bound(top_moves[0], bounds[1], False) or
            not satisfies_bound(top_moves[1], bounds[2], True) or
            not satisfies_bound(top_moves[1], bounds[3], False)):
            return False
    return True

def main():
    output_filename = str(time.time()) + ".txt"
    
    type_of_position = input("Enter 'endgame' or 'top moves' for the type of position to find: ")
    
    database_name = input("Enter the name of the pgn database you are using: ")

    game_to_start_search_at = input("""To start the search in the DB after a certain game, enter 
the last name of White, then the last name of Black. To not do this, just press enter: """)
    
    if game_to_start_search_at != "":
        name_of_player_as_white_in_first_game = game_to_start_search_at.split()[0]
        name_of_player_as_black_in_first_game = game_to_start_search_at.split()[1]

    move_to_start_in_each_game = int(
        input("Enter the move to start searching for matching positions in each game: ")
        or "0"
    )
    
    if type_of_position == "endgame":
        num_pieces_desired_endgame = int(input("How many pieces in this endgame: "))
        endgame_specs = get_endgame_specs_from_user()
        # list of 17 strings.
        # Index 0 is for pieces that have to exist, but can be placed anywhere.
        # Indices 1-8 for rows 1-8.
        # Indices 9-16 for columns a-h.
        # Each string will store all the piece(s) and pawn(s) the user wants
        # in that particular row/column. E.g.: "PKp" means to have a white pawn,
        # white king, and black pawn in the column/row that string represents.
    elif type_of_position == "top moves":
        print("For each of the following, just press enter if you don't want a bound.")
        bounds_as_strings = []
        bounds_as_strings.append(input("Enter the lower bound the top move's eval: "))
        bounds_as_strings.append(input("Upper bound for top move's eval: "))
        bounds_as_strings.append(input("Lower bound for the second top move's eval: "))
        bounds_as_strings.append(input("Upper bound for the second top move's eval: "))
        
        bounds = [] 
        # Will be used later in the main while loop. This list will store 4 floats,
        # representing the info above (in that order). So, lower bound for the top move in the
        # first spot in the list, etc.
        
        for current_bound_as_string in bounds_as_strings:
            if current_bound_as_string == "":
                bounds.append(None)
            else:
                bounds.append(float(current_bound_as_string))

    stockfish = Stockfish(path="stockfish")
    pgn = open(database_name, "r", errors="replace")
    num_games_parsed = 0
    hit_counter = 0
    output_string = ""
    # Will store the games which feature the desired type of endgame.
    
    reached_first_game_for_search_in_DB = game_to_start_search_at == ""
    while True:
        if not reached_first_game_for_search_in_DB:
            headers = chess.pgn.read_headers(pgn)
            if name_of_player_as_white_in_first_game in headers.get(
                "White", "?"
            ) and name_of_player_as_black_in_first_game in headers.get("Black", "?"):
                reached_first_game_for_search_in_DB = True
            continue
        current_game = chess.pgn.read_game(pgn)
        if current_game is None:
            break

        board = current_game.board()
        move_counter = 0
        for move in current_game.mainline_moves():
            board.push(move)
            move_counter += 1
            if move_counter < move_to_start_in_each_game * 2:
                continue
            if type_of_position == "endgame":
                num_pieces_in_current_fen = num_pieces_in_fen(board.fen())
                if num_pieces_in_current_fen < num_pieces_desired_endgame:
                    break  # Too few pieces to ever reach the desired endgame now.
                if (num_pieces_in_current_fen == num_pieces_desired_endgame and 
                    does_endgame_satisfy_specs(stockfish, board.fen(), endgame_specs)
                ):
                    output_string += (
                        board.fen()
                        + "\n"
                        + str(board)
                        + "\nfrom:\n"
                        + str(current_game)
                        + "\n\n----------\n\n"
                    )
                    hit_counter += 1
                    break  # On to the next game

            elif type_of_position == "top moves":
                if does_position_satisfy_top_moves_specs(stockfish, board.fen(), bounds):
                    output_string += (
                        board.fen()
                        + "\n"
                        + str(board)
                        + "\nfrom:\n"
                        + str(current_game)
                        + "\nTop moves:\n"
                        + stockfish.get_top_moves(2)
                        + "\n\n----------\n\n"
                    )
                    hit_counter += 1
                    break  # On to the next game
        # End of for loop
        
        num_games_parsed += 1
        if num_games_parsed % 20 == 0:
            print("current output string:\n" + output_string)
            print("Games parsed: " + str(num_games_parsed))
            print("Hit_counter = " + str(hit_counter))
            f = open(output_filename, "w")
            f.write(output_string)
            f.close()


if __name__ == "__main__":
    main()
