# position_finder
Finds games which at some point satisfy certain piece/pawn configurations (as specified by the user).

To run this program, you'll need a pgn database for the games, and also a stockfish executable (https://stockfishchess.org/), with the file name being 'stockfish'. Both the database and the stockfish engine should be put in the same directory as main.py.

This project's dependencies include the 'python-chess' and 'stockfish' PyPI packages (https://pypi.org/project/python-chess/, https://pypi.org/project/stockfish/).

The program can be run with 'python3 main.py'. It will output results to the console, as well as to generated textfiles (where the filename is a unique number based on the current time).

## Training exercises: the 'prophylaxis' and 'conversion' features

Two of the features look for positions to use as training exercises, rather than for piece configurations.

- **prophylaxis** looks for positions where the opponent has a concrete idea, and where one
  quiet move (clearly the best one) takes that idea away. It works the way Dvoretsky told
  students to think: it hands the opponent a free move to see what they would play, and then
  checks that the best move stops exactly that, while the second best move allows it.
- **conversion** looks for positions where one side is clearly better (about +0.8 or more) in a
  simplified position, and where the best move keeps the advantage while the natural
  alternative lets most of it slip away. These work either as 'find the move' exercises or as
  starting positions for training games.

Both features walk the database **most recent game first**. The first run over a database
builds a game index under `pgn-index/`, which takes a minute or two for a multi-gigabyte pgn
and is reused afterwards. Each hit is written out as a pgn game with a set-up position, the
solution, and the losing alternative, so it can be dropped straight into a chess GUI or a
lichess study.

For a large search, `find_exercises.py` runs the same code over several cores at once, and
`curate_exercises.py` then re-checks the results with a much bigger engine budget and ranks
what survives:

    python3 find_exercises.py --db big_database.pgn --games 2000 --workers 7 --min-elo 2400
    python3 curate_exercises.py --hits 'exercise-hits-*.jsonl' --top 40

The thresholds that define both themes (how big the gap to the second best move must be, how
much the opponent's idea has to be worth, and so on) are collected in the `Config` class in
`exercises.py`.
