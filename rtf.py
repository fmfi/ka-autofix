#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from copy import copy
from collections import deque
from itertools import chain


class PeekIter:
    def __init__(self, iterator):
        self._iterator = iterator
        self._buf = deque()

    def __iter__(self):
        return self

    def __next__(self):
        if self._buf:
            return self._buf.popleft()
        return next(self._iterator)

    def peek(self, index=0):
        while len(self._buf) <= index:
            try:
                self._buf.append(next(self._iterator))
            except StopIteration:
                return None
        return self._buf[index]


class ByteStream:
    def __init__(self, file):
        self._file = file
        self._buf = b''
        self.pos = 0

    def _readbuf(self):
        if len(self._buf) == 0:
            self._buf += self._file.read(1024)

    def get(self):
        self._readbuf()
        if len(self._buf) == 0:
            return b''
        ret = self._buf[0:1]
        self._buf = self._buf[1:]
        self.pos += 1
        return ret

    def peek(self):
        self._readbuf()
        if len(self._buf) == 0:
            return b''
        return self._buf[0:1]


class Token:
    def __init__(self, pos=None):
        self.pos = pos


class ControlWord(Token):
    def __init__(self, word, number=None, pos=None, trailing=None):
        super().__init__(pos=pos)
        self.word = word
        self.number = number
        if trailing is None:
            self.trailing = b''
        else:
            self.trailing = trailing

    def __bytes__(self):
        ret = b'\\' + self.word
        if self.number is not None:
            ret += str(self.number).encode('ascii')
        ret += self.trailing
        return ret


class BinaryData(Token):
    def __init__(self, data, pos=None, trailing=None):
        self.data = data
        if trailing is None:
            self.trailing = b''
        else:
            self.trailing = trailing

    def __bytes__(self):
        ret = b'\\bin'
        ret += str(len(self.data)).encode('ascii')
        ret += self.trailing
        ret += self.data
        return ret

class ControlSymbol(Token):
    def __init__(self, symbol, pos=None):
        super().__init__(pos=pos)
        self.symbol = symbol

    def __bytes__(self):
        return b'\\' + self.symbol


class Separator(Token):
    def __init__(self, bytes, pos=None):
        super().__init__(pos=pos)
        self.bytes = bytes

    def __bytes__(self):
        return self.bytes


class Char(Token):
    def __init__(self, ordinal, pos=None):
        super().__init__(pos=pos)
        self.ordinal = ordinal


class RawChar(Char):
    def __bytes__(self):
        return chr(self.ordinal).encode('ascii')


class ANSIEscapedChar(Char):
    def __bytes__(self):
        return b'\\\'' + hex(self.ordinal)[2:].zfill(2).encode('ascii')


class GroupBoundary(Token):
    def __init__(self, opening=True, pos=None):
        super().__init__(pos=pos)
        self.opening = opening

    def __bytes__(self):
        if self.opening:
            return b'{'
        else:
            return b'}'

    def __eq__(self, other):
        return isinstance(other, GroupBoundary) and self.opening == other.opening


def tokenize(bs):
    while True:
        b = bs.peek()
        loop_pos = bs.pos
        if b == b'':
            return
        elif b == b'{':
            bs.get()
            yield GroupBoundary(opening=True, pos=loop_pos)
        elif b == b'}':
            bs.get()
            yield GroupBoundary(opening=False, pos=loop_pos)
        elif b == b'\\':
            bs.get()
            if b'a' <= bs.peek() <= b'z' or b'A' <= bs.peek() <= b'Z':
                # control word
                num = 0
                word = b''
                trailing = b''
                while b'a' <= bs.peek() <= b'z' or b'A' <= bs.peek() <= b'Z':
                    word += bs.get()
                    num += 1
                    if num > 32:
                        raise ValueError('Too long control word')
                number = None
                if bs.peek() == ' ':
                    trailing = bs.get()
                elif b'0' <= bs.peek() <= b'9' or bs.peek() == b'-':
                    number = bs.get()
                    while b'0' <= bs.peek() <= b'9':
                        number += bs.get()
                    if bs.peek() == b' ':
                        trailing = bs.get()
                    number = int(number.decode('ascii'))
                if word == b'bin':
                    if number < 0:
                        raise ValueError('Negative \\bin')
                    skip = number
                    data = b''
                    while skip > 0:
                        data += bs.get()
                    yield BinaryData(data, pos=loop_pos, trailing=trailing)
                else:
                    yield ControlWord(word, number=number, pos=loop_pos, trailing=trailing)
            elif bs.peek() == b'\'':
                bs.get()
                ordval = int(bs.get() + bs.get(), 16)
                yield ANSIEscapedChar(ordval)
            else:
                yield ControlSymbol(bs.get(), pos=loop_pos)
        elif b == b'\r' or b == b'\n':
            yield Separator(bs.get(), pos=loop_pos)
        else:
            yield RawChar(ord(bs.get().decode('ascii')), pos=loop_pos)


class Node:
    pass


class Text(Node):
    def __init__(self, text, tokens=None):
        self.tokens = tokens
        self._text = text

    @property
    def text(self):
        return self._text

    @text.setter
    def text(self, text):
        if text != self._text:
            self._text = text
            self.tokens = None

    def append(self, text, tokens):
        self._text += text
        self.tokens.extend(tokens)


class Group(Node):
    def __init__(self, pos=None):
        self.content = []
        self.pos = pos

    def __bytes__(self):
        return b'{' + b''.join(bytes(x) for x in self.content) + b'}'


class TokenNode(Node):
    def __init__(self, token):
        self.token = token


def parse_group(tokens):
    open_brace = next(tokens)
    if open_brace != GroupBoundary(opening=True):
        raise ValueError('Expecting {')
    group = Group(open_brace.pos)
    while True:
        try:
            token = next(tokens)
        except StopIteration:
            raise ValueError('Premature EOF')

        if token == GroupBoundary(opening=True):
            group.content.append(parse_group(chain([token], tokens)))
        elif token == GroupBoundary(opening=False):
            return group
        else:
            group.content.append(token)


class Scope:
    def __init__(self, group):
        self.group = group
        self.unicode_skip = 1


RTF_ENCODINGS = {
    10000: 'mac_roman',
    10001: 'mac_japan',
    10005: 'mac_greek',
    10007: 'mac_cyrillic',
    10029: 'mac_latin2',
    10081: 'mac_turkish'
}


def parse(tokens, encoding=None):
    tokens = PeekIter(tokens)
    effective_encoding = 'ascii' if encoding is None else encoding

    def set_encoding(name):
        nonlocal effective_encoding
        if encoding is None:
            effective_encoding = name

    open_brace = next(tokens)
    if open_brace != GroupBoundary(opening=True):
        raise ValueError('Expecting {')
    root = Group(open_brace.pos)

    stack = [Scope(root)]

    def combine_text(text, tokens):
        if stack[-1].group.content and isinstance(stack[-1].group.content[-1], Text):
            text_node = stack[-1].group.content[-1]
        else:
            text_node = Text('', [])
            stack[-1].group.content.append(text_node)
        text_node.append(text, tokens)

    for token in tokens:
        if token == GroupBoundary(opening=True):
            new_scope = copy(stack[-1])
            new_scope.group = Group(token.pos)
            stack[-1].group.content.append(new_scope.group)
            stack.append(new_scope)
        elif token == GroupBoundary(opening=False):
            stack.pop()
            if len(stack) == 0:
                break
        elif isinstance(token, Char):
            decoded_text = bytes([token.ordinal]).decode(effective_encoding)
            combine_text(decoded_text, [token])
        elif isinstance(token, ControlWord):
            if token.word == b'u':  # unicode text
                ordinal = token.number
                if ordinal < 0:
                    ordinal += 65536
                skipped_tokens = [token]
                for i in range(stack[-1].unicode_skip):
                    to_skip = tokens.peek()
                    if isinstance(to_skip, GroupBoundary):
                        break
                    skipped_tokens.append(next(tokens))
                combine_text(chr(ordinal), skipped_tokens)
                continue
            elif token.word == b'uc':
                if token.number is None:
                    raise ValueError('\\uc requires argument')
                stack[-1].unicode_skip = token.number
            elif token.word == b'ansi':
                set_encoding('ascii')
            elif token.word == b'pc':
                set_encoding('cp437')
            elif token.word == b'pca':
                set_encoding('cp850')
            elif token.word == b'ansicpg':
                if token.number in RTF_ENCODINGS:
                    set_encoding(RTF_ENCODINGS[token.number])
                else:
                    set_encoding('cp{}'.format(token.number))
            stack[-1].group.content.append(TokenNode(token))
        else:
            stack[-1].group.content.append(TokenNode(token))

    try:
        token = next(tokens)
    except StopIteration:
        return root
    else:
        raise ValueError('Unexpected trailing token {!r}'.format(token))


def escape_text_tokens(text, encoding=None):
    prevc = None
    for c in text:
        if (c == '\n' and prevc != '\r') or (c == '\r' and prevc != '\n'):
            yield ControlWord(b'line')
        elif (c == '\n' and prevc == '\r') or (c == '\r' and prevc == '\n'):
            pass
        elif c in '\\{}':
            yield ControlSymbol(c.encode('ascii'))
        elif c in 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789 :;@/()_-?.,"\'=&%+[]*':
            yield RawChar(c.encode('ascii'))
        else:
            encoded = False
            if encoding:
                try:
                    yield ANSIEscapedChar(c.encode(encoding)[0])
                    encoded = True
                except UnicodeEncodeError:
                    pass
            if not encoded:
                ordinal = ord(c)
                if ordinal > 32768:
                    ordinal -= 65536
                yield ControlWord(b'u', number=ordinal)
                yield RawChar(b'?')
        prevc = c


def escape_text(text, encoding=None):
    return b''.join(bytes(x) for x in escape_text_tokens(text, encoding=encoding))


def flatten(node, encoding=None):
    if isinstance(node, Group):
        yield GroupBoundary(opening=True)
        for child in node.content:
            for token in flatten(child):
                yield token
        yield GroupBoundary(opening=False)
    elif isinstance(node, TokenNode):
        yield node.token
    elif isinstance(node, Text):
        tokens = node.tokens
        if tokens is None:
            tokens = escape_text_tokens(node.text, encoding=encoding)
        for token in tokens:
            yield token


if __name__ == '__main__':
    import sys
    import argparse

    parser = argparse.ArgumentParser()
    args = parser.parse_args()

    bs = ByteStream(sys.stdin.buffer)
    try:
        for token in flatten(parse(tokenize(bs), encoding='cp1250')):
            sys.stdout.buffer.write(bytes(token))
    except:
        sys.stderr.write('Current position: {}\n'.format(bs.pos))
        raise