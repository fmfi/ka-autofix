#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import re
from copy import copy
from collections import deque


class Error(Exception):
    pass


class ParseError(Error):
    def __init__(self, position, description):
        self.position = position
        self.description = description

    def __str__(self):
        return 'Parse error at position {}: {}'.format(self.position, self.description)


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

    def __repr__(self):
        return 'ControlWord({!r}, number={!r}, trailing={!r}, pos={!r})'.format(self.word, self.number,
                                                                                self.trailing, self.pos)


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

    def __repr__(self):
        return 'ControlSymbol({!r}, pos={!r})'.format(self.symbol, self.pos)


class Separator(Token):
    def __init__(self, bytes, pos=None):
        super().__init__(pos=pos)
        self.bytes = bytes

    def __bytes__(self):
        return self.bytes

    def __repr__(self):
        return 'Separator({!r}, pos={!r})'.format(self.bytes, self.pos)


class Char(Token):
    def __init__(self, ordinal, pos=None):
        super().__init__(pos=pos)
        self.ordinal = ordinal

    def __repr__(self):
        return '{}({!r}, pos={!r})'.format(self.__class__.__name__, self.ordinal, self.pos)


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

    def __ne__(self, other):
        return not (self == other)


def tokenize(bs):
    if not isinstance(bs, ByteStream):
        bs = ByteStream(bs)
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
                        raise ParseError(bs.pos, 'Too long control word')
                number = None
                if bs.peek() == b' ':
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
                        raise ParseError(loop_pos, 'Negative \\bin')
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
            sep = bs.get()
            if (b == b'\r' and bs.peek() == b'\n') or (b == b'\n' and bs.peek() == b'\r'):
                sep += bs.get()
            yield Separator(sep, pos=loop_pos)
        else:
            yield RawChar(ord(bs.get().decode('ascii')), pos=loop_pos)


class Node:
    def __init__(self, parent=None):
        self.parent = parent

    def walk(self):
        yield self


class Text(Node):
    def __init__(self, text, tokens=None, parent=None):
        super().__init__(parent=parent)
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

    def __repr__(self):
        return 'Text({!r}, tokens={!r})'.format(self._text, self.tokens)


class Group(Node):
    def __init__(self, pos=None, parent=None):
        super().__init__(parent=parent)
        self.content = []
        self.pos = pos

    def __bytes__(self):
        return b'{' + b''.join(bytes(x) for x in self.content) + b'}'

    def walk(self):
        yield self
        for child in self.content:
            for node in child.walk():
                yield node

    def append(self, node):
        if node.parent is not None:
            raise ValueError('A node can only be inserted once')
        node.parent = self
        self.content.append(node)


class TokenNode(Node):
    def __init__(self, token, parent=None):
        super().__init__(parent=parent)
        self.token = token

    def __repr__(self):
        return 'TokenNode({!r})'.format(self.token)


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


class Document(Node):
    def __init__(self, root, trailing=None):
        super().__init__(parent=None)
        self.root = root
        self.trailing = trailing

    def walk(self):
        return self.root.walk()


def parse(tokens, encoding=None):
    tokens = PeekIter(tokens)
    effective_encoding = 'ascii' if encoding is None else encoding

    def set_encoding(name):
        nonlocal effective_encoding
        if encoding is None:
            effective_encoding = name

    open_brace = next(tokens)
    if open_brace != GroupBoundary(opening=True):
        raise ParseError(open_brace.pos, 'Expecting {')
    root = Group(open_brace.pos)

    stack = [Scope(root)]

    def combine_text(text, tokens):
        if stack[-1].group.content and isinstance(stack[-1].group.content[-1], Text):
            text_node = stack[-1].group.content[-1]
        else:
            text_node = Text('', [])
            stack[-1].group.append(text_node)
        text_node.append(text, tokens)

    for token in tokens:
        if token == GroupBoundary(opening=True):
            new_scope = copy(stack[-1])
            new_scope.group = Group(token.pos)
            stack[-1].group.append(new_scope.group)
            stack.append(new_scope)
        elif token == GroupBoundary(opening=False):
            stack.pop()
            if len(stack) == 0:
                break
        elif isinstance(token, Char):
            try:
                decoded_text = bytes([token.ordinal]).decode(effective_encoding)
            except UnicodeDecodeError:
                stack[-1].group.append(TokenNode(token))
            else:
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
                    raise ParseError(token.pos, '\\uc requires argument')
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
            stack[-1].group.append(TokenNode(token))
        else:
            stack[-1].group.append(TokenNode(token))

    trailing = []
    for token in tokens:
        if isinstance(token, Separator):
            trailing.append(token)
            continue
        raise ParseError(token.pos, 'Unexpected trailing token {!r}'.format(token))

    return Document(root, trailing=trailing)


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
    elif isinstance(node, Document):
        for token in flatten(node.root):
            yield token
        if node.trailing:
            for token in node.trailing:
                yield token


def find_text(root, text):
    for node in root.walk():
        if isinstance(node, Text):
            if text in node.text:
                yield node


def find_re(root, pattern):
    if isinstance(pattern, str):
        pattern = re.compile(pattern)
    for node in root.walk():
        if isinstance(node, Text):
            m = pattern.match(node.text)
            if m:
                yield node, m


def dfs_rtl(node, include_root=True):
    if include_root:
        yield node
    if isinstance(node, Group):
        for child in reversed(node.content):
            for child_node in dfs_rtl(child, include_root=True):
                yield child_node


def dfs_ltr(node, include_root=True):
    if include_root:
        yield node
    if isinstance(node, Group):
        for child in node.content:
            for child_node in dfs_ltr(child, include_root=True):
                yield child_node


def walk_left(node):
    """Generates nodes towards beginning of the document, starting before node"""
    if node.parent is None or not isinstance(node.parent, Group):
        return

    # Find the current node's position
    for index, index_node in enumerate(node.parent.content):
        if index_node is node:
            current_index = index
            break
    else:
        raise AssertionError('A node was not found within its parent')

    current_index -= 1
    while current_index >= 0:
        for other_node in dfs_rtl(node.parent.content[current_index]):
            yield other_node
        current_index -= 1

    yield node.parent

    for other_node in walk_left(node.parent):
        yield other_node


def walk_right(node):
    """Generates nodes towards end of the document, starting after node"""
    if node.parent is None or not isinstance(node.parent, Group):
        return

    # Find the current node's position
    for index, index_node in enumerate(node.parent.content):
        if index_node is node:
            current_index = index
            break
    else:
        raise AssertionError('A node was not found within its parent')

    current_index += 1
    while current_index < len(node.parent.content):
        for other_node in dfs_ltr(node.parent.content[current_index]):
            yield other_node
        current_index += 1

    yield node.parent

    for other_node in walk_right(node.parent):
        yield other_node

def filter_control_word(nodes, name):
    for node in nodes:
        if isinstance(node, TokenNode) and isinstance(node.token, ControlWord):
            if node.token.word == name:
                yield node


def node_range(start_node, end_node):
    for node in walk_right(start_node):
        if node is end_node:
            return
        yield node


def as_text(nodes):
    ret = ''
    for node in nodes:
        if isinstance(node, Text):
            ret += node.text
    return ret

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