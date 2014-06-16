#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import itertools
import re
from rtf import ByteStream, flatten, parse, tokenize, walk_left, find_text, filter_control_word, node_range, walk_right, \
    as_text, dfs_ltr, document_content, match_control_word, split_by, split_end_by, Group, TokenNode, ControlWord, \
    Separator
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


def check_rtf(messages, path, handler=None):
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
            handler(messages, path, document)

        print('{}: OK'.format(path), file=sys.stderr)


header_cwords = {'rtf', 'adeflang', 'ansi', 'ansicpg', 'adeff', 'deff', 'uc', 'stshfdbch', 'stshfloch',
                'stshfhich', 'stshfbi', 'deflang', 'deflangfe', 'themelang', 'themelangfe', 'themelangcs',
                'noqfpromote', 'paperw', 'paperh', 'margl', 'margr', 'margt', 'margb', 'gutter', 'ltrsect',
                'deftab', 'widowctrl', 'ftnbj', 'aenddoc', 'hyphhotz', 'trackmoves', 'trackformatting',
                'donotembedsysfont', 'relyonvml', 'donotembedlingdata', 'grfdocevents', 'validatexml',
                'showplaceholdtext', 'ignoremixedcontent', 'saveinvalidxml', 'showxmlerrors', 'noxlattoyen',
                'expshrtn', 'noultrlspc', 'dntblnsbdb', 'nospaceforul', 'formshade', 'horzdoc', 'dgmargin',
                'dghspace', 'dgvspace', 'dghorigin', 'dgvorigin', 'dghshow', 'dgvshow', 'jexpand', 'viewkind',
                'viewscale', 'pgbrdrhead', 'pgbrdrfoot', 'splytwnine', 'ftnlytwnine', 'htmautsp',
                'nolnhtadjtbl', 'useltbaln', 'alntblind', 'lytcalctblwd', 'lyttblrtgr', 'lnbrkrule',
                'nobrkwrptbl', 'snaptogridincell', 'allowfieldendsel', 'wrppunct', 'asianbrkrule', 'rsidroot',
                'newtblstyruls', 'nogrowautofit', 'usenormstyforlist', 'noindnmbrts', 'felnbrelev',
                'nocxsptable', 'indrlsweleven', 'noafcnsttbl', 'afelev', 'utinl', 'hwelev', 'spltpgpar',
                'notcvasp', 'notbrkcnstfrctbl', 'notvatxbx', 'krnprsnet', 'cachedcolbal', 'nouicompat', 'fet'}

ignored_destinations = {'fonttbl', 'colortbl', 'defchp', 'defpap', 'stylesheet', 'listtable', 'listoverridetable',
                      'rsidtbl', 'mmathPr', 'info', 'xmlnstbl', 'themedata', 'header', 'headerl', 'headerr',
                      'headerf', 'footer', 'footerl', 'footerr', 'footerf', 'themedata', 'colorschememapping',
                      'latentstyles', 'datastore'}


def is_ignored_node(x):
    if isinstance(x, Group):
        destination, invisible = x.destination
        if destination is not None:
            return destination.token.word in ignored_destinations
    elif isinstance(x, TokenNode) and isinstance(x.token, ControlWord):
        return x.token.word in ignored_cwords
    elif isinstance(x, TokenNode) and isinstance(x.token, Separator):
        return True
    return False


class UserDataType:
    def __repr__(self):
        return 'UserData'

UserData = UserDataType()


class FormCell:
    def __init__(self, content, section=None):
        self.content = content
        self.section = section

    def __repr__(self):
        return 'FormCell({!r})'.format(self.content)


class FormRow:
    def __init__(self, *content, section=None):
        if section is None and content and isinstance(content[0], str) and content[0]:
            section = content[0].split()[0]
        self.section = section

        def make_cell(x):
            if not isinstance(x, FormCell):
                x = FormCell(x, section=section)
            return x

        self.content = [make_cell(x) for x in content]

    def match(self, rows, index):
        row = rows[index]
        matches = True
        for cell, value in zip(self.content, row):
            if cell.content is not UserData:
                if cell.content != value:
                    matches = False
        if len(self.content) != len(row):
            matches = False
        return matches, 1

    def __repr__(self):
        return 'FormRow({!r})'.format(self.content)


class ItemList:
    def __init__(self, cols=1, section=None, items=None, numbers=True):
        self.items = items
        self.cols = cols
        self.section = section
        self.numbers = numbers

    def match(self, rows, index):
        matches = False
        item_count = 0
        for item in itertools.count(0):
            if len(rows[index + item]) != self.cols + 1:
                break
            if self.numbers and rows[index + item][0] != '{}.'.format(item + 1):
                break
            item_count += 1
            matches = True

        return matches, item_count


struct_formular_sp = (
    FormRow('I. Základné informácie'),
    FormRow('I.1 Vysoká škola', UserData),
    FormRow('I.2 Fakulta', UserData),
    FormRow('I.3 Miesto poskytovania študijného programu', UserData),
    FormRow('I.4 Číslo a názov študijného odboru', UserData, UserData),
    FormRow('I.5 Názov študijného programu', UserData),
    FormRow('I.6 Stupeň vysokoškolského štúdia', UserData),
    FormRow('I.7 Počet kreditov potrebných na riadne skončenie štúdia príslušného  študijného programu', UserData),
    FormRow('I.8 Minimálny počet hodín výučby (len v\xa0zdravotníckych študijných odboroch)', UserData),
    FormRow('I.9 Celkový počet hodín odbornej praxe', UserData),
    FormRow('I.10 Forma štúdia', 'denná', UserData, 'externá', UserData),
    FormRow('', 'Denná forma štúdia', 'Externá forma štúdia'),
    FormRow('I.11 Štandardná dĺžka štúdia', UserData, UserData),
    FormRow('I.12 Platnosť priznaného práva do', UserData, UserData),
    FormRow('I.13 Identifikačný kód študijného programu', UserData, UserData),
    FormRow('I.14 Jazyk, v\xa0ktorom sa má študijný program uskutočňovať', UserData, UserData),
    FormRow('I.15 Udeľovaný akademický titul', UserData),
    FormRow(FormCell('I.16 Profesijne orientovaný študijný program', section='I.16'), FormCell(UserData, section='I.16'),
            FormCell('I.17 Spoločný študijný program', section='I.17'), FormCell(UserData, section='I.17')),
    FormRow('I.18 Typ žiadosti', UserData),
    FormRow('II. Podklady na vyhodnotenie plnenia jednotlivých kritérií akreditácie'),
    FormRow('Úroveň výskumnej činnosti alebo umeleckej činnosti'),
    FormRow('Podklady na\xa0vyhodnotenie plnenia kritéria KSP-A1'),
    FormRow('II.1 Výsledok hodnotenia výskumnej činnosti alebo umeleckej činnosti, do ktorej patrí študijný odbor ', UserData),
    FormRow('II.2 Najvýznamnejšie publikované vedecké práce alebo umelecké práce v\xa0príslušnom študijnom odbore s\xa0uvedením kategórie výstupu. Maximálne päť výstupov.'),
    ItemList(items=5, section='II.2'),
    FormRow('II.3 Najvýznamnejšie publikované vedecké práce alebo umelecké práce za posledných šesť rokov v\xa0príslušnom študijnom odbore s\xa0uvedením kategórie výstupu. Maximálne päť výstupov.'),
    ItemList(items=5, section='II.3'),
    FormRow('II.4 Najvýznamnejšie získané a\xa0úspešne riešené výskumné projekty za posledných  šesť rokov v príslušnom študijnom odbore s\xa0vyznačením medzinárodných projektov. Maximálne\xa0päť projektov.'),
    ItemList(items=5, section='II.4'),
    FormRow('II.5 Výstupy v príslušnom študijnom odbore s\xa0najvýznamnejšími ohlasmi a\xa0prehľad ohlasov na tieto výstupy. Maximálne päť výstupov a desať najvýznamnejších ohlasov na jeden výstup.'),
    ItemList(items=5, section='II.5'),
    FormRow('II.6 Najvýznamnejšie uznanie vedeckých výstupov alebo umeleckých výstupov v\xa0študijnom odbore, v\xa0ktorom sa uskutočňuje študijný program.'),
    FormRow(UserData, section='II.6'),
    FormRow('II. 7 Komentár vysokej školy k\xa0plneniu kritéria'),
    FormRow(UserData, section='II.7'),
    FormRow('Priestorové, materiálne, technické a\xa0informačné zabezpečenie študijného programu', section='II'),
    FormRow('Podklady na\xa0vyhodnotenie plnenia kritéria KSP-A2', section='II'),
    FormRow('II.8 Spôsob zabezpečenia knižničných služieb v\xa0mieste uskutočňovania študijného programu'),
    FormRow(UserData, section='II.8'),
    FormRow('II.9 Informácie o\xa0materiálnom a\xa0technickom zabezpečení študijného programu'),
    FormRow(UserData, section='II.9'),
    FormRow('II.10 Informácie o\xa0priestorovom zabezpečení študijného programu'),
    FormRow(UserData, section='II.10'),
    FormRow('II.11 Informácie o\xa0informačnom zabezpečení študijného programu'),
    FormRow(UserData, section='II.11'),
    FormRow('II.12 Komentár vysokej školy k\xa0plneniu kritéria'),
    FormRow(UserData, section='II.12'),
    FormRow('Personálne zabezpečenie'),
    FormRow('Podklady na vyhodnotenie plnenia kritéria KSP-A3'),
    FormRow('II.13 Dátum, ku ktorému sú údaje platné', UserData),
    FormRow('II.14 Počet a\xa0štruktúra osôb, ktoré majú zabezpečovať študijný program'),
    FormRow('Funkcia alebo zaradenie fyzickej osoby', 'Fyzický počet', 'Prepočítaný počet', 'Z toho na ustanovený týždenný pracovný čas', section='II.14'),
    FormRow('', '', 'Z toho mimoriadnych', '', 'Z toho mimoriadnych', '', section='II.14'),
    FormRow('Profesor r1', UserData, UserData, UserData, UserData, UserData, section='II.14 r1'),
    FormRow('Docent r2', UserData, UserData, UserData, UserData, UserData, section='II.14 r2'),
    FormRow('', '', 'Z toho s\xa0vysokoškolským vzdelaním tretieho stupňa', '', 'Z toho s\xa0vysokoškolským vzdelaním tretieho stupňa', '', section='II.14'),
    FormRow('Hosťujúci profesor r3', UserData, UserData, UserData, UserData, UserData, section='II.14 r3'),
    FormRow('Odborný asistent r4', UserData, UserData, UserData, UserData, UserData, section='II.14 r4'),
    FormRow('Asistent r5', UserData, UserData, UserData, UserData, UserData, section='II.14 r5'),
    FormRow('Lektor r6', UserData, UserData, UserData, UserData, UserData, section='II.14 r6'),
    FormRow('Vysokoškolskí učitelia spolu r7=r1+r2+r3+r4+r5+r6', UserData, UserData, UserData, UserData, UserData, section='II.14 r7'),
    FormRow('Výskumný pracovník r8', UserData, UserData, UserData, UserData, UserData, section='II.14 r8'),
    FormRow('Zamestnanci v\xa0pracovnom pomere spolu r9=r7+r8', UserData, UserData, UserData, UserData, UserData, section='II.14 r9'),
    FormRow('Denný doktorand r10', UserData, UserData, UserData, UserData, UserData, section='II.14 r10'),
    FormRow('Zamestnanci, mimo pracovného pomeru r11', UserData, UserData, UserData, UserData, UserData, section='II.14 r11'),
    FormRow('Spolu r12=r9+r10+r11', UserData, UserData, UserData, UserData, UserData, section='II.14 r12'),
    FormRow('II.15 Počet študentov študijného programu',
            'v dennej forme štúdia:', 'v externej forme štúdia:', 'spolu:'),
    FormRow('II.16 Pomer počtu študentov študijného programu a\xa0prepočítaného počtu zamestnancov s\xa0vysokoškolským vzdelaním  tretieho stupňa',
            'v dennej forme štúdia:', 'v externej forme štúdia:', 'spolu:'),
    FormRow('II.17 Zoznam všetkých fyzických osôb, ktoré zabezpečujú povinné a\xa0povinne voliteľné predmety študijného programu'),
    FormRow('Názov predmetu', 'Priezvisko a meno', 'Funkcia', 'Kvalifikácia', 'Pracovný úväzok', 'Typ vzdelávacej činnosti', 'Jadro ŠOáno/nie', section='II.17'),
    ItemList(cols=7, section='II.17'),
    FormRow('II.18 Minimálna podmienka personálneho zabezpečenia študijného programu'),
    FormRow('Prvý profesor alebo docent', section='II.18'),
    FormRow('Priezvisko a meno', UserData, 'Tituly', UserData, section='II.18'),
    FormRow('Študijný odbor (funkcia)', UserData, section='II.18'),
    FormRow('Študijný odbor (titul profesor)', UserData, 'Rok udelenia', UserData, section='II.18'),
    FormRow('Študijný odbor (titul docent)', UserData, 'Rok udelenia', UserData, section='II.18'),
    FormRow('Veľkosť pracovného úväzku', UserData, '', section='II.18'),
    FormRow('Pôsobenie v\xa0tejto pozícii v\xa0ďalších študijných programoch', UserData, section='II.18'),
    FormRow('', section='II.18'),
    FormRow('Druhý profesor alebo docent', section='II.18'),
    FormRow('Priezvisko a meno', UserData, 'Tituly', UserData, section='II.18'),
    FormRow('Študijný odbor (funkcia)', UserData, section='II.18'),
    FormRow('Študijný odbor (titul profesor)', UserData, 'Rok udelenia', UserData, section='II.18'),
    FormRow('Študijný odbor (titul docent)', UserData, 'Rok udelenia', UserData, section='II.18'),
    FormRow('Veľkosť pracovného úväzku', UserData, '', section='II.18'),
    FormRow('Pôsobenie v\xa0tejto pozícii v\xa0ďalších študijných programoch', UserData, section='II.18'),
    FormRow('', section='II.18'),
    FormRow('Tretí profesor alebo docent', section='II.18'),
    FormRow('Priezvisko a meno', UserData, 'Tituly', UserData, section='II.18'),
    FormRow('Študijný odbor (funkcia)', UserData, section='II.18'),
    FormRow('Študijný odbor (titul profesor)', UserData, 'Rok udelenia', UserData, section='II.18'),
    FormRow('Študijný odbor (titul docent)', UserData, 'Rok udelenia', UserData, section='II.18'),
    FormRow('Veľkosť pracovného úväzku', UserData, '', section='II.18'),
    FormRow('Pôsobenie v\xa0tejto pozícii v\xa0ďalších študijných programoch', UserData, section='II.18'),
    FormRow('', section='II'),
    FormRow('II.19 Komentár vysokej školy k\xa0plneniu kritéria'),
    FormRow(UserData, section='II.19'),
    FormRow('Podklady na vyhodnotenie plnenia kritéria KSP-A4', section='II'),
    FormRow('II.20 Počet záverečných prác v\xa0študijnom programe za akademický rok', UserData, 'Počet', UserData),
    FormRow('II.21 Počet vedúcich záverečných prác v\xa0študijnom programe', UserData),
    FormRow('II.22 Celkový počet záverečných prác vedených vedúcimi záverečných prác v II.21', UserData),
    FormRow('II.23 Zoznam vedúcich záverečných prác/školiteľov doktorandov'),
    FormRow(' Priezvisko a meno', 'Kvalifikácia', 'Odborník z\xa0praxeáno/nie', 'Pracovný úväzok', 'Stupeň štúdia', 'Celkový počet vedených záverečných prác', section='II.23'),
    FormRow('', '', '', '', '', 'R-1/R', 'R/R+1', section='II.23'),
    ItemList(cols=6, section='II.23'),
    FormRow('II.24 Komentár vysokej školy k\xa0plneniu kritéria'),
    FormRow(UserData, section='II.24'),
    FormRow('II.25 Pravidlá vytvárania skúšobných komisií na vykonanie štátnych skúšok'),
    FormRow(UserData, section='II.25'),
    FormRow('II.26 Počet skúšobných komisií na vykonanie štátnych skúšok v\xa0priemere v\xa0študijnom programe v\xa0jednom akademickom roku',
            UserData),
    FormRow('II.27 Komentár vysokej školy k\xa0plneniu kritéria'),
    FormRow(UserData, section='II.27'),
    FormRow('Podklady na vyhodnotenie plnenia kritéria KSP-A6', section='II'),
    FormRow('II.28 Informácie o\xa0garantovi študijného programu'),
    FormRow('Priezvisko a meno', UserData, 'Tituly', UserData, section='II.28'),
    FormRow('Rok narodenia', UserData, '', section='II.28'),
    FormRow('Študijný odbor (funkcia)', UserData, section='II.28'),
    FormRow('Študijný odbor (titul profesor)', UserData, 'Rok udelenia', UserData, section='II.28'),
    FormRow('Študijný odbor (titul docent)', UserData, 'Rok udelenia', UserData, section='II.28'),
    FormRow('Veľkosť pracovného úväzku', UserData, '', '', section='II.28'),
    FormRow('Garantuje študijný program na inej vysokej škole', UserData, section='II.28'),
    FormRow('Pracuje pre inú vysokú školu v\xa0pozícií rektora, prorektora, dekana, prodekana, vedúceho zamestnanca vysokej školy alebo vedúceho zamestnanca fakulty alebo vykonáva obdobnú prácu pre vysokú školu v\xa0zahraničí', UserData, section='II.28'),
    FormRow('II.29 Informácie o\xa0spolugarantovi študijného programu', ''),
    FormRow('Priezvisko a meno', UserData, 'Tituly', UserData, section='II.29'),
    FormRow('Rok narodenia', UserData, '', section='II.29'),
    FormRow('Študijný odbor (funkcia)', UserData, section='II.29'),
    FormRow('Študijný odbor (titul profesor)', UserData, 'Rok udelenia', UserData, section='II.29'),
    FormRow('Študijný odbor (titul docent)', UserData, 'Rok udelenia', UserData, section='II.29'),
    FormRow('Veľkosť pracovného úväzku', UserData, '', '', section='II.29'),
    FormRow('Garantuje študijný program na inej vysokej škole', UserData, section='II.29'),
    FormRow('Pracuje pre inú vysokú školu v\xa0pozícií rektora, prorektora, dekana, prodekana, vedúceho zamestnanca vysokej školy alebo vedúceho zamestnanca fakulty alebo vykonáva obdobnú prácu pre vysokú školu v\xa0zahraničí', UserData, section='II.29'),
    FormRow('II.30 Informácie o\xa0spolugarantovi študijného programu'),
    FormRow('Priezvisko a meno', UserData, 'Tituly', UserData, section='II.30'),
    FormRow('Rok narodenia', UserData, '', section='II.30'),
    FormRow('Študijný odbor (funkcia)', UserData, section='II.30'),
    FormRow('Študijný odbor (titul profesor)', UserData, 'Rok udelenia', UserData, section='II.30'),
    FormRow('Študijný odbor (titul docent)', UserData, 'Rok udelenia', UserData, section='II.30'),
    FormRow('Veľkosť pracovného úväzku', UserData, '', '', section='II.30'),
    FormRow('Garantuje študijný program na inej vysokej škole', UserData, section='II.30'),
    FormRow('Pracuje pre inú vysokú školu v\xa0pozícií rektora, prorektora, dekana, prodekana, vedúceho zamestnanca verejnej vysokej školy, vedúceho zamestnanca fakulty alebo vykonáva obdobnú prácu pre vysokú školu v\xa0zahraničí', UserData, section='II.30'),
    FormRow('II.31 Požiadavky aplikované pri výberovom konaní na funkčné miesta profesorov a\xa0docentov'),
    FormRow(UserData, section='II.31'),
    FormRow('II.32 Komentár vysokej školy k\xa0plneniu kritéria'),
    FormRow(UserData, section='II.32'),
    FormRow('Obsah študijného programu', section='II'),
    FormRow('Podklady na vyhodnotenie plnenia kritéria KSP-B1', section='II'),
    FormRow('II.33 Štruktúra študijného programu z\xa0pohľadu kreditov'),
    FormRow('II.33a Celkový počet kreditov potrebných na riadne skončenie štúdia', UserData),
    FormRow('II.33b Počet kreditov za povinné predmety, ktorý je potrebné získať na riadne skončenie štúdia', UserData, UserData),
    FormRow('II.33c Počet kreditov za povinne voliteľné predmety', UserData, UserData, UserData),
    FormRow('II.33d Celkový počet kreditov za jadro študijného odboru', UserData, '%'),
    FormRow('II.33e Počet kreditov za spoločný základ a\xa0za príslušný predmet, ak ide o učiteľský študijný program (v kombinácii), alebo za príslušný jazyk, v\xa0prípade študijných programov v\xa0študijnom odbore prekladateľstvo a tlmočníctvo (v kombinácii)', UserData, UserData),
    FormRow('II.34 Charakteristika predmetov študijného plánu z\xa0pohľadu opisu študijného odboru'),
    FormRow(UserData, section='II.34'),
    FormRow('II.35 Profil absolventa '),
    FormRow(UserData, section='II.35'),
    FormRow('II.36 Komentár vysokej školy k\xa0plneniu kritéria'),
    FormRow(UserData, section='II.36'),
    FormRow('Podklady na vyhodnotenie plnenia kritéria KSP-B2', section='II'),
    FormRow('II.37 Počet kreditov za prax študentov v\xa0reálnej prevádzke', UserData),
    FormRow('II.38 Splnenie charakteristiky študijného programu'),
    FormRow(UserData, section='II.38'),
    FormRow('II.39 Komentár vysokej školy k\xa0plneniu kritéria'),
    FormRow(UserData, section='II.39'),
    FormRow('Podklady na vyhodnotenie plnenia kritéria KSP-B3', section='II'),
    FormRow('II.40 Zdôvodnenie štandardnej dĺžky štúdia'),
    FormRow(UserData, section='II.40'),
    FormRow('Podklady na vyhodnotenie plnenia kritéria KSP-B4', section='II'),
    FormRow('II.41 Zdôvodnenie spojenia prvého a\xa0druhého stupňa vysokoškolského štúdia do jedného celku'),
    FormRow(UserData, section='II.41'),
    FormRow('Podklady na vyhodnotenie plnenia kritéria KSP-B5'),
    FormRow('II.42 Počet kreditov za záverečnú prácu, vrátane obhajoby', UserData),
    FormRow('II.43 Ciele a\xa0organizácia záverečnej práce vrátane obhajoby'),
    FormRow(UserData, section='II.43'),
    FormRow('Podklady na vyhodnotenie plnenia kritéria KSP-B6', section='II'),
    FormRow('II.44 Názov študijného programu obsahuje spojenie „inžinierstvo, inžiniersky“', UserData),
    FormRow('II.45 Udeľovaný akademický titul je inžinier (v skratke Ing.) alebo inžinier architekt (v skratke Ing. arch.) ', UserData),
    FormRow('II.46 Počet kreditov za projektovú prácu  celkovo', UserData),
    FormRow('-Záverečná práca ', UserData, '-Práca na projektoch v\xa0rámci ostatných predmetov', UserData),
    FormRow('', '', '-Odborná prax ', UserData),
    FormRow('II.47 Podiel kreditov, ktoré sa získavajú za prácu na projektoch, na celkovom počte kreditov  potrebných na riadne skončenie štúdia', UserData),
    FormRow('II.48 Komentár vysokej školy k\xa0plneniu kritéria'),
    FormRow(UserData, section='II.48'),
    FormRow('Podklady na vyhodnotenie plnenia kritéria KSP-B7', section='II'),
    FormRow('II.49 Názov študijného programu obsahuje slovo umenie alebo od neho odvodený názov', UserData),
    FormRow('II.50 Udeľovaný akademický titul je magister umenia (v skratke Mgr. art.) alebo doktor umenia (v skratke ArtD.)', UserData),
    FormRow('II.51 Počet kreditov získaných za umelecké výkony - celkovo', UserData, '-z toho za záverečnú prácu', UserData),
    FormRow('II.52 Podiel kreditov získaných za umelecké výkony na celkovom počte kreditov potrebných na riadne skončenie štúdia', UserData),
    FormRow('II.53 Komentár vysokej školy k\xa0plneniu kritéria'),
    FormRow(UserData),
    FormRow('Požiadavky na uchádzačov a\xa0spôsob ich výberu', section='II'),
    FormRow('Podklady na vyhodnotenie plnenia kritéria KSP-B8', section='II'),
    FormRow('II.54 Spôsob prijímania na štúdium'),
    FormRow(UserData, section='II.54'),
    FormRow('II.55 Ďalšie podmienky prijatia na štúdium'),
    FormRow(UserData, section='II.55'),
    FormRow('II.56 Selektívnosť podmienok prijatia'),
    FormRow('Denná forma'),
    FormRow(' Akademický rok', 'Počet podaných prihlášok', 'Počet prijatých', 'Počet zapísaných'),
    ItemList(cols=6, section='II.56', numbers=False),
    FormRow('Externá forma'),
    FormRow('Akademický rok', 'Počet podaných prihlášok', 'Počet prijatých', 'Počet zapísaných'),
    ItemList(cols=6, section='II.56', numbers=False),
    FormRow('Požiadavky na absolvovanie štúdia', section='II'),
    FormRow('Podklady na\xa0vyhodnotenie plnenia kritéria KSP-B9', section='II'),
    FormRow('II.57 Aplikovanie systému vnútorného zabezpečovania kvality'),
    FormRow(UserData, section='II.57'),
    FormRow('II.58 Štruktúra požiadaviek na riadne skončenie štúdia'),
    FormRow(UserData, section='II.58'),
    FormRow('II.59 Úspešnosť štúdia'),
    FormRow('Denní', 'R/R+1', 'R+1/R+2', 'R+2/R+3', 'R+3/R+4', 'R+4/R+5', 'R+5/R+6', section='II.59'),
    FormRow('Novoprijatí', UserData, UserData, UserData, UserData, UserData, UserData, section='II.59'),
    FormRow('Absolventi', UserData, UserData, UserData, UserData, UserData, UserData, section='II.59'),
    FormRow('', section='II.59'),
    FormRow('Externí', 'R/R+1', 'R+1/R+2', 'R+2/R+3', 'R+3/R+4', 'R+4/R+5', 'R+5/R+6', section='II.59'),
    FormRow('Novoprijatí', UserData, UserData, UserData, UserData, UserData, UserData, section='II.59'),
    FormRow('Absolventi', UserData, UserData, UserData, UserData, UserData, UserData, section='II.59'),
    FormRow('', section='II.59'),
    FormRow('II.60 Rozloženie hodnotenia záverečných prác'),
    FormRow('Počet študentov v\xa0dennej forme štúdia so zodpovedajúcim hodnotením v\xa0príslušnom akademickom roku', section='II.60'),
    FormRow(' Hodnotenie', 'R/R+1', 'R+1/R+2', 'R+2/R+3', 'R+3/R+4', 'R+4/R+5', 'R+5/R+6', section='II.60'),
    FormRow('A', UserData, UserData, UserData, UserData, UserData, UserData, section='II.60'),
    FormRow('B', UserData, UserData, UserData, UserData, UserData, UserData, section='II.60'),
    FormRow('C', UserData, UserData, UserData, UserData, UserData, UserData, section='II.60'),
    FormRow('D', UserData, UserData, UserData, UserData, UserData, UserData, section='II.60'),
    FormRow('E', UserData, UserData, UserData, UserData, UserData, UserData, section='II.60'),
    FormRow('FX', UserData, UserData, UserData, UserData, UserData, UserData, section='II.60'),
    FormRow('Počet študentov v\xa0externej forme štúdia so zodpovedajúcim hodnotením v\xa0príslušnom akademickom roku', section='II.60'),
    FormRow(' Hodnotenie', 'R/R+1', 'R+1/R+2', 'R+2/R+3', 'R+3/R+4', 'R+4/R+5', 'R+5/R+6', section='II.60'),
    FormRow('A', UserData, UserData, UserData, UserData, UserData, UserData, section='II.60'),
    FormRow('B', UserData, UserData, UserData, UserData, UserData, UserData, section='II.60'),
    FormRow('C', UserData, UserData, UserData, UserData, UserData, UserData, section='II.60'),
    FormRow('D', UserData, UserData, UserData, UserData, UserData, UserData, section='II.60'),
    FormRow('E', UserData, UserData, UserData, UserData, UserData, UserData, section='II.60'),
    FormRow('FX', UserData, UserData, UserData, UserData, UserData, UserData, section='II.60'),
    FormRow('', section='II.60'),
    FormRow('II.61 Komentár vysokej školy k\xa0plneniu kritéria'),
    FormRow(UserData, section='II.61'),
    FormRow('Podklady na vyhodnotenie plnenia kritéria KSP-B10', section='II'),
    FormRow('II.62 Komentár vysokej školy k\xa0plneniu kritéria'),
    FormRow(UserData, section='II.62'),
    FormRow('Podklady na vyhodnotenie plnenia kritéria KSP-B11', section='II'),
    FormRow('II.63 Uplatnenie absolventov '),
    FormRow(UserData, section='II.63'),
    FormRow('III. Spolu s\xa0formulárom sa predkladajú nasledujúce doklady'),
    FormRow(' ', 'Počet', section='III'),
    FormRow('III.1 Vedecko-pedagogické alebo umelecko-pedagogické charakteristiky profesorov a\xa0docentov pôsobiacich v\xa0študijnom programe (kritérium KSP-A3)', UserData),
    FormRow('III.2 Vedecko-pedagogické alebo umelecko-pedagogické charakteristiky školiteľov v\xa0doktorandskom štúdiu (kritérium KSP-A4)', UserData),
    FormRow('III.3 Zoznam vedúcich záverečných prác  a\xa0tém záverečných prác za obdobie dvoch rokov (kritérium KSP-A4)', UserData),
    FormRow('III.4 Zloženie skúšobných komisií na vykonanie štátnych skúšok v\xa0študijnom programe za posledné dva roky (kritérium KSP-A5)', UserData),
    FormRow('III.5 Kritériá na obsadzovanie funkcií profesor a\xa0docent (kritérium KSP-A6)', UserData),
    FormRow('III.6 Odporúčaný študijný plán (kritérium KSP-B1)', UserData),
    FormRow('III.7 Dohoda spolupracujúcich vysokých škôl (kritérium KSP-B1)', UserData),
    FormRow('III.8 Informačné listy predmetov (kritérium KSP-B2)', UserData),
    FormRow('III.9 Požadované schopnosti a\xa0predpoklady uchádzača o\xa0štúdium študijného programu (kritérium KSP-B8)', UserData),
    FormRow('III.10 Pravidlá na schvaľovanie školiteľov v\xa0doktorandskom študijnom programe (kritérium KSP-B9)', UserData),
    FormRow('III.11 Stanovisko alebo súhlas príslušnej autority k\xa0študijnému programu (kritérium KSP-B10)', UserData),
    FormRow('III.12 Zoznam dokumentov predložených ako príloha k\xa0žiadosti', UserData),
)


def check_formular_sp(messages, path, document):
    rows = []
    for row in split_by(document_content(document.root), match_control_word(b'row')):
        rows.append([as_text(x) for x in list(split_end_by(row, match_control_word(b'cell')))])

    form_rows = struct_formular_sp

    i = 0
    j = 0
    row_index = 0

    table = [[0] * (len(form_rows) + 1) for i in range(len(rows)+1)]
    direction = [[0] * (len(form_rows) + 1) for i in range(len(rows)+1)]

    for i in range(len(rows) + 1):
        for j in range(len(form_rows) + 1):
            if i == 0:
                table[i][j] = j
            elif j == 0:
                table[i][j] = i
            else:
                have_data = len(rows) > row_index
                if have_data:
                    match, skip = form_rows[j-1].match(rows, row_index)
                    row_index += min(1, skip)
                else:
                    match = False
                subst = table[i - 1][j - 1] + (0 if match else 1)
                delet = table[i - 1][j] + (1 if have_data else 0)
                inser = table[i][j - 1] + 1
                value = min(subst, delet, inser)
                table[i][j] = value
                if value == subst:
                    direction[i][j] = 0
                elif value == inser:
                    direction[i][j] = 1
                elif not have_data:
                    direction[i][j] = 3
                else:
                    direction[i][j] = 2

    i, j = len(rows), len(form_rows)

    while i > 0 and j > 0:
        print(direction[i][j])

    print(table)
    print(direction)


def check_formular_sp2(messages, path, document):
    rows = []
    for row in split_by(document_content(document.root), match_control_word(b'row')):
        rows.append([as_text(x) for x in list(split_end_by(row, match_control_word(b'cell')))])

    i = 0
    while i < len(struct_formular_sp):
        form_row = struct_formular_sp[i]
        if isinstance(form_row, FormRow):
            for j in range(len(rows)):
                match, skip = form_row.match(rows, j)
                if match:
                    break
            else:
                # TODO




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
    check_rtf(messages, sp_form_path, check_formular_sp)


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