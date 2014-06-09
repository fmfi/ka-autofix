#!/usr/bin/env python3
# -*- coding: utf-8 -*-


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


class ControlWord:
    def __init__(self, word, number=None, data=None, pos=None, trailing=None):
        self.word = word
        self.number = number
        self.data = data
        self.pos = pos
        if trailing is None:
            self.trailing = b''
        else:
            self.trailing = trailing

    def __bytes__(self):
        ret = b'\\' + self.word
        if self.number is not None:
            ret += str(self.number).encode('ascii')
        if self.data is not None:
            ret += self.trailing
            ret += self.data
        else:
            ret += self.trailing
        return ret


class ControlSymbol:
    def __init__(self, symbol, pos=None):
        self.symbol = symbol
        self.pos = pos

    def __bytes__(self):
        return b'\\' + self.symbol


class Text:
    def __init__(self, text, pos=None):
        self.text = text
        self.pos = pos

    def __bytes__(self):
        r = b''
        prevc = None
        for c in self.text:
            if (c == '\n' and prevc != '\r') or (c == '\r' and prevc != '\n'):
                r += b'\line '
            elif (c == '\n' and prevc == '\r') or (c == '\r' and prevc == '\n'):
                pass
            elif c in 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789 :;@/()_-?.,"\'=&%+[]*':
                r += c.encode('ascii')
            else:
                r += r'\u{}?'.format(ord(c)).encode('ascii')
            prevc = c
        return r


class Separator:
    def __init__(self, bytes):
        self.bytes = bytes

    def __bytes__(self):
        return self.bytes


class Group:
    def __init__(self, pos=None):
        self.content = []
        self.pos = pos

    def __bytes__(self):
        return b'{' + b''.join(bytes(x) for x in self.content) + b'}'


def rtf_parse(bs):
    startpos = bs.pos
    open_brace = bs.get()
    if open_brace != b'{':
        raise ValueError('Expecting {')
    group = Group(startpos)
    while True:
        b = bs.peek()
        loop_pos = bs.pos
        if b == b'':
            raise ValueError('Premature EOF')
        elif b == b'{':
            group.content.append(rtf_parse(bs))
        elif b == b'}':
            bs.get()
            return group
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
                data = None
                if word == b'bin':
                    if number < 0:
                        raise ValueError('Negative \\bin')
                    skip = number
                    data = b''
                    while skip > 0:
                        data += bs.get()
                group.content.append(ControlWord(word, number=number, data=data, pos=loop_pos, trailing=trailing))
            else:
                group.content.append(ControlSymbol(bs.get(), pos=loop_pos))
        elif b == b'\r' or b == b'\n':
            group.content.append(Separator(bs.get()))
        else:
            text = ''
            while bs.peek() != b'\r' and bs.peek() != b'\n' and bs.peek() != b'\\' and bs.peek() != b'' and bs.peek() != b'{' and bs.peek() != b'}':
                text += bs.get().decode('ascii')
            group.content.append(Text(text, pos=loop_pos))


if __name__ == '__main__':
    import sys
    import argparse

    parser = argparse.ArgumentParser()
    args = parser.parse_args()

    bs = ByteStream(sys.stdin.buffer)
    try:
        sys.stdout.buffer.write(bytes(rtf_parse(bs)))
    except:
        sys.stderr.write('Current position: {}\n'.format(bs.pos))
        raise