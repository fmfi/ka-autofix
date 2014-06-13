#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from rtf import ByteStream, flatten, parse, tokenize, walk_left, find_text, filter_control_word, node_range, walk_right, \
    as_text, dfs_ltr, document_content, match_control_word, split_by, split_end_by


def print_iterator(iterator):
    for item in iterator:
        print(item)
        yield item


def check_rtf(path, handler=None):
    with open(path, 'rb') as f:
        mimetype = magic.from_buffer(f.read(1024), mime=True)
        if mimetype not in (b'text/rtf', b'application/rtf'):
            print('{}: Nie je RTF, ale {}'.format(path, mimetype), file=sys.stderr)
            return
        f.seek(0)
        bs = ByteStream(f)
        try:
            document = parse(tokenize(bs), encoding='cp1250')
        except:
            print('{}: Chyba pri parsovani na pozicii {}\n'.format(path, bs.pos), file=sys.stderr)

        if handler:
            handler(path, document)

        print('{}: OK'.format(path), file=sys.stderr)


def check_formular_sp(path, document):
    for row in split_by(document_content(document.root), match_control_word(b'row')):
        for cell in split_end_by(row, match_control_word(b'cell')):
            print(repr(as_text(cell)))
        print()



if __name__ == '__main__':
    import sys
    import argparse
    import os
    import os.path
    import magic

    parser = argparse.ArgumentParser()
    parser.add_argument('path')
    args = parser.parse_args()

    if os.path.isdir(args.path):
        for root, dirs, files in os.walk(args.path):
            for file in files:
                if file.endswith('.rtf'):
                    path = os.path.join(root, file)
                    check_rtf(path)
    elif os.path.isfile(args.path):
        if args.path.endswith('.rtf'):
            check_rtf(args.path, check_formular_sp)
    else:
        raise ValueError('Musi byt subor alebo adresar')