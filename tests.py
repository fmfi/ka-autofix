#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from rtf import tokenize, GroupBoundary, ControlWord


def test_tokenize():
    assert list(tokenize(b'')) == []
    assert list(tokenize(b'{}')) == [GroupBoundary(opening=True), GroupBoundary(opening=False)]
    print(repr(list(tokenize(b'\\rtf1'))))
    assert list(tokenize(b'\\rtf1')) == [ControlWord(b'rtf', number=1)]
    assert list(tokenize(b'\\rtf1\\fs2')) == [ControlWord(b'rtf', number=1), ControlWord(b'fs', number=2)]
    assert list(tokenize(b'\\rtf1 \\fs2')) == [ControlWord(b'rtf', number=1), ControlWord(b'fs', number=2)]


if __name__ == "__main__":
  import nose
  nose.main()