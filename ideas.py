"""
- Add a way for the user to specify having at most a certain number of pieces total, rather than exactly that
  number.
    - Maybe ask the user for a min and max.
- Clean up the code a bit, wherever seems necessary.
- When the Stockfish fork is eventually on PyPI, and updated so that mypy can analyze it, import it again for
  this project instead of using models.py directly.
- Make the move count (when to start looking for positions) and games_parsed counter in the main loop more exact.
- Don't keep printing positions already found to the screen multiple times.
- Allow the user to specify a range of rows/files, rather than being forced to narrow down an area to just a single row/file.
- Allow for a "disjunction" in a requirement string. E.g., maybe the user wants any positions where a white rook
  is on any of a1, a2, or a3.
- Update the README with a section on the 'endgame' feature (i.e., allowed foramts for requirement strings).
  Could add a link to it in the code when asking the user to input.
- Could add an option where if the user wants, something like "R1p1" would mean one side has 1 rook,
  the other side has 1 pawn -- rather than it having to be White having 1 rook, Black having 1 pawn.
"""