"""Batch driver for the prophylaxis/conversion search.

Walks a pgn database most-recent-game-first, in parallel, and writes every position that
passes the criteria in exercises.py to a jsonl file (one hit per line) plus a pgn file.

Example:
    python3 find_exercises.py --db big_database.pgn --games 4000 --workers 7 --min-elo 2400
"""

from __future__ import annotations

import argparse
import dataclasses
import json
import multiprocessing as mp
import os
import time
from typing import Optional

import chess.pgn

import exercises
import pgn_index

def parse_args(argv: Optional[list[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--db', default='big_database.pgn', help='pgn file to search')
    parser.add_argument('--games', type=int, default=1000, help='how many games to analyse')
    parser.add_argument('--skip', type=int, default=0,
                        help='how many of the most recent games to skip over first')
    parser.add_argument('--workers', type=int, default=max(1, (os.cpu_count() or 2) - 1))
    parser.add_argument('--themes', default='prophylaxis,conversion')
    parser.add_argument('--min-elo', type=int, default=0,
                        help='both players must be at least this strong (0 to not care)')
    parser.add_argument('--min-plies', type=int, default=40)
    parser.add_argument('--min-date', type=int, default=0, help='e.g. 19990000')
    parser.add_argument('--out', default='exercise-hits', help='output filename prefix')
    parser.add_argument('--scan-nodes', type=int, default=exercises.Config.scan_nodes)
    parser.add_argument('--check-nodes', type=int, default=exercises.Config.check_nodes)
    parser.add_argument('--verify-nodes', type=int, default=exercises.Config.verify_nodes)
    parser.add_argument('--first-move', type=int, default=exercises.Config.first_move)
    return parser.parse_args(argv)

def eligible_game_nums(index: pgn_index.PgnIndex, games: int, skip: int = 0, min_elo: int = 0,
                       min_plies: int = 40, min_date: int = 0) -> list[int]:
    """Returns the game numbers to analyse: newest first, and only games that could hold a
       useful exercise (long enough, and played by strong enough players)."""
    wanted: list[int] = []
    candidates = index.game_nums_by_date()
    if min_date:
        candidates = [n for n in candidates if index.date_of(n) >= min_date]
    skipped = 0
    with open(index.pgn_path(), 'rb') as f:
        for game_num in candidates:
            headers = _read_headers(f, index, game_num)
            if headers is None:
                continue
            try:
                plies = int(headers.get('PlyCount', '0'))
            except ValueError:
                plies = 0
            if plies and plies < min_plies:
                continue
            if min_elo:
                try:
                    elos = [int(headers.get(k, '0')) for k in ('WhiteElo', 'BlackElo')]
                except ValueError:
                    continue
                if min(elos) < min_elo:
                    continue
            if skipped < skip:
                skipped += 1
                continue
            wanted.append(game_num)
            if len(wanted) >= games:
                break
    return wanted

def search_recent_games(specs, output_data, num_games: int, min_elo: int) -> None:
    """The single-process version, used by main.py: walks the most recent games of a database
       and reports every exercise found through the usual Output object."""
    index = pgn_index.get_index(specs.pgn())
    cfg = exercises.Config()
    if specs.move_to_begin_at():
        cfg.first_move = specs.move_to_begin_at()
    game_nums = eligible_game_nums(index, num_games, skip=specs.game_num_to_search_after() or 0,
                                   min_elo=min_elo)
    if not game_nums:
        print("No games matched the filters.")
        return
    print(f"Analysing {len(game_nums)} games, newest first: {index.date_of(game_nums[0])} "
          f"down to {index.date_of(game_nums[-1])}.")
    themes = (specs.type_of_position(),)
    with exercises.Analyzer() as analyzer:
        for game_num, game in index.read_games(game_nums):
            output_data.prep_for_new_game()
            try:
                found = list(exercises.find_in_game(analyzer, game, cfg, themes))
            except (ValueError, AssertionError) as err:
                print(f"Skipping game {game_num}: {err}")
                continue
            for exercise in found:
                exercise.game_info['game_num'] = game_num
                output_data.add_newest_hit(exercises.exercise_to_pgn(exercise))
                output_data.print_and_write_data(specs)
                output_data.clear_newest_hit()
            if output_data.num_games() % specs.default_output_interval() == 0:
                output_data.print_and_write_data(specs)
    output_data.print_and_write_data(specs)

def _read_headers(f, index: pgn_index.PgnIndex, game_num: int) -> Optional[dict]:
    """Reads just the header block of a game, cheaply."""
    f.seek(index._offsets[game_num])
    block = f.read(1400).decode('utf-8', errors='replace')
    headers = {}
    for line in block.splitlines():
        if not line.startswith('['):
            if headers:
                break
            continue
        key, _, rest = line[1:].partition(' "')
        headers[key] = rest.rsplit('"', 1)[0]
    return headers or None

def worker(worker_id: int, game_nums: list[int], args: argparse.Namespace,
           out_path: str, counter) -> None:
    cfg = exercises.Config(scan_nodes=args.scan_nodes, check_nodes=args.check_nodes,
                           verify_nodes=args.verify_nodes, first_move=args.first_move)
    themes = tuple(t.strip() for t in args.themes.split(','))
    index = pgn_index.get_index(args.db, verbose=False)
    hits = 0
    with exercises.Analyzer() as analyzer, open(out_path, 'w') as out:
        for done, (game_num, game) in enumerate(index.read_games(game_nums), start=1):
            try:
                for exercise in exercises.find_in_game(analyzer, game, cfg, themes):
                    exercise.game_info['game_num'] = game_num
                    exercise.game_info['db'] = os.path.basename(args.db)
                    out.write(json.dumps(dataclasses.asdict(exercise)) + '\n')
                    out.flush()
                    hits += 1
            except (ValueError, AssertionError) as err:
                print(f"[worker {worker_id}] skipping game {game_num}: {err}", flush=True)
            with counter.get_lock():
                counter.value += 1
            if done % 10 == 0:
                print(f"[worker {worker_id}] {done}/{len(game_nums)} games, {hits} hits",
                      flush=True)

def main(argv: Optional[list[str]] = None) -> None:
    args = parse_args(argv)
    started = time.time()
    index = pgn_index.get_index(args.db)
    print(f"{index.num_games()} games in {args.db}. Selecting games (newest first)...", flush=True)
    game_nums = eligible_game_nums(index, args.games, skip=args.skip, min_elo=args.min_elo,
                                   min_plies=args.min_plies, min_date=args.min_date)
    if not game_nums:
        print("No games matched the filters.")
        return
    print(f"Analysing {len(game_nums)} games, from {index.date_of(game_nums[0])} "
          f"down to {index.date_of(game_nums[-1])}, on {args.workers} workers.", flush=True)

    slices = [game_nums[i::args.workers] for i in range(args.workers)]
    counter = mp.Value('i', 0)
    out_paths = [f"{args.out}-{i}.jsonl" for i in range(args.workers)]
    procs = [mp.Process(target=worker, args=(i, slices[i], args, out_paths[i], counter))
             for i in range(args.workers) if slices[i]]
    for proc in procs:
        proc.start()
        time.sleep(0.5)  # so the engines don't all load their neural net at the same instant
    for proc in procs:
        proc.join()

    hits = merge_results(out_paths, args.out)
    print(f"\nDone in {(time.time() - started) / 60:.1f} min: {len(hits)} exercises found "
          f"in {counter.value} games -> {args.out}.jsonl / {args.out}.pgn", flush=True)

def merge_results(out_paths: list[str], prefix: str) -> list[dict]:
    """Gathers the per-worker output into one jsonl file and one pgn file."""
    hits: list[dict] = []
    for path in out_paths:
        if not os.path.exists(path):
            continue
        with open(path) as f:
            hits.extend(json.loads(line) for line in f if line.strip())
    hits.sort(key=lambda h: (h['theme'], -h['game_info'].get('game_num', 0)))
    with open(f"{prefix}.jsonl", 'w') as f:
        for hit in hits:
            f.write(json.dumps(hit) + '\n')
    with open(f"{prefix}.pgn", 'w') as f:
        for hit in hits:
            exercise = exercises.Exercise(**hit)
            f.write(exercises.exercise_to_pgn(exercise) + '\n\n')
    return hits

if __name__ == '__main__':
    main()
