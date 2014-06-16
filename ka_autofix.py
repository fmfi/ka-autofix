#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import re
from rtf import ByteStream, flatten, parse, tokenize, walk_left, find_text, filter_control_word, node_range, walk_right, \
    as_text, dfs_ltr, document_content, match_control_word, split_by, split_end_by
from enum import Enum

RE_TITULY = r'(?:Bc|Mgr|PhD|Ing)'
RE_SP = r'SP_\d+(?:[.]\d+)*_' + RE_TITULY + r'(?:_' + RE_TITULY + r')*_[a-zA-Z0-9_-]+'
RE_SUBOR = r'[a-zA-Z0-9_.-]+'

PAT_SP_DIR = re.compile('^{}$'.format(RE_SP))
PAT_SP_FORM = re.compile('^2a_{}.rtf$'.format(RE_SP))
PAT_SP_FORM_PERMISSIVE = re.compile(r'.*2a_SP.*rtf$', re.IGNORECASE)
PAT_SUBOR = re.compile(r'^{}$'.format(RE_SUBOR))
PAT_IL_FORM = re.compile('^IL_PREDMETU_{}.rtf$'.format(RE_SUBOR))
PAT_VPCH_FORM = re.compile('^VPCH_{}.rtf$'.format(RE_SUBOR))

class MessageType(Enum):
    error = 1
    warning = 2
    info = 3


class Message:
    def __init__(self, message, path=None, type=MessageType.error):
        self.message = message
        self.path = path
        self.type = type

    def __str__(self):
        ret = '[{}] '.format(self.type.name.upper())
        if self.path:
            ret += '{}: '.format(self.path)
        ret += self.message
        return ret


class Messages:
    def __init__(self):
        self.messages = []

    def add(self, *args, **kwargs):
        self.messages.append(Message(*args, **kwargs))

    def __str__(self):
        return '\n'.join(str(message) for message in self.messages)


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
            return

        if handler:
            handler(path, document)

        print('{}: OK'.format(path), file=sys.stderr)


def check_formular_sp(path, document):
    for row in split_by(document_content(document.root), match_control_word(b'row')):
        for cell in split_end_by(row, match_control_word(b'cell')):
            print(repr(as_text(cell)))
        print()


def process_sp_list_dir(messages, sp_list_dir_path):
    """Spracovava adresare s nazvom 3a_SP_ziadosti"""
    for name in os.listdir(sp_list_dir_path):
        path = os.path.join(sp_list_dir_path, name)
        if not os.path.isdir(path):
            messages.add('nie je adresar', path=path)
            continue
        if not PAT_SP_DIR.match(name):
            messages.add('nevyhovuje formatu nazvu adresara pre studijny program', path=path)
        process_sp_dir(messages, path, nazov_sp=name)


def process_sp_dir(messages, sp_dir_path, nazov_sp=None):
    """Spracovava adresare studijneho programu"""
    pocet_formularov_sp = 0
    pocet_formularov_vpch = 0
    pocet_formularov_il = 0
    for name in os.listdir(sp_dir_path):
        path = os.path.join(sp_dir_path, name)
        if PAT_SP_FORM_PERMISSIVE.match(name):
            process_sp_form(messages, path, nazov_sp=nazov_sp)
            pocet_formularov_sp += 1
        else:
            if PAT_IL_FORM.match(name):
                pocet_formularov_il += 1
            elif PAT_VPCH_FORM.match(name):
                pocet_formularov_vpch += 1
            process_generic_file(messages, path)

    if pocet_formularov_sp == 0:
        messages.add('adresar neobsahuje formular SP', path=sp_dir_path)
    else:
        messages.add('v adresari sa nachadza viac formularov SP', path=sp_dir_path)

    if pocet_formularov_il == 0:
        messages.add('adresar neobsahuje formular IL', path=sp_dir_path)

    if pocet_formularov_vpch == 0:
        messages.add('adresar neobsahuje formular VPCH', path=sp_dir_path)


def process_sp_form(messages, sp_form_path, nazov_sp=None):
    name = os.path.basename(sp_form_path)
    if not PAT_SP_FORM.match(name):
        messages.add('nazov formulara SP nevyhovuje formatu', path=sp_form_path)
    if nazov_sp is not None and name != '2a_{}_formular.rtf':
        messages.add('nazov formulara SP nesuhlasi s nazvom adresara', path=sp_form_path)
    check_rtf(sp_form_path, check_formular_sp)


def process_generic_file(messages, path):
    name = os.path.basename(path)
    if not PAT_SUBOR.match(name):
        messages.add('nazov suboru obsahuje nepovolene znaky', path=path)


def guess_path_type(path):
    path = os.path.abspath(path)
    basename = os.path.basename(path)
    is_dir = os.path.isdir(path)
    is_file = os.path.isfile(path)
    if is_dir and basename == '3a_SP_ziadosti':
        return 'sp_list'
    elif is_dir and PAT_SP_DIR.match(basename):
        return 'sp'
    elif is_file and PAT_SP_FORM_PERMISSIVE.match(basename):
        return 'sp_form'
    return None


def process_path(messages, path, type):
    if type == 'sp_list':
        process_sp_list_dir(messages, path)
    elif type == 'sp':
        process_sp_dir(messages, path)
    elif type == 'sp_form':
        process_sp_form(messages, path)
    else:
        raise ValueError('Unknown path type')


if __name__ == '__main__':
    import sys
    import argparse
    import os
    import os.path
    import magic

    parser = argparse.ArgumentParser()
    parser.add_argument('path')
    parser.add_argument('--type', choices=('sp', 'sp_list', 'sp_form'))
    args = parser.parse_args()

    messages = Messages()
    if args.type is None:
        type = guess_path_type(args.path)
        if type is None:
            sys.stderr.write('Neviem zistit typ cesty {}\n'.format(args.path))
            exit(1)
    else:
        type = args.type
    process_path(messages, args.path, type)
    print(messages)