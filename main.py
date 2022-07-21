import chess.pgn
from stockfish import Stockfish

def all_legal_pieces(str_of_pieces):
    valid_chars = ['P', 'p', 'N', 'n', 'B', 'b', 'R', 'r', 'Q', 'q', 'K', 'k']
    for c in str_of_pieces:
        if c not in valid_chars:
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
                pieces = input("Enter what you want in column " + chr(ord('a') + (i-9)))
        except SyntaxError:
            pieces = ""
        if not all_legal_pieces(pieces):
            raise RuntimeError("Illegal chars entered for pieces")
        endgame_specs.append(pieces)
    return endgame_specs

def main():
    endgame_specs = get_specs_from_user # list of 17 strings.
        # Index 0 is for pieces that have to exist, but can be placed anywhere.
        # Indices 1-8 for rows 1-8.
        # Indices 9-16 for columns a-h.
        # Each string will store all the piece(s) and pawn(s) the user wants
        # in that particular row/column. E.g.: "PKp" means to have a white pawn,
        # white king, and black pawn in the column/row that string represents.
    stockfish = Stockfish(path="stockfish")
    pgn = open("big database over 2200.pgn")
    current_game = chess.pgn.read_game(pgn)
    while current_game is not None:
        board = current_game.board()
        for move in current_game.mainline_moves():
            board.push(move)
            # CONTINUE HERE - work with the board to check if it's reached the
            # desired type of endgame, using endgame_specs. Also can use the functions of
            # the stockfish instance, which has been initialized without issue.
        current_game = chess.pgn.read_game(pgn)


if __name__ == "__main__":
    main()
    
    
    
