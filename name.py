import sys
import main

def do_name_feature():
    main.main(['name'] + sys.argv[1:])

if __name__ == '__main__':
    do_name_feature()