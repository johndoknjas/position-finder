import berserk

session, client = None, None

def get_api_key():
    with open('api-key.txt') as f:
        return f.readline().strip('\n')

def get_study_pgn(study_id) -> str:
    global session, client
    if not session:
        session = berserk.TokenSession(get_api_key())
        client = berserk.Client(session=session)
    return '\n\n\n'.join(client.studies.export(study_id))
