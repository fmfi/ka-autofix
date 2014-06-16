#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from __future__ import print_function
from nose.tools import eq_
from rtf import tokenize, GroupBoundary, ControlWord, parse, Document, Group, Text, TokenNode


def test_tokenize():
    eq_(list(tokenize(b'')), [])
    eq_(list(tokenize(b'{}')), [GroupBoundary(opening=True), GroupBoundary(opening=False)])
    eq_(list(tokenize(b'\\rtf1')), [ControlWord(b'rtf', number=1)])
    eq_(list(tokenize(b'\\rtf1\\fs2')), [ControlWord(b'rtf', number=1), ControlWord(b'fs', number=2)])
    eq_(list(tokenize(b'\\rtf1 \\fs2')), [ControlWord(b'rtf', number=1), ControlWord(b'fs', number=2)])


def test_parse_text_combine():
    eq_(parse(tokenize(b'{\\rtf1Hello\u32?world}')), Document(Group([TokenNode(ControlWord(b'rtf', number=1)), Text('Hello world')])))


if __name__ == "__main__":
    import nose
    nose.main()