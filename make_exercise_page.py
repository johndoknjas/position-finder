"""Renders curated exercises as a single self-contained html page, with board diagrams.

    python3 curate_exercises.py --hits 'exercise-hits-*.jsonl' --out curated
    python3 make_exercise_page.py --hits curated.jsonl --out exercises.html
"""

from __future__ import annotations

import argparse
import html
import json
from typing import Optional

import chess
import chess.svg

BOARD_COLORS = {
    'square light': '#DCE1E8',
    'square dark': '#7C93A9',
    'margin': '#C3CAD4',
    'coord': '#2B313A',
    'inner border': '#5D6B7C',
    'outer border': '#C3CAD4',
    'arrow green': '#1D6B57cc',
    'arrow red': '#A8341Ecc',
}

THEME_TEXT = {
    'prophylaxis': ("Prophylaxis",
                    "Ask what the opponent would play if it were their move, then stop it."),
    'conversion': ("Conversion",
                   "One side is clearly better. Find the move that brings the point home."),
}

def parse_args(argv: Optional[list[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--hits', default='curated.jsonl')
    parser.add_argument('--out', default='exercises.html')
    parser.add_argument('--title', default='Prophylaxis &amp; Conversion')
    parser.add_argument('--games-searched', type=int, default=0)
    parser.add_argument('--source', default='')
    return parser.parse_args(argv)

def diagram(fen: str, arrows: list = [], size: int = 340) -> str:
    board = chess.Board(fen)
    return chess.svg.board(board, orientation=board.turn, size=size, colors=BOARD_COLORS,
                           arrows=arrows, borders=True)

def solution_diagram(hit: dict) -> str:
    """The same position with the point of the exercise drawn on it: the move to play in
       green, and (for prophylaxis) the idea it takes away in red."""
    board = chess.Board(hit['fen'])
    best = chess.Move.from_uci(hit['best_uci'])
    arrows = [chess.svg.Arrow(best.from_square, best.to_square, color='green')]
    if hit['theme'] == 'prophylaxis' and hit.get('opponent_idea_san'):
        passed = board.copy(stack=False)
        passed.turn = not board.turn
        passed.ep_square = None
        try:
            idea = passed.parse_san(hit['opponent_idea_san'])
            arrows.append(chess.svg.Arrow(idea.from_square, idea.to_square, color='red'))
        except ValueError:
            pass
    return diagram(hit['fen'], arrows, size=300)

def evaluation(cp: int) -> str:
    return f"{cp / 100:+.2f}"

def source_line(info: dict) -> str:
    players = f"{info.get('white', '?')} &ndash; {info.get('black', '?')}"
    elos = [info.get('white_elo'), info.get('black_elo')]
    rating = (f" ({elos[0]}/{elos[1]})" if all(e and e != '?' for e in elos) else '')
    date = (info.get('date') or '').split('.')[0]
    event = info.get('event', '?')
    return f"{players}{rating} &middot; {event} {date}"

def exercise_html(hit: dict, number: int) -> str:
    info = hit['game_info']
    theme = hit['theme']
    to_move = info.get('side_to_move', 'White')
    if theme == 'prophylaxis':
        brief = (f"<p class=\"brief\">{to_move} to play. If the opponent were given a free move "
                 f"they would play <span class=\"move\">{html.escape(hit['opponent_idea_san'])}</span>, "
                 f"worth about <span class=\"num\">{evaluation(hit['threat_cp'])}</span> to them. "
                 f"Find the quiet move that takes it away.</p>")
    else:
        brief = (f"<p class=\"brief\">{to_move} to play, and better by "
                 f"<span class=\"num\">{evaluation(hit['best_cp'])}</span>. One move keeps that; "
                 f"the natural <span class=\"move\">{html.escape(hit['second_san'])}</span> leaves only "
                 f"<span class=\"num\">{evaluation(hit['second_cp'])}</span>. Find it.</p>")

    played = html.escape(info.get('played_san', '?'))
    verdict = ("played it in the game" if info.get('player_found_it')
               else f"went for {played} instead")
    rows = [
        ("Best", f"<span class=\"move\">{html.escape(hit['best_san'])}</span>",
         evaluation(hit['best_cp'])),
        ("Second best", f"<span class=\"move\">{html.escape(hit['second_san'])}</span>",
         evaluation(hit['second_cp'])),
    ]
    if theme == 'prophylaxis':
        rows.append(("Opponent's idea",
                     f"<span class=\"move\">{html.escape(hit['opponent_idea_san'])}</span>",
                     evaluation(hit['threat_cp'])))
    table = '\n'.join(
        f"<tr><th>{label}</th><td>{move}</td><td class=\"num\">{value}</td></tr>"
        for label, move, value in rows
    )
    lines = [f"<p class=\"line\"><span class=\"label\">Main line</span> "
             f"{html.escape(hit['best_line'])}</p>"]
    if hit.get('second_line'):
        lines.append(f"<p class=\"line\"><span class=\"label\">If instead</span> "
                     f"{html.escape(hit['second_line'])}</p>")
    if theme == 'prophylaxis' and hit.get('opponent_idea_line'):
        lines.append(f"<p class=\"line\"><span class=\"label\">The idea</span> "
                     f"{html.escape(hit['opponent_idea_line'])}</p>")
    fen = html.escape(hit['fen'])
    lichess = "https://lichess.org/analysis/standard/" + hit['fen'].replace(' ', '_')

    return f'''
<article class="exercise {theme}">
  <header>
    <span class="number">{number}</span>
    <span class="chip">{THEME_TEXT[theme][0]}</span>
    <span class="source">{source_line(info)}, move {info.get('move_number', '?')}</span>
  </header>
  <div class="body">
    <figure class="board">{diagram(hit['fen'])}</figure>
    <div class="text">
      {brief}
      <details>
        <summary>Show the solution</summary>
        <div class="solution">
          <figure class="board small">{solution_diagram(hit)}</figure>
          <table>{table}</table>
          {''.join(lines)}
          <p class="meta">The player {verdict}. <a href="{lichess}">Open in an analysis board</a></p>
          <p class="fen"><span class="label">FEN</span> {fen}</p>
        </div>
      </details>
    </div>
  </div>
</article>'''

def page_html(hits: list[dict], args: argparse.Namespace) -> str:
    by_theme: dict[str, list[dict]] = {}
    for hit in hits:
        by_theme.setdefault(hit['theme'], []).append(hit)
    sections = []
    for theme in ('prophylaxis', 'conversion'):
        of_theme = by_theme.get(theme, [])
        if not of_theme:
            continue
        name, blurb = THEME_TEXT[theme]
        cards = '\n'.join(exercise_html(hit, i) for i, hit in enumerate(of_theme, start=1))
        sections.append(f'''
<section id="{theme}">
  <div class="section-head">
    <h2>{name}</h2>
    <p>{blurb}</p>
    <span class="count">{len(of_theme)} positions</span>
  </div>
  {cards}
</section>''')

    searched = (f"Found by searching the {args.games_searched:,} most recent games of "
                f"{html.escape(args.source)}" if args.games_searched and args.source else '')

    return f'''<title>{args.title}</title>
<style>
:root {{
  color-scheme: light dark;
  --ground: #F3F4F7;
  --surface: #FFFFFF;
  --sunken: #E9EBF0;
  --ink: #15181D;
  --ink-soft: #5A6371;
  --rule: #D5D9E1;
  --proph: #1D6B57;
  --conv: #9A4A16;
  --link: #2A5DA8;
  --shadow: 0 1px 2px rgba(21, 24, 29, .06), 0 8px 24px -12px rgba(21, 24, 29, .18);
  --display: Georgia, "Iowan Old Style", "Times New Roman", serif;
  --body: system-ui, -apple-system, "Segoe UI", Roboto, sans-serif;
  --mono: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
}}
@media (prefers-color-scheme: dark) {{
  :root:not([data-theme="light"]) {{
    --ground: #0F1216;
    --surface: #171B21;
    --sunken: #1E242C;
    --ink: #E7EAEF;
    --ink-soft: #9BA5B3;
    --rule: #2A313B;
    --proph: #64C2A6;
    --conv: #E3945C;
    --link: #82AEEA;
    --shadow: 0 1px 2px rgba(0, 0, 0, .4), 0 10px 28px -14px rgba(0, 0, 0, .7);
  }}
}}
:root[data-theme="dark"] {{
  --ground: #0F1216;
  --surface: #171B21;
  --sunken: #1E242C;
  --ink: #E7EAEF;
  --ink-soft: #9BA5B3;
  --rule: #2A313B;
  --proph: #64C2A6;
  --conv: #E3945C;
  --link: #82AEEA;
  --shadow: 0 1px 2px rgba(0, 0, 0, .4), 0 10px 28px -14px rgba(0, 0, 0, .7);
}}

* {{ box-sizing: border-box; }}
body {{
  margin: 0;
  background: var(--ground);
  color: var(--ink);
  font-family: var(--body);
  font-size: 16px;
  line-height: 1.55;
  -webkit-font-smoothing: antialiased;
}}
.wrap {{ max-width: 960px; margin: 0 auto; padding: 0 20px 96px; }}

header.page {{ padding: 72px 0 40px; border-bottom: 1px solid var(--rule); }}
header.page h1 {{
  font-family: var(--display);
  font-size: clamp(2.2rem, 5vw, 3.4rem);
  line-height: 1.05;
  letter-spacing: -0.015em;
  margin: 0 0 18px;
  text-wrap: balance;
}}
header.page .standfirst {{
  font-size: 1.08rem;
  color: var(--ink-soft);
  max-width: 62ch;
  margin: 0 0 28px;
}}
.method {{
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
  gap: 20px 32px;
  padding: 22px 24px;
  background: var(--surface);
  border: 1px solid var(--rule);
  border-radius: 4px;
  box-shadow: var(--shadow);
}}
.method h3 {{
  font-family: var(--body);
  font-size: .72rem;
  text-transform: uppercase;
  letter-spacing: .1em;
  color: var(--ink-soft);
  margin: 0 0 6px;
}}
.method p {{ margin: 0; font-size: .93rem; }}

section {{ padding-top: 56px; }}
.section-head {{
  display: flex;
  flex-wrap: wrap;
  align-items: baseline;
  gap: 8px 16px;
  padding-bottom: 10px;
  border-bottom: 2px solid currentColor;
  margin-bottom: 28px;
}}
#prophylaxis .section-head {{ color: var(--proph); }}
#conversion .section-head {{ color: var(--conv); }}
.section-head h2 {{
  font-family: var(--display);
  font-size: 1.75rem;
  margin: 0;
  letter-spacing: -0.01em;
}}
.section-head p {{ margin: 0; color: var(--ink-soft); flex: 1 1 320px; font-size: .95rem; }}
.section-head .count {{
  font-family: var(--mono);
  font-size: .78rem;
  color: var(--ink-soft);
  font-variant-numeric: tabular-nums;
}}

.exercise {{
  background: var(--surface);
  border: 1px solid var(--rule);
  border-radius: 4px;
  box-shadow: var(--shadow);
  margin-bottom: 22px;
  overflow: hidden;
}}
.exercise header {{
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 12px;
  padding: 14px 20px;
  border-bottom: 1px solid var(--rule);
  background: var(--sunken);
}}
.exercise .number {{
  font-family: var(--display);
  font-size: 1.15rem;
  font-weight: 700;
  min-width: 1.4em;
  font-variant-numeric: tabular-nums;
}}
.exercise .chip {{
  font-size: .68rem;
  text-transform: uppercase;
  letter-spacing: .09em;
  padding: 3px 9px;
  border-radius: 999px;
  border: 1px solid currentColor;
}}
.prophylaxis .chip, .prophylaxis .number {{ color: var(--proph); }}
.conversion .chip, .conversion .number {{ color: var(--conv); }}
.exercise .source {{ font-size: .85rem; color: var(--ink-soft); flex: 1 1 240px; }}

.body {{ display: flex; flex-wrap: wrap; gap: 28px; padding: 24px 20px; align-items: flex-start; }}
figure.board {{ margin: 0; flex: 0 0 340px; max-width: 100%; line-height: 0; }}
figure.board.small {{ flex-basis: 300px; margin: 4px 0 18px; }}
figure.board svg {{ width: 100%; height: auto; border-radius: 2px; }}
.text {{ flex: 1 1 300px; min-width: 260px; }}
.brief {{ margin: 0 0 18px; }}
.move {{ font-family: var(--mono); font-weight: 600; }}
.num {{ font-family: var(--mono); font-variant-numeric: tabular-nums; }}

details {{ border-top: 1px dashed var(--rule); padding-top: 14px; }}
summary {{
  cursor: pointer;
  font-size: .8rem;
  text-transform: uppercase;
  letter-spacing: .09em;
  color: var(--ink-soft);
  list-style: none;
}}
summary::-webkit-details-marker {{ display: none; }}
summary::before {{ content: "+ "; font-family: var(--mono); }}
details[open] summary::before {{ content: "\\2212 "; }}
summary:hover, summary:focus-visible {{ color: var(--ink); }}
.solution {{ padding-top: 14px; }}
.solution table {{ border-collapse: collapse; width: 100%; margin-bottom: 14px; font-size: .92rem; }}
.solution th {{
  text-align: left;
  font-weight: 400;
  color: var(--ink-soft);
  font-size: .78rem;
  text-transform: uppercase;
  letter-spacing: .07em;
  padding: 5px 12px 5px 0;
  white-space: nowrap;
}}
.solution td {{ padding: 5px 0; }}
.solution td.num {{ text-align: right; }}
.line {{ margin: 0 0 8px; font-family: var(--mono); font-size: .84rem; line-height: 1.5; }}
.label {{
  font-family: var(--body);
  font-size: .7rem;
  text-transform: uppercase;
  letter-spacing: .08em;
  color: var(--ink-soft);
  margin-right: 6px;
}}
.meta {{ font-size: .88rem; color: var(--ink-soft); margin: 14px 0 6px; }}
.fen {{ font-family: var(--mono); font-size: .76rem; color: var(--ink-soft);
        overflow-x: auto; white-space: nowrap; margin: 0; }}
a {{ color: var(--link); }}
a:focus-visible, summary:focus-visible {{ outline: 2px solid var(--link); outline-offset: 3px; }}

footer {{ margin-top: 64px; padding-top: 20px; border-top: 1px solid var(--rule);
          color: var(--ink-soft); font-size: .86rem; }}
@media (max-width: 640px) {{
  header.page {{ padding-top: 48px; }}
  figure.board {{ flex-basis: 100%; }}
}}
</style>

<div class="wrap">
<header class="page">
  <h1>{args.title}</h1>
  <p class="standfirst">Two sets of training positions taken from real games. In the first, the
  point is to see what the opponent wants and stop it before it happens. In the second, one side
  is already better and has to turn that into a win. Every position has one move that works and a
  natural-looking one that does not.</p>
  <div class="method">
    <div>
      <h3>How prophylaxis was found</h3>
      <p>Each position was given to Stockfish twice: once normally, and once with the opponent
      handed a free move. A position qualifies when that free move would be worth a lot, when the
      best move is a quiet one that takes it away, and when the second best move allows it.</p>
    </div>
    <div>
      <h3>How conversion was found</h3>
      <p>Simplified positions where one side stands at least +0.8, the best move keeps that
      advantage, and the runner-up move gives most of it back &mdash; without losing. So the
      choice is about technique, not about avoiding a blunder.</p>
    </div>
    <div>
      <h3>Using them</h3>
      <p>Show the diagram, ask for a move and a reason, then open the solution. The conversion
      positions also work as training games: set one up and play it out from both sides.
      {searched}</p>
    </div>
  </div>
</header>
{''.join(sections)}
<footer>
  <p>Evaluations are Stockfish&nbsp;18, from the point of view of the side to move, in pawns.
  Every position was re-checked at a much higher search budget before it made this page.</p>
</footer>
</div>
'''

def main(argv: Optional[list[str]] = None) -> None:
    args = parse_args(argv)
    with open(args.hits) as f:
        hits = [json.loads(line) for line in f if line.strip()]
    with open(args.out, 'w') as f:
        f.write(page_html(hits, args))
    print(f"Wrote {args.out} with {len(hits)} exercises.")

if __name__ == '__main__':
    main()
