from __future__ import annotations

import os
import tempfile

import chess

import exercises
import pgn_index

SAMPLE_PGN = '''[Event "Test event"]
[Site "Somewhere"]
[Date "1997.06.??"]
[White "Aaa, A"]
[Black "Bbb, B"]
[Result "1-0"]

1. e4 e5 2. Nf3 Nc6 3. Bb5 a6 1-0

[Event "Later event"]
[Site "Elsewhere"]
[Date "2001.11.30"]
[White "Ccc, C"]
[Black "Ddd, D"]
[Result "0-1"]

1. d4 d5 2. c4 e6 0-1

[Event "Undated event"]
[Site "?"]
[Date "????.??.??"]
[EventDate "1985.03.??"]
[White "Eee, E"]
[Black "Fff, F"]
[Result "1/2-1/2"]

1. c4 c5 1/2-1/2
'''

def test_date_parsing() -> None:
    assert pgn_index._parse_date(b'1997.06.??') == 19970600
    assert pgn_index._parse_date(b'2001.11.30') == 20011130
    assert pgn_index._parse_date(b'????.??.??') == 0

def test_index_orders_games_by_date() -> None:
    with tempfile.TemporaryDirectory() as folder:
        path = os.path.join(folder, 'sample.pgn')
        with open(path, 'w') as f:
            f.write(SAMPLE_PGN)
        index = pgn_index.build_index(path, verbose=False)
        assert index.num_games() == 3
        # The undated game falls back to its EventDate.
        assert [index.date_of(n) for n in range(3)] == [19970600, 20011130, 19850300]
        newest_first = index.game_nums_by_date()
        assert newest_first == [1, 0, 2]
        games = [game for _, game in index.read_games(newest_first)]
        assert [game.headers['White'] for game in games] == ['Ccc, C', 'Aaa, A', 'Eee, E']

def test_null_move_position() -> None:
    board = chess.Board()
    passed = exercises.null_move_position(board)
    assert passed is not None and passed.turn == chess.BLACK
    # Passing is not allowed when the student is in check, since handing the opponent the
    # move would let them capture the king.
    in_check = chess.Board("4k3/4R3/8/8/8/8/8/4K3 b - - 0 1")
    assert exercises.null_move_position(in_check) is None

def test_is_quiet() -> None:
    board = chess.Board("r1bqkbnr/pppp1ppp/2n5/4p3/2B1P3/5Q2/PPPP1PPP/RNB1K1NR w KQkq - 4 4")
    assert not exercises.is_quiet(board, board.parse_san("Qxf7#"))  # capture and check
    assert exercises.is_quiet(board, board.parse_san("d3"))
    promotion = chess.Board("8/4P3/8/8/8/5k2/8/4K3 w - - 0 1")
    assert not exercises.is_quiet(promotion, promotion.parse_san("e8=Q"))

def test_is_technical() -> None:
    cfg = exercises.Config()
    rook_endgame = chess.Board("8/5pk1/6p1/8/8/1R6/5PPP/6K1 w - - 0 40")
    assert exercises.is_technical(rook_endgame, cfg)
    middlegame = chess.Board("r1bq1rk1/pp2ppbp/2np1np1/8/2BNP3/2N1B3/PPP2PPP/R2Q1RK1 w - - 0 9")
    assert not exercises.is_technical(middlegame, cfg)
    # Too few pawns left for the win to be about technique.
    bare = chess.Board("8/8/8/4k3/8/8/5PK1/6R1 w - - 0 60")
    assert not exercises.is_technical(bare, cfg)

def test_worth_scanning_skips_openings_and_checks() -> None:
    cfg = exercises.Config()
    opening = chess.Board()
    assert not exercises.worth_scanning(opening, cfg)
    in_check = chess.Board("r1bqk2r/pppp1ppp/2n2n2/8/1b1PP3/8/PPP2PPP/RNBQK1NR w KQkq - 0 20")
    assert not exercises.worth_scanning(in_check, cfg)
    quiet = chess.Board("r1bq1rk1/pp2ppbp/2np1np1/8/2BNP3/2N1B3/PPP2PPP/R2Q1RK1 w - - 0 20")
    assert exercises.worth_scanning(quiet, cfg)

def test_exercise_to_pgn_has_a_setup_position_and_both_moves() -> None:
    exercise = exercises.Exercise(
        theme='prophylaxis',
        fen="1rb2r1k/pp2q1pp/5p2/P3p3/1nNp4/1Q1P2P1/1P2PPBP/RR4K1 w - - 2 21",
        best_san='Ra4', best_uci='a1a4', second_san='Nd2', best_cp=78, second_cp=-7,
        best_line='21. Ra4 Na6', second_line='21. Nd2 Bg4',
        opponent_idea_san='Bg4', opponent_idea_line='21... Bg4 22. Bf3', threat_cp=112,
        prevention_cp=449,
        game_info={'white': 'Hennigan, Michael', 'black': 'Bezold, Michael', 'date': '2001.03.18',
                   'event': 'BCF-chT', 'played_san': 'Ra4', 'player_found_it': True,
                   'move_number': 21, 'side_to_move': 'White'},
    )
    pgn = exercises.exercise_to_pgn(exercise)
    assert '[FEN "1rb2r1k/pp2q1pp/5p2/P3p3/1nNp4/1Q1P2P1/1P2PPBP/RR4K1 w - - 2 21"]' in pgn
    assert '[SetUp "1"]' in pgn
    assert 'Bg4' in pgn  # the opponent's idea is part of the exercise's statement
    assert 'Ra4' in pgn and 'Nd2' in pgn

def test_engine_evaluations_use_the_movers_point_of_view() -> None:
    """The one test that needs Stockfish: check the sign convention that everything else
       in exercises.py relies on."""
    # Whoever moves first here comes out on top: White by taking the queen with Bxd5, Black
    # by saving it. So both evaluations have to be positive, which is only true if scores are
    # relative to the side to move rather than to White.
    board = chess.Board("4k3/pp6/8/3q4/4B3/8/PP6/4K3 w - - 0 1")
    with exercises.Analyzer() as analyzer:
        top_white = analyzer.top_moves(board, 200_000, multipv=1)
        assert top_white and top_white[0].move == chess.Move.from_uci('e4d5')
        assert top_white[0].cp > 300
        passed = exercises.null_move_position(board)
        assert passed is not None
        top_black = analyzer.top_moves(passed, 200_000, multipv=1)
        assert top_black and top_black[0].cp > 300
        # eval_after reports from the point of view of the player who made the move.
        after_capture = analyzer.eval_after(board, board.parse_san("Bxd5"), 200_000)
        assert after_capture is not None and after_capture > 300

def main() -> None:
    """Lets the file be run directly, for when pytest isn't installed."""
    tests = [value for name, value in sorted(globals().items()) if name.startswith('test_')]
    for test in tests:
        test()
        print(f"passed: {test.__name__}")
    print(f"\n{len(tests)} tests passed.")

if __name__ == '__main__':
    main()
