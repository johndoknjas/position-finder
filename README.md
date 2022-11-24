# position-finder
Finds games which at some point satisfy certain piece/pawn configurations (as specified by the user).

To run this program, you'll need a pgn database for the games, and also a stockfish executable (https://stockfishchess.org/), with the file name being 'stockfish'. Both the database and the stockfish engine should be put in the same directory as main.py. 

This project's dependencies include the 'python-chess' and 'stockfish' PyPI packages.

The program can be run with 'python3 main.py'. It will output results to the console, as well as to generated textfiles (where the filename is a unique number based on the current time). Textfile(s) will be created storing positions matching the requirements.
