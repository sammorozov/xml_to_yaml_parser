import re
from collections import Counter
from typing import List
from typing import NamedTuple
from typing import Optional
from typing import Union

import xml_lexer

XmlNode = Union['XmlSection', 'XmlElement']


class XmlParserError(Exception):
    pass


class XmlSection(NamedTuple):
    name: str
    attributes: dict
    parent: Optional['XmlSection']
    inc: List[XmlNode]


class XmlElement(NamedTuple):
    name: str
    value: str
    attributes: dict
    parent: XmlSection


def get_tag_attributes(tag_match: re.Match) -> dict:
    attributes = {}
    attrs_string = tag_match.group('attrs')
    if attrs_string is not None:
        for s in attrs_string.split():
            if not xml_lexer.attribute_re.match(s):
                raise XmlParserError(
                    'Wrong attribute {} in tag {}'.format(
                        s, tag_match.group(2)))
            name, value = s.split('=')
            value = value[1:-1]
            if name not in attributes:
                attributes[name] = value
            else:
                raise XmlParserError(
                    '>=2 attrs with same name in {} tag'.format(
                        tag_match.group(2)))
    return attributes


def __recur_parse(sec: XmlSection, tokens: List[str],
                  p: int = 0, stack=None) -> None:
    if stack is None:
        stack = []

    tag = tokens[p]
    pros_open = xml_lexer.open_tag_re.match(tag)
    if pros_open:
        if p + 2 <= len(tokens) - 1:
            pros_data = xml_lexer.data_re.match(tokens[p + 1])
            pros_close = xml_lexer.close_tag_re.match(tokens[p + 2])
            if pros_data and pros_close \
                    and pros_open.group('name') \
                    == pros_close.group('name'):
                sec.inc.append(
                    XmlElement(pros_open.group('name'),
                               pros_data.group('data'),
                               get_tag_attributes(pros_open),
                               sec))
                p += 3
                __recur_parse(sec, tokens, p, stack)
                return
        if p + 1 <= len(tokens) - 1:
            pros_close = xml_lexer.close_tag_re.match(tokens[p + 1])
            if pros_close and pros_close.group('name') \
                    == pros_open.group('name'):
                sec.inc.append(
                    XmlElement(pros_open.group('name'),
                               '',
                               get_tag_attributes(pros_open),
                               sec))
                p += 2
                __recur_parse(sec, tokens, p, stack)
                return
        stack.append(pros_open.group('name'))
        sec.inc.append(XmlSection(pros_open.group('name'),
                                  get_tag_attributes(pros_open),
                                  sec, []))
        sec = sec.inc[-1]
        p += 1
        __recur_parse(sec, tokens, p, stack)
        return
    pros_self_closed = xml_lexer.self_closed_tag_re.match(tag)
    if pros_self_closed:
        sec.inc.append(
            XmlElement(pros_self_closed.group('name'),
                       '',
                       get_tag_attributes(pros_self_closed),
                       sec))
    pros_close = xml_lexer.close_tag_re.match(tag)
    if pros_close:
        if stack.pop() != pros_close.group('name'):
            raise XmlParserError()
        sec = sec.parent
        if len(stack) == 0:
            return
        p += 1
        __recur_parse(sec, tokens, p, stack)


def __write_attrs_to_yaml(f, attrs: dict, d: int, indent='  ') -> None:
    f.write('{}{}:\n'.format(indent * d, 'attributes'))
    d += 1
    for name in attrs:
        f.write('{}{}: {}\n'.format(indent * d, name,
                                    attrs[name]))


def to_yaml(el: XmlSection, f, d=0, indent='  '):
    ex_name = Counter()
    for i in el.inc:
        name = i.name
        ex_name[name] += 1
        if ex_name[name] != 1:
            name += str(ex_name[i.name] - 1)

        if isinstance(i, XmlElement):
            f.write('{}{}:'.format(indent * d, name))
            if len(i.attributes) != 0:
                f.write('\n')
                d += 1
                __write_attrs_to_yaml(f, i.attributes, d)
                f.write('{}value: {}\n'.format(indent * d, i.value))
            else:
                f.write(' {}\n'.format(i.value))
        elif isinstance(i, XmlSection):
            f.write('{}{}:\n'.format(indent * d, name))
            d += 1
            if len(i.attributes) != 0:
                __write_attrs_to_yaml(f, i.attributes, d)
            to_yaml(i, f, d)
            d -= 1


def parse(f) -> Optional[XmlSection]:
    tokens = xml_lexer.get_tokens(f)
    if not len(tokens):
        return
    start = 0
    decl_match = xml_lexer.decl_re.match(tokens[0])
    if decl_match:
        version = '1.0' or decl_match.group('ver')
        encoding = 'utf-8' or decl_match.group('enc').lower()
        standalone = 'yes' or decl_match.group('stand')
        if version != '1.0' or encoding != 'utf-8' \
                or standalone != 'yes':
            raise XmlParserError(
                'Parse only standalone 1.0 xml in utf-8 encode')
        start = 1
    root_tag = tokens[start]
    root_tag_match = xml_lexer.open_tag_re.match(root_tag)
    if not root_tag_match:
        raise XmlParserError('No open root tag')
    root_attrs = get_tag_attributes(root_tag_match)
    root = XmlSection(root_tag_match.group('name'),
                      root_attrs, None, [])
    __recur_parse(root, tokens, start + 1, [root_tag_match.group('name')])
    return root