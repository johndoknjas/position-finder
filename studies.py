from __future__ import annotations
import requests

def get_api_key() -> str:
    with open('api-key.txt') as f:
        return f.readline().strip('\n')

def get_study_pgn(study_id) -> str:
    local_response = requests.get(
        f'http://localhost:9663/api/study/{study_id}.pgn?source=true'
    )
    if local_response.status_code == 200:
        return local_response.text
    remote_response = requests.get(
        f'https://lichess.org/api/study/{study_id}.pgn?source=true',
        headers={"Authorization": f"Bearer {get_api_key()}"}
    )
    if remote_response.status_code == 200:
        return remote_response.text
    raise RuntimeError(f"lichess api response status code is {remote_response.status_code}")
