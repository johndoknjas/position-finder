def remove_lines_starting_with(multline_str: str, starting_substr: str) -> str:
    as_lst = multline_str.splitlines()
    return '\n'.join(line for line in as_lst if not line.startswith(starting_substr))