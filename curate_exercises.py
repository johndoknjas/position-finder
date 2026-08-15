"""Turns the raw output of find_exercises.py into a short, ranked set of exercises.

The search stage is deliberately generous, so this stage does the quality control:
  - drops duplicates and positions from the same game,
  - re-checks every survivor with a much bigger engine budget, so that a 'clearly best move'
    is not just an artefact of a shallow search,
  - ranks what is left by how instructive it looks.

Example:
    python3 curate_exercises.py --hits 'exercise-hits-*.jsonl' --top 40 --workers 5
"""

from __future__ import annotations

import argparse
import dataclasses
import glob
import json
import multiprocessing as mp
import os
from typing import Optional

import chess

import exercises

def parse_args(argv: Optional[list[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--hits', required=True, help='glob for the jsonl files to read')
    parser.add_argument('--out', default='curated', help='output filename prefix')
    parser.add_argument('--top', type=int, default=40,
                        help='how many candidates (per theme) to re-verify')
    parser.add_argument('--workers', type=int, default=max(1, (os.cpu_count() or 2) - 3))
    parser.add_argument('--verify-nodes', type=int, default=4_000_000)
    parser.add_argument('--per-game', type=int, default=1,
                        help='at most this many exercises from any one game')
    return parser.parse_args(argv)

def load_hits(pattern: str) -> list[dict]:
    hits: list[dict] = []
    for path in sorted(glob.glob(pattern)):
        with open(path) as f:
            hits.extend(json.loads(line) for line in f if line.strip())
    return hits

def piece_count(fen: str) -> int:
    return sum(1 for c in fen.split(' ')[0] if c.isalpha())

def score_of(hit: dict) -> float:
    """A rough ranking of how instructive an exercise looks, used to decide what is worth
       verifying and in what order to present the results."""
    info = hit['game_info']
    gap = hit['best_cp'] - hit['second_cp']
    # A gap of one to two pawns is the sweet spot: enough that the move really is the move,
    # but not so much that every other move simply loses on the spot, which makes for a
    # find-the-only-move puzzle rather than an exercise in a way of thinking.
    score = 1.5 if 70 <= gap <= 200 else 1.0 if gap <= 350 else 0.4
    if not info.get('player_found_it'):
        score += 1.0  # a strong player going wrong here is good evidence that it is a real test
    if hit['theme'] == 'prophylaxis':
        score += min(hit['threat_cp'], 300) / 100
        score += min(hit['prevention_cp'], 250) / 100
        if abs(hit['best_cp']) <= 100:
            score += 0.5  # a balanced position, so the exercise is not about winning material
        if 'x' not in hit['opponent_idea_san']:
            score += 0.5  # a positional idea rather than a capture is a subtler thing to spot
    else:
        if 100 <= hit['best_cp'] <= 250:
            score += 0.5  # clearly better, with real work still to do
        if -20 <= hit['second_cp'] <= 45:
            score += 0.5  # the alternative draws rather than loses: a pure conversion decision
        if piece_count(hit['fen']) <= 12:
            score += 0.5
    return score

def dedupe(hits: list[dict], per_game: int) -> list[dict]:
    """Keeps the best-looking exercise (or few) from each game, and drops repeats."""
    hits = sorted(hits, key=score_of, reverse=True)
    kept: list[dict] = []
    seen_fens: set[str] = set()
    from_game: dict[tuple, int] = {}
    for hit in hits:
        fen_key = ' '.join(hit['fen'].split(' ')[:4])
        info = hit['game_info']
        game_key = (info.get('db'), info.get('game_num'), hit['theme'])
        if fen_key in seen_fens or from_game.get(game_key, 0) >= per_game:
            continue
        seen_fens.add(fen_key)
        from_game[game_key] = from_game.get(game_key, 0) + 1
        kept.append(hit)
    return kept

def verify(hit: dict, verify_nodes: int) -> Optional[dict]:
    """Runs the detector again on one position, with a much bigger budget."""
    cfg = exercises.Config(check_nodes=verify_nodes // 2, verify_nodes=verify_nodes)
    board = chess.Board(hit['fen'])
    detector = (exercises.prophylaxis_at if hit['theme'] == 'prophylaxis'
                else exercises.conversion_at)
    with exercises.Analyzer() as analyzer:
        found = detector(analyzer, board, cfg, verify_nodes)
    if found is None:
        return None
    verified = dataclasses.asdict(found)
    verified['game_info'] = hit['game_info']
    # Keep what the shallower search thought, so that the two can be compared.
    verified['game_info']['first_pass'] = {
        'best_san': hit['best_san'], 'best_cp': hit['best_cp'], 'second_cp': hit['second_cp'],
    }
    verified['game_info']['player_found_it'] = (
        verified['game_info'].get('played_san') == found.best_san)
    return verified

def _verify_one(job: tuple[dict, int]) -> Optional[dict]:
    hit, verify_nodes = job
    try:
        return verify(hit, verify_nodes)
    except Exception as err:  # a hung or unhappy engine should not sink the whole batch
        print(f"  verification failed for {hit['fen']}: {err}", flush=True)
        return None

def lichess_url(fen: str) -> str:
    return "https://lichess.org/analysis/standard/" + fen.replace(' ', '_')

def main(argv: Optional[list[str]] = None) -> None:
    args = parse_args(argv)
    hits = load_hits(args.hits)
    print(f"Loaded {len(hits)} raw hits.")
    themes = sorted({hit['theme'] for hit in hits})
    shortlist: list[dict] = []
    for theme in themes:
        of_theme = dedupe([h for h in hits if h['theme'] == theme], args.per_game)
        print(f"  {theme}: {len(of_theme)} after de-duplication, "
              f"verifying the top {min(args.top, len(of_theme))}")
        shortlist.extend(of_theme[:args.top])

    jobs = [(hit, args.verify_nodes) for hit in shortlist]
    with mp.Pool(args.workers) as pool:
        verified = [v for v in pool.imap_unordered(_verify_one, jobs) if v is not None]
    print(f"{len(verified)} of {len(shortlist)} survived verification at "
          f"{args.verify_nodes / 1e6:.1f}M nodes.")

    verified.sort(key=lambda h: (h['theme'], -score_of(h)))
    with open(f"{args.out}.jsonl", 'w') as f:
        for hit in verified:
            f.write(json.dumps(hit) + '\n')
    with open(f"{args.out}.pgn", 'w') as f:
        for hit in verified:
            f.write(exercises.exercise_to_pgn(exercises.Exercise(**hit)) + '\n\n')
    print(f"Wrote {args.out}.jsonl and {args.out}.pgn")
    for hit in verified:
        info = hit['game_info']
        print(f"\n[{hit['theme']}] {hit['fen']}")
        print(f"  {info['side_to_move']} to play, move {info['move_number']}: "
              f"{hit['best_san']} ({hit['best_cp'] / 100:+.2f}) vs "
              f"{hit['second_san']} ({hit['second_cp'] / 100:+.2f})")
        if hit['theme'] == 'prophylaxis':
            print(f"  opponent's idea: {hit['opponent_idea_san']} "
                  f"(worth {hit['threat_cp'] / 100:+.2f})")
        print(f"  {info['white']} - {info['black']}, {info['event']} {info['date']}; "
              f"played {info['played_san']}")
        print(f"  {lichess_url(hit['fen'])}")

if __name__ == '__main__':
    main()
