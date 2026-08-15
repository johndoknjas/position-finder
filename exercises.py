"""Finds positions that work as training exercises on two themes:

  - prophylaxis: positions where the opponent has a concrete idea, and the (clearly) best
    move is a quiet move that takes that idea away. This follows Dvoretsky's definition:
    ask what the opponent would play if it were their move, and let the answer decide yours.
    The search literally does that, by handing the opponent a free move (a null move) and
    seeing what they would do with it.

  - conversion: positions where one side is clearly better (at least ~+0.8) but the win still
    has to be brought home, and where one move keeps the advantage while the natural
    alternative lets it slip away.

The work is done by a funnel: a cheap engine pass over every candidate position, then a
more expensive check of the survivors, then a slow verification of what is left.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterator, Optional

import chess
import chess.engine
import chess.pgn

MATE_SCORE = 100000

PIECE_VALUES = {chess.PAWN: 1, chess.KNIGHT: 3, chess.BISHOP: 3,
                chess.ROOK: 5, chess.QUEEN: 9, chess.KING: 0}

@dataclass
class MoveEval:
    """One line of engine output: a move, its evaluation (in centipawns, from the point of
       view of the side to move) and the principal variation."""
    move: chess.Move
    cp: int
    mate: Optional[int]
    pv: tuple[chess.Move, ...]

@dataclass
class Config:
    """Thresholds for the two detectors. All evaluations are centipawns, from the point of
       view of the side to move (the 'student')."""

    # Node budgets for the stages of the funnel. Each stage is roughly 4x the cost of the
    # one before it, and only a small fraction of positions ever reach the later ones.
    scan_depth: int = 12
    scan_nodes: int = 60_000
    probe_nodes: int = 120_000
    check_nodes: int = 250_000
    verify_nodes: int = 1_000_000

    # Which positions are worth an engine call at all.
    first_move: int = 14
    min_legal_moves: int = 6
    # Once a position in a game qualifies, skip ahead this many plies: neighbouring
    # positions in the same game make near-duplicate exercises.
    cooldown_plies: int = 8

    # Shared: how much better the best move has to be than the second best.
    gap: int = 70
    scan_gap: int = 70
    # How much slack to allow the shallow scan, which is noisy, before ruling a position out.
    scan_slack: int = 60

    # Prophylaxis.
    proph_min_eval: int = -80    # the student should not already be lost,
    proph_max_eval: int = 300    # nor already completely winning
    proph_min_threat: int = 90   # how much the opponent gains from a free move
    proph_min_prevention: int = 80  # how much the best move takes away from that idea
    proph_allowed_slack: int = 40   # how well the idea still has to work after the alternative
    proph_min_material: int = 14    # non-pawn material of both sides, so plans still exist

    # Conversion.
    conv_min_eval: int = 80      # 'one side is better' starts at +0.8
    conv_max_eval: int = 350     # but is not yet trivially winning
    conv_max_second: int = 45    # the alternative move throws the advantage away,
    conv_min_second: int = -60   # but doesn't lose - otherwise this is a tactic, not technique
    conv_max_material: int = 20  # simplified enough that this is technique, not a tactic
    conv_max_material_with_queens: int = 18  # queens on the board keep things sharper
    conv_min_pawns: int = 3

def _non_pawn_material(board: chess.Board) -> int:
    return sum(PIECE_VALUES[piece.piece_type] for piece in board.piece_map().values()
               if piece.piece_type != chess.PAWN)

def _num_pawns(board: chess.Board) -> int:
    return len(board.pieces(chess.PAWN, chess.WHITE)) + len(board.pieces(chess.PAWN, chess.BLACK))

def is_technical(board: chess.Board, cfg: Config) -> bool:
    """Whether the position is simplified enough that winning it is a matter of technique
       rather than of tactics - which is what makes a conversion exercise."""
    material = _non_pawn_material(board)
    limit = (cfg.conv_max_material_with_queens
             if board.pieces(chess.QUEEN, chess.WHITE) or board.pieces(chess.QUEEN, chess.BLACK)
             else cfg.conv_max_material)
    return material <= limit and _num_pawns(board) >= cfg.conv_min_pawns

def null_move_position(board: chess.Board) -> Optional[chess.Board]:
    """Returns the same position but with the opponent to move (i.e. the student passes),
       or None if that position would be illegal."""
    passed = board.copy(stack=False)
    passed.turn = not board.turn
    passed.ep_square = None
    return passed if passed.is_valid() else None

def is_quiet(board: chess.Board, move: chess.Move) -> bool:
    """A prophylactic move is a quiet one: it isn't a capture, a check or a promotion."""
    return not (board.is_capture(move) or move.promotion or board.gives_check(move))

class Analyzer:
    """A thin wrapper around a Stockfish process, giving evaluations in centipawns from the
       point of view of whoever is to move."""

    def __init__(self, engine_path: str = "stockfish", threads: int = 1, hash_mb: int = 64) -> None:
        # The generous timeout is for when several of these start at once: loading the neural
        # net off disk can take a while when the workers all do it together.
        self._engine = chess.engine.SimpleEngine.popen_uci(engine_path, timeout=120)
        self._engine.configure({"Threads": threads, "Hash": hash_mb})

    def close(self) -> None:
        self._engine.quit()

    def __enter__(self) -> "Analyzer":
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.close()

    def top_moves(self, board: chess.Board, nodes: int, multipv: int = 2,
                  depth: Optional[int] = None) -> list[MoveEval]:
        if board.is_game_over(claim_draw=False):
            return []
        limit = chess.engine.Limit(nodes=nodes, depth=depth)
        infos = self._engine.analyse(board, limit, multipv=multipv)
        results: list[MoveEval] = []
        for info in infos:
            pv = info.get("pv")
            score = info.get("score")
            if not pv or score is None:
                continue
            relative = score.relative
            results.append(MoveEval(pv[0], relative.score(mate_score=MATE_SCORE),
                                    relative.mate(), tuple(pv[:8])))
        return results

    def eval_after(self, board: chess.Board, move: chess.Move, nodes: int) -> Optional[int]:
        """Evaluates the position after the given move, from the point of view of the player
           who just made it."""
        after = board.copy(stack=False)
        after.push(move)
        if after.is_checkmate():
            return MATE_SCORE
        if after.is_game_over(claim_draw=False):
            return 0
        top = self.top_moves(after, nodes, multipv=1)
        return None if not top else -top[0].cp

@dataclass
class Exercise:
    """Everything needed to present one position as an exercise."""
    theme: str
    fen: str
    best_san: str
    best_uci: str
    second_san: str
    best_cp: int
    second_cp: int
    best_line: str
    second_line: str
    # Prophylaxis only: what the opponent wanted to do, and how much it was worth.
    opponent_idea_san: str = ''
    opponent_idea_line: str = ''
    threat_cp: int = 0
    prevention_cp: int = 0
    # Filled in by the caller, about the game the position came from.
    game_info: dict = field(default_factory=dict)

def _san(board: chess.Board, moves: tuple[chess.Move, ...]) -> str:
    return board.variation_san(list(moves)) if moves else ''

def worth_scanning(board: chess.Board, cfg: Config) -> bool:
    """A cheap check, so that most positions never reach the engine."""
    return (board.fullmove_number >= cfg.first_move and not board.is_check() and
            board.legal_moves.count() >= cfg.min_legal_moves)

def scan(analyzer: Analyzer, board: chess.Board, cfg: Config) -> Optional[list[MoveEval]]:
    """The cheap first pass: is there any sign of a single clearly best move here?"""
    top = analyzer.top_moves(board, cfg.scan_nodes, multipv=2, depth=cfg.scan_depth)
    if len(top) < 2 or top[0].mate is not None:
        return None
    return top if top[0].cp - top[1].cp >= cfg.scan_gap else None

def proph_prefilter(board: chess.Board, top: list[MoveEval], cfg: Config) -> bool:
    """Everything about a prophylaxis candidate that can be ruled out from the shallow scan
       alone, so that the expensive stages only see plausible positions."""
    best, second = top[0], top[1]
    return (_non_pawn_material(board) >= cfg.proph_min_material and
            cfg.proph_min_eval - cfg.scan_slack <= best.cp <= cfg.proph_max_eval + cfg.scan_slack and
            best.cp - second.cp >= cfg.gap - cfg.scan_slack and
            is_quiet(board, best.move))

def conv_prefilter(board: chess.Board, top: list[MoveEval], cfg: Config) -> bool:
    """The same idea for conversion candidates."""
    best, second = top[0], top[1]
    return (is_technical(board, cfg) and
            cfg.conv_min_eval - cfg.scan_slack <= best.cp <= cfg.conv_max_eval + cfg.scan_slack and
            best.cp - second.cp >= cfg.gap - cfg.scan_slack and
            cfg.conv_min_second - cfg.scan_slack <= second.cp <= cfg.conv_max_second + cfg.scan_slack)

def proph_probe(analyzer: Analyzer, board: chess.Board, top: list[MoveEval],
                cfg: Config) -> bool:
    """The cheap version of the key prophylaxis question: given a free move, does the
       opponent have anything worth having?"""
    passed = null_move_position(board)
    if passed is None:
        return False
    opponent = analyzer.top_moves(passed, cfg.probe_nodes, multipv=1)
    return bool(opponent) and opponent[0].cp + top[0].cp >= cfg.proph_min_threat - cfg.scan_slack

def prophylaxis_at(analyzer: Analyzer, board: chess.Board, cfg: Config,
                   nodes: int) -> Optional[Exercise]:
    """Checks the prophylaxis criteria at the given node budget.

       The position qualifies when all of the following hold:
         1. one quiet move is clearly the best,
         2. the opponent, given a free move, would achieve something concrete,
         3. the best move takes that idea away,
         4. the second best move does not (so seeing the opponent's idea is the whole point)."""

    if _non_pawn_material(board) < cfg.proph_min_material:
        return None
    aux_nodes = nodes // 2  # for the follow-up questions, which are comparisons rather than verdicts
    top = analyzer.top_moves(board, nodes, multipv=2)
    if len(top) < 2 or top[0].mate is not None or top[1].mate is not None:
        return None
    best, second = top[0], top[1]
    if not cfg.proph_min_eval <= best.cp <= cfg.proph_max_eval:
        return None
    if best.cp - second.cp < cfg.gap:
        return None
    if not is_quiet(board, best.move):
        return None

    passed = null_move_position(board)
    if passed is None:
        return None
    opponent = analyzer.top_moves(passed, nodes, multipv=1)
    if not opponent:
        return None
    idea = opponent[0]
    # What the opponent gains by being handed the move: their evaluation after their own
    # idea, compared with what they would get if the student played the best move.
    threat = idea.cp + best.cp
    if threat < cfg.proph_min_threat:
        return None

    # Does the best move actually stop that idea?
    after_best = board.copy(stack=False)
    after_best.push(best.move)
    if idea.move in after_best.legal_moves:
        idea_cp_now = analyzer.eval_after(after_best, idea.move, aux_nodes)
        if idea_cp_now is None or idea.cp - idea_cp_now < cfg.proph_min_prevention:
            return None
        prevention = idea.cp - idea_cp_now
    else:
        prevention = MATE_SCORE  # the idea is not even a legal move any more

    # Would the natural alternative have allowed it? If not, the position is not really
    # about the opponent's plan.
    after_second = board.copy(stack=False)
    after_second.push(second.move)
    if idea.move not in after_second.legal_moves:
        return None
    idea_cp_after_second = analyzer.eval_after(after_second, idea.move, aux_nodes)
    if idea_cp_after_second is None or idea_cp_after_second < idea.cp - cfg.proph_allowed_slack:
        return None

    return Exercise(
        theme='prophylaxis',
        fen=board.fen(),
        best_san=board.san(best.move),
        best_uci=best.move.uci(),
        second_san=board.san(second.move),
        best_cp=best.cp,
        second_cp=second.cp,
        best_line=_san(board, best.pv),
        second_line=_san(board, second.pv),
        opponent_idea_san=passed.san(idea.move),
        opponent_idea_line=_san(passed, idea.pv),
        threat_cp=threat,
        prevention_cp=min(prevention, MATE_SCORE),
    )

def conversion_at(analyzer: Analyzer, board: chess.Board, cfg: Config,
                  nodes: int) -> Optional[Exercise]:
    """Checks the conversion criteria at the given node budget.

       The position qualifies when the side to move is clearly better but not yet home, the
       material is simplified enough that the job is technique rather than tactics, and one
       move keeps the advantage while the second best move lets most of it go."""

    if not is_technical(board, cfg):
        return None
    top = analyzer.top_moves(board, nodes, multipv=2)
    if len(top) < 2 or top[0].mate is not None:
        return None
    best, second = top[0], top[1]
    if not cfg.conv_min_eval <= best.cp <= cfg.conv_max_eval:
        return None
    second_cp = second.cp if second.mate is None else (MATE_SCORE if second.mate > 0 else -MATE_SCORE)
    if best.cp - second_cp < cfg.gap:
        return None
    if not cfg.conv_min_second <= second_cp <= cfg.conv_max_second:
        return None

    return Exercise(
        theme='conversion',
        fen=board.fen(),
        best_san=board.san(best.move),
        best_uci=best.move.uci(),
        second_san=board.san(second.move),
        best_cp=best.cp,
        second_cp=second_cp,
        best_line=_san(board, best.pv),
        second_line=_san(board, second.pv),
    )

def find_in_game(analyzer: Analyzer, game: chess.pgn.Game, cfg: Config,
                 themes: tuple[str, ...] = ('prophylaxis', 'conversion')) -> Iterator[Exercise]:
    """Walks one game and yields every position in it that survives the whole funnel."""
    board = game.board()
    if board.fen() != chess.STARTING_FEN:
        return
    cooldown = {theme: 0 for theme in themes}
    for ply, played in enumerate(game.mainline_moves()):
        for theme in cooldown:
            cooldown[theme] = max(0, cooldown[theme] - 1)
        if not worth_scanning(board, cfg) or all(cooldown.values()):
            board.push(played)
            continue
        top = scan(analyzer, board, cfg)
        if top is None:
            board.push(played)
            continue
        for theme in themes:
            if cooldown[theme]:
                continue
            if theme == 'prophylaxis':
                if not proph_prefilter(board, top, cfg) or not proph_probe(analyzer, board, top, cfg):
                    continue
                detector = prophylaxis_at
            else:
                if not conv_prefilter(board, top, cfg):
                    continue
                detector = conversion_at
            found = detector(analyzer, board, cfg, cfg.check_nodes)
            if found is None:
                continue
            found = detector(analyzer, board, cfg, cfg.verify_nodes)
            if found is None:
                continue
            cooldown[theme] = cfg.cooldown_plies
            found.game_info = describe_game(game, board, played, found.best_uci)
            found.game_info['ply'] = ply
            yield found
        board.push(played)

def describe_game(game: chess.pgn.Game, board: chess.Board, played: chess.Move,
                  best_uci: str) -> dict:
    headers = game.headers
    return {
        'white': headers.get('White', '?'),
        'black': headers.get('Black', '?'),
        'white_elo': headers.get('WhiteElo', '?'),
        'black_elo': headers.get('BlackElo', '?'),
        'event': headers.get('Event', '?'),
        'site': headers.get('Site', '?'),
        'date': headers.get('Date', '?'),
        'result': headers.get('Result', '*'),
        'eco': headers.get('ECO', '?'),
        'move_number': board.fullmove_number,
        'side_to_move': 'White' if board.turn == chess.WHITE else 'Black',
        'played_san': board.san(played),
        'player_found_it': played.uci() == best_uci,
    }

def exercise_to_pgn(exercise: Exercise) -> str:
    """Writes one exercise as a pgn game with a set-up position, so it can be dropped into a
       chess GUI or a lichess study."""
    info = exercise.game_info
    board = chess.Board(exercise.fen)
    game = chess.pgn.Game()
    game.setup(board)
    game.headers['Event'] = f"{exercise.theme.capitalize()} exercise"
    game.headers['Site'] = info.get('site', '?')
    game.headers['Date'] = info.get('date', '????.??.??')
    game.headers['White'] = info.get('white', '?')
    game.headers['Black'] = info.get('black', '?')
    game.headers['Result'] = '*'
    for key in ('WhiteElo', 'BlackElo'):
        value = info.get(key.lower().replace('elo', '_elo'), '?')
        if value not in ('?', ''):
            game.headers[key] = value
    game.headers['Annotator'] = 'position-finder'
    game.headers['SourceEvent'] = info.get('event', '?')

    task = ("Black to move" if board.turn == chess.BLACK else "White to move")
    if exercise.theme == 'prophylaxis':
        summary = (f"{task}. What does the opponent want to play? "
                   f"If it were their move they would play {exercise.opponent_idea_san} "
                   f"({exercise.threat_cp / 100:+.2f} worth of ideas). Find the move that stops it.")
    else:
        summary = (f"{task}, and better by {exercise.best_cp / 100:+.2f}. "
                   f"Find the move that keeps the advantage - "
                   f"the natural {exercise.second_san} only gives {exercise.second_cp / 100:+.2f}.")
    played = info.get('played_san', '?')
    found = "played it in the game" if info.get('player_found_it') else f"played {played} instead"
    summary += f" [{info.get('white','?')}-{info.get('black','?')}, {info.get('date','?')}; the player {found}.]"

    node = game.add_variation(chess.Move.from_uci(exercise.best_uci))
    node.comment = f"Best: {exercise.best_san} ({exercise.best_cp / 100:+.2f}). {exercise.best_line}"
    second_move = board.parse_san(exercise.second_san)
    alt = game.add_variation(second_move)
    alt.comment = (f"Second best: {exercise.second_san} ({exercise.second_cp / 100:+.2f}). "
                   f"{exercise.second_line}")
    if exercise.theme == 'prophylaxis':
        alt.comment += f" Now {exercise.opponent_idea_san} works: {exercise.opponent_idea_line}"
    game.comment = summary
    return str(game)
