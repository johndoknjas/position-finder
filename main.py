import chess.pgn
from stockfish import Stockfish

piece_chars = ['P', 'p', 'N', 'n', 'B', 'b', 'R', 'r', 'Q', 'q', 'K', 'k']

def all_legal_pieces(str_of_pieces):
    global piece_chars
    for c in str_of_pieces:
        if c not in piece_chars:
            return False
    return True

def get_specs_from_user():
    endgame_specs = []
    for i in range(17):
        pieces = ""
        try:
            if i == 0:
                pieces = input("Enter pieces which must exist, but can be anywhere: ")
            elif i <= 8:
                pieces = input("Enter what you want in row " + str(i) + ": ")
            else:
                pieces = input("Enter what you want in column " + chr(ord('a') + (i-9)) + ": ")
        except SyntaxError:
            pieces = ""
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
        elif c == 'w' or c == 'b':
            break
    return counter

def are_pieces_in_board(stockfish, pieces, file=None, row=None):
    # If values aren't sent in for file or row, just check if each piece exists
    # anywhere on stockfish's current board.
    # Otherwise, check if the pieces exist in the specified file/row.
    
    initial_row_iterator = 1 if not row else row
    end_row_iterator = 9 if not row else initial_row_iterator + 1
    initial_col_iterator = 1 if not file else (ord(file) - ord('a'))
    end_col_iterator = 9 if not file else initial_col_iterator + 1
    
    for piece in pieces:
        found_piece = False
        for row in range(initial_row_iterator, end_row_iterator):
            for col in range(initial_col_iterator, end_col_iterator):
                square = chr(ord('a') + col - 1) + str(row)
                try: # TEST
                    if stockfish.get_what_is_on_square(square) is not None:
                        if stockfish.get_what_is_on_square(square).value == piece:
                            found_piece = True
                            break
                except:
                    print("PROBLEM: " + square)
            if found_piece:
                break
        if not found_piece:
            return False
    return True

def main():
    num_pieces = int(input("How many pieces in this endgame: "))
    endgame_specs = get_specs_from_user() # list of 17 strings.
        # Index 0 is for pieces that have to exist, but can be placed anywhere.
        # Indices 1-8 for rows 1-8.
        # Indices 9-16 for columns a-h.
        # Each string will store all the piece(s) and pawn(s) the user wants
        # in that particular row/column. E.g.: "PKp" means to have a white pawn,
        # white king, and black pawn in the column/row that string represents.
    stockfish = Stockfish(path="stockfish")
    pgn = open("big database over 2200.pgn")
    num_games_parsed = 0
    current_game = chess.pgn.read_game(pgn)
    while current_game is not None:
        game_works = True
        board = current_game.board()
        for move in current_game.mainline_moves():
            if num_pieces_in_fen(board.fen()) < num_pieces:
                break # Too few pieces to ever reach the desired endgame now.
            elif num_pieces_in_fen(board.fen()) == num_pieces:
                # Right number of pieces, so now check if there's a match.
                stockfish.set_fen_position(board.fen())
                for i in range(17):
                    if i == 0:
                        file = None
                        row = None
                    elif i <= 8:
                        file = None
                        row = i
                    else:
                        file = chr(ord('a') + (i - 9))
                        row = None
                    if not are_pieces_in_board(stockfish, endgame_specs[i], file, row):
                        game_works = False
                        break
                if game_works:
                    print(board.fen()) # TEST
                    # CONTINUE HERE - Was testing by running the program, 32 pieces,
                    # only requirement being a N on row 3, but no fens get printed out.
                    # Solve this bug, then if there are no other bugs, may be all good
                    # to go after that.
                    break # On to the next game
            board.push(move)
        current_game = chess.pgn.read_game(pgn)
        num_games_parsed += 1
        print("Games parsed: " + str(num_games_parsed))


if __name__ == "__main__":
    main()
    
    
    
