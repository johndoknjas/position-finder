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


def main():
    output_filename = str(time.time()) + ".txt"
    type_of_position = input(
        "Enter 'endgame' or 'top moves' for the type of position to find: "
    )
    if type_of_position not in ["endgame", "top moves"]:
        raise ValueError("Did not enter a valid type of position to look for.")
    game_to_start_search_at = input(
        "To start the search in the DB after a certain game, enter the last name of White, then the last name of Black. To not do this, just press enter: "
    )
    if game_to_start_search_at == "":
        game_to_start_search_at = None
    name_of_player_as_white_in_first_game = None if game_to_start_search_at is None else game_to_start_search_at.split()[0]
    name_of_player_as_black_in_first_game = None if game_to_start_search_at is None else game_to_start_search_at.split()[1]
    database_name = input("Enter the name of the pgn database you are using: ")
    num_pieces = int(input("How many pieces in this endgame: "))
    endgame_specs = get_endgame_specs_from_user()  # list of 17 strings.
    # Index 0 is for pieces that have to exist, but can be placed anywhere.
    # Indices 1-8 for rows 1-8.
    # Indices 9-16 for columns a-h.
    # Each string will store all the piece(s) and pawn(s) the user wants
    # in that particular row/column. E.g.: "PKp" means to have a white pawn,
    # white king, and black pawn in the column/row that string represents.
    stockfish = Stockfish(path="stockfish")
    pgn = open(database_name, "r", errors="replace")
    num_games_parsed = 0
    hit_counter = 0
    output_string = (
        ""
    )  # Will store the games which feature the desired type of endgame.
    reached_first_game_for_search_in_DB = (game_to_start_search_at == None)
    while True:
        if not reached_first_game_for_search_in_DB:
            headers = chess.pgn.read_headers(pgn)
            if (name_of_player_as_white_in_first_game in headers.get("White", "?") and
                name_of_player_as_black_in_first_game in headers.get("Black", "?")):
                reached_first_game_for_search_in_DB = True
            continue
        current_game = chess.pgn.read_game(pgn)
        if current_game is not None:
            board = current_game.board()
        move_counter = 0
        for move in current_game.mainline_moves():
            board.push(move)
            move_counter += 1
            if move_counter < 40:
                continue
            elif num_pieces_in_fen(board.fen()) < num_pieces:
                break  # Too few pieces to ever reach the desired endgame now.
            elif num_pieces_in_fen(board.fen()) == num_pieces:
                # Right number of pieces, so now check if there's a match.
                stockfish.set_fen_position(board.fen())
                position_works = True
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
                        position_works = False
                        break
                if position_works:
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
        num_games_parsed += 1
        if num_games_parsed % 50 == 0:
            print("current output string:\n" + output_string)
            print("Games parsed: " + str(num_games_parsed))
            print("Hit_counter = " + str(hit_counter))
            f = open(output_filename, "w")
            f.write(output_string)
            f.close()


if __name__ == "__main__":
    main()
