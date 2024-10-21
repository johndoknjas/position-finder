from __future__ import annotations
import requests

def get_api_key() -> str:
    with open('api-key.txt') as f:
        return f.readline().strip('\n')

def get_study_pgn(study_id) -> str:
    return requests.get(
        f'https://lichess.org/api/study/{study_id}.pgn?source=true',
        headers={"Authorization": f"Bearer {get_api_key()}"}
    ).text
