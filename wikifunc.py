# coding=utf-8 

import bz2
import re
import sys
from ufal.morphodita import *

reload(sys)  
sys.setdefaultencoding('utf-8')

# In Python2, wrap sys.stdin and sys.stdout to work with unicode.
if sys.version_info[0] < 3:
    import codecs
    import locale
    encoding = locale.getpreferredencoding()
    sys.stdin = codecs.getreader(encoding)(sys.stdin)
    sys.stdout = codecs.getwriter(encoding)(sys.stdout)

try:
    import xml.etree.cElementTree as ET
except ImportError:
    import xml.etree.ElementTree as ET

from mwlib.parser import nodes 
from mwlib.refine.compat import parse_txt

###########################################################################

def encode_entities(text):
    return text.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;').replace('"', '&quot;')

###########################################################################

def title_sux(title, bad_title, bad_title_dir, bad_title_list, bad_date, bad_letter):
    if re.match(bad_title, title) or re.match(bad_title_dir, title) or re.match(bad_title_list, title) or re.match(bad_date, title) or re.match(bad_letter, title):
        return True
    else:
        return False

###########################################################################

def parse_dump(xml_fn, MW_NS):
    with bz2.BZ2File(xml_fn, 'r') as fr:
        for event, elem in ET.iterparse(fr):
            if elem.find('{0}redirect'.format(MW_NS)) is None: #v prvni verzi preskocit redirect, pozdeji by sel tenhle prvek pridat do json vystupu do sekce synonyms
                if event == 'end' and elem.tag == '{0}page'.format(MW_NS):
                    text = elem.find('{0}revision/{0}text'.format(MW_NS))
    
                    title = elem.find('{0}title'.format(MW_NS)).text

                    yield title, text.text
                    elem.clear()
            else:
                continue

###########################################################################

def get_text(p, o, buffer=None, depth=0):
    if buffer is None:
        buffer = []
        
    for ch in p.children:
        descend = True
        if isinstance(ch, o.IGNORE):
            continue
        elif isinstance(ch, nodes.Section):
            for ch in ch.children[1:]:
                get_text(ch, o, buffer, depth+1)
            descend = False
        elif isinstance(ch, nodes.Text):
            text = ch.asText()
            text = ' '.join(text.splitlines())
            buffer.append(text)

        if descend:
            get_text(ch, o, buffer, depth+1)
    
    return buffer

###########################################################################

def removeParentheses(s):
    ret = ''
    skip = 0
    for i in s:
        if i == '(':
            skip += 1
        elif i == ')'and skip > 0:
            skip -= 1
        elif skip == 0:
            ret += i
    return ret

###########################################################################

def removeBraces(s):
    ret = ''
    skip = 0
    i = 0
    s += ' ' # napr. kvuli clanku Binarni cisla, kde jne posledni extrahovana veta ukoncena jen jednim '}'  

    for x in s:
        if i == len(s):
            break
        
        elif s[i] == '{' and s[i+1] == '{':         
            skip += 1          
            i += 1
        elif s[i] == '}' and s[i+1] == '}' and skip > 0:         
            skip -= 1
            i += 1 

        elif skip == 0:                       
            ret += s[i]
            if s[i] == '.': # pridani mezery za kazdou tecku, morphodita je dost citliva a nerozpozna konec spatne formatovane vety
                ret += ' '     
        i += 1          

    return ret

###########################################################################

def n1_no_n7(definitions): # pokud existuje definice s N1, pouzij jen definice obsahujici N1, jinak pouzij puvodni definice

    new_definitions = []
    found_n1 = False

    for definition in definitions:
        for word in definition:
            if word[0][0] == 'N' and word[0][4] == '1':
                found_n1 = True
                new_definitions.append(definition)
                break
    if found_n1: # nalezena alespon jedna definice s N1, pouzit pouze definice s N1
        return new_definitions
    else: # ani jedna definice s N1, pouzit vsechny definice (muze tam byt nekde N7)
        return definitions

###########################################################################

def divide_definitions(definitions):

    new_definitions = []
    new_definition = []

    for definition in definitions:
        for word in definition:
            if word[2] == '.': # je to tecka
                continue
            elif word[2] == 'a' or word[2] == 'i':
                new_definitions.append(new_definition) # pridano do new_definitions
                new_definition = []   
                continue                    
            else: # pokud neni spojka, zapisuj dal do noveho listu
                new_definition.append(word)
        new_definitions.append(new_definition)
        new_definition = []
    del definitions[:]
    return new_definitions

###########################################################################

def connect_single_adverbs(definitions):
       
    new_definitions = []

    if len(definitions) > 0:

        found_sample = False
        found_adv = False
        candidate = False # nalezen kandidatni A na pridani N k sobe
        test_definitions = zip(definitions[1:], definitions)

        for definition, prev_definition in test_definitions:
            if len(prev_definition) == 1 and prev_definition[0][0][0] == 'A':
                candidate = True
                for word in definition:
                    if word[0][0] == 'A':
                        found_adv = True
                    if found_adv:
                        if word[0][0] == 'A': # dalsi A preskakuj nez najdes N
                            continue
                        if word[0][0] == 'N' and (word[0][4] == '1' or word[0][4] == '7'): # prvni nalezene N17, bude to sample
                            sample = word
                            found_sample = True
                            break
                    
            if found_sample and candidate: # nic nebrani do prev_def nacpat N
                prev_definition.append(sample)

            new_definitions.append(prev_definition)        

            found_sample = False
            found_adv = False
            candidate = False

        new_definitions.append(definitions[-1]) # pridani posledni definice      

    return new_definitions            

###########################################################################

def leave_disconnected(definitions): # pokud doslo k rozdeleni "pro vojaky a statecne generaly" -> "pro vojaky"

    new_definitions = []
    found_prep = False
    found_sample = False
    delete_definition = False
    # pokud byla v predchozi definici predlozka, 
    # vytahni z ni sample N a uloz; ignoruj v aktualni definici vsechna A nez najdes N. 
    # Pokud ma stejny pad jako sample, aktualni definici neukladej

    if len(definitions) > 0:
        new_definitions.append(definitions[0]) # vloz automaticky prvni definici
        test_definitions = zip(definitions[1:], definitions)

        for definition, prev_definition in test_definitions:
            for prev_word in prev_definition: # hledej predlozku
                if found_prep:
                    if prev_word[0][0] == 'N':
                        sample = prev_word
                        found_sample = True
                if prev_word[0][0] == 'R':
                    found_prep = True

            if found_prep and found_sample: # naslo to predlozku a ulozilo prvni N jako sample
                for word in definition:
                    if word[0][0] == 'A': # preskakuj A
                        continue
                    elif word[0][0] == 'N':
                        if word[0][4] == sample[0][4]: # bylo nalezeno N ve stejnem padu jako sample
                            delete_definition = True
                            break
                    else: # pokud by to naslo neco jineho nez A nebo N
                        break

            if not delete_definition:
                new_definitions.append(definition)
            found_prep = False
            found_sample = False
            delete_definition = False

    return new_definitions

###########################################################################    

def limit_definitions(definitions):

    for definition in definitions: # pokud v definici neni VN127, smazat
        i = 0
        for d in definition:
            if d[0][0] == 'V' or (d[0][0] == 'N' and (d[0][4] == '1' or d[0][4] == '7' or d[0][4] == '2')):
                continue
            i += 1                        
        if i == len(definition):
            definitions.remove(definition)
    return definitions

###########################################################################

def isAlive(words_list):
    next = False # prepinac: slovo 'byt' nalezeno 
    for word in words_list:
        for w in word:                
            if next:
                if w[0][0] == 'N' and w[0][1] == 'N':
                    if (w[0][2] == 'M' or w[0][2] == 'F'): # je to zivy, rod M nebo F                            
                        return True # je to F / M                          
                    else:
                        return False # je to N

            if w[1].encode('utf-8') == 'být': # 1. vyskyt slova byt, za nim musi byt nejake podstatne jmeno                    
                next = True
                
    return False 

###########################################################################

def connect_definitions(definitions, title, o): # otec Claire a Alice => otec Claire, otec Alice

    b = 0
    i = 0
    found_noun = False
    found_suspected = False
    new_definitions = zip(definitions[1:], definitions) # pripojeni vhodnych definic kde byly rozdeleny spojkou zpatky
    for definition, prev_definition in new_definitions: # tuples ve formatu (predchozi definice, aktualni definice)  
        for prev_d in prev_definition: # predchozi definice         
            if not found_noun:
                if prev_d[0][0] == 'N' and prev_d[0][1] == 'N' and prev_d[2] != title: #BUG: provizorni fix reseni situace struktury clanku .. je <NAME> oznacovan za.. 
                    found_noun = True
                    sample = prev_d # tohle je to co se vlozi do druhe definic
                    continue
            if found_noun:
                if prev_d[0][0] == 'N' and prev_d[0][1] == 'N':
                    suspected = prev_d # tohle je to co bude mit stejny pad jako to v druhe definici
                    found_suspected = True
                    break

        if found_noun: # nasel 1. dostupne podstatne jmeno v predchozi definici
            for d in definition: # aktualni definice, prvni prubeh            
                if d[0][0] == 'N' and d[0][1] == 'N':
                    if d[0][4] == '1': # konec, nasel 1. pad
                        b = 0
                        break
                    elif found_suspected and d[0][4] == suspected[0][4]: # je tam podstatne jmeno mimo prvni pad a stejneho padu jako suspected
                        b += 1
            if b == 1: # v aktualni definici je jedno podst. jm. stejneho padu jako suspected, a zadne v 1. pade
                sample = morph_fall(sample, o)            
                definitions[i+1].insert(0, sample)
        found_noun = False
        found_suspected = False
        b = 0
        i += 1

###########################################################################

def definitions_postprocessing(definitions): # BUG: pouzit rozsirena pravidla pro zjistovani obsahu vety, nejen pomoci prvniho slova ale i podle dalsich nasledujicich slov ve vete. Nejen prislovce, ale i spojky... atd

    new_definition = []
    new_definitions = []
    special = False # specialni zpracovani prislovce na zacatku vety
    found_noun = False # zpracovani prislovce - musi to najit podst jmeno v 1./7. pade, aby veta s prislvocem na zacatku prosla

    for definition in definitions: # postprocessing definic
        if len(definition) > 0:
            if definition[0][0][0] == 'N' and definition[0][0][4] != '1' and definition[0][0][4] != '7': # definice zacina na N23456 - preskocit
                continue
            # bacha, tohle je hodne nebezpecne. Musi v ni byt N17 - viz limit definitions, neni nejspis moc dulezite na co zacina.
            #elif definition[0][0][0] != 'P' and definition[0][0][0] != 'V' and definition[0][0][0] != 'D' and definition[0][0][0] != 'T' and not(definition[0][0][0] == 'C' and definition[0][0][1] == '='):
            #   new_definitions.append(definition) # definice nezacina na TPVDC=, tak ji pridej
            elif definition[0][0][0] == 'D': # zacinala na prislovce
                for d in definition:
                    if d[0][0] == 'N' and d[0][1] == 'N' and (d[0][4] == '1' or d[0][4] == '7'):
                        found_noun = True
                    if found_noun:
                        new_definition.append(d)
                if found_noun:
                    new_definitions.append(new_definition)
                new_definition = []
            else: # prozatimni nahrada TPVDC=, treba to nebude fungovat tak kdyztak dat zpatky
                new_definitions.append(definition)

            found_noun = False

    return new_definitions

###########################################################################

def cut_by_act_adjective(definitions):

    new_definitions = []
    new_definition = []
    foundag = False # nalezeno aktivni adjektivum
    foundn = False # nalezeno N17

    for definition in definitions:
        for word in definition:
            if not foundn and word[0][0] == 'N' and (word[0][4] == '1' or word[0][4] == '7'):
                foundn = True
            elif not foundag and word[0][0] == 'A' and word[0][1] == 'G':
                foundag = True
                if foundn: # N17 uz bylo nalezeno, AG nechces, ukonci
                    break
                else: # N17 jeste nenalezeno, pokracuj v jeho hledani
                    new_definition = [] # smaz co uz je pridano
                    continue
            new_definition.append(word)

        if foundn and len(new_definition) > 0:
            new_definitions.append(new_definition)                      

        new_definition = []
        foundag = False
        foundn = False

    return new_definitions

###########################################################################

def cut_by_preposition(definitions):
    # pokud najde Rx, useknuti definicice - at neni zbytecne dlouha
    new_definition = []
    new_definitions = []
    found_noun = False
    delete = False

    for definition in definitions:
        for word in definition:
            if not found_noun and word[0][0] == 'R': # pokud je nalezena predlozka, ale jeste ne podst jmeno, neukladat
                delete = True
                break
            elif found_noun and word[0][0] == 'R': # musi to napred najit N, nez to zacne mazat neco za predlozkami
                break
            elif word[0][0] == 'N' and (word[0][4] == '1' or word[0][4] == '7'):
                found_noun = True
            new_definition.append(word)

        if len(new_definition) > 0 and not delete:
            new_definitions.append(new_definition)  
        new_definition = []
        found_noun = False
        delete = False

    return new_definitions

###########################################################################

def cut_by_n2(definitions): # zkracuje: N1 ... N2 |CUT

    found_noun = False
    found_noun_n2 = False
    new_definition = []
    new_definitions = []

    for definition in definitions:
        for d in definition:
            if found_noun_n2:
                if d[0][0] == 'A' or (d[0][0] == 'N' and d[0][1] == 'N' and d[0][4] == '2'): # dohledej zbytek N2 nebo A
                    new_definition.append(d)
                    continue
                else: # pokud uz nejsou N2 ani A, utni to
                    break
            elif found_noun: # "oblast .." ocekavam N2 nebo neco jineho
                if d[0][0] == 'N' and d[0][1] == 'N' and d[0][4] == '2': # naslo to N2, pokracovat dokud je to nepobere vsechny
                    new_definition.append(d)
                    found_noun_n2 = True
                    continue
            elif d[0][0] == 'N' and d[0][1] == 'N' and d[0][4] == '1':
                found_noun = True # naslo to N1
            new_definition.append(d)

        new_definitions.append(new_definition)
        new_definition = []
        found_noun = False
        found_noun_n2 = False

    return new_definitions

###########################################################################

def print_type(setup,o):

    if setup == 'L':
        o.f.write('location\t')
    elif setup == 'A':
        o.f.write('art\t')
    elif setup == 'O':
        o.f.write('organization\t')
    elif setup == 'R':
        o.f.write('product\t')
    elif setup == 'P':                   
        o.f.write('person\t')
    elif setup == 'E':                   
        o.f.write('event\t') 

###########################################################################

def print_subdefinitions(subdefinitions,o):
    for subdefinition in subdefinitions:                                      
        o.f.write('|') 
        for s in subdefinition:
            o.f.write(s[2].encode('utf-8'))
            o.f.write(' ')
    o.f.write('\t')        
         
def test_print(definitions,o):
    o.rr.write('Definice co predchazely 0:\t')
    for definition in definitions:                                      
        o.rr.write('|'),
        for d in definition:
            o.rr.write(d[2].encode('utf-8') + ' '),
    o.rr.write('\n')     

###########################################################################

def create_subdefinitions(definitions, o):

    subdefinitions = []
    subdefinition = []

    for definition in definitions:
        
        if len(definition) == 1: # jednoslovna definice, jeden z castych pripadu
            if definition[0][0][0] == 'N':
                for d in definition:
                    if d[0][4] != '1':                
                        d = morph_fall(d, o) # prepis na prvni pad
                    subdefinition.append(d)
                    subdefinitions.append(subdefinition)

        else: # definice delsi nez jedno slovo, analyza po slovech
            n = 0 # pocitadlo podst. jmen
            c = 0 # counter poctu vyskytu podstatnych jmen v 1. pade
            noun_processed = False #pouze kdyz c == 0
            fall_is_ok = False # nalezen N17 ve vete, jinak vynechat

            for d in definition:
                if d[0][0] == 'N' and d[0][1] == 'N':
                    n += 1
                    if d[0][4] == '1': # N1
                        c += 1
                    if d[0][4] == '1' or d[0][4] == '7': # N17
                        fall_is_ok = True

            if n > 0 and fall_is_ok: # je tam alespon jedno podst. jm.
                w = 0 # celkovy citac slov
                a = 0 # pocitadlo adjektiv
                i = 0 # iterator celkovy

                for d in definition:
                    if d[0][0] == 'A':
                        if i == 0 and d[0][4] != '1': # na zacatku vety, pravdepodobne potreba prevest do 1. padu
                            subdefinition.append(morph_fall(d, o))
                        else:
                            subdefinition.append(d)                            
                        a += 1
                        w += 1                      
                        continue
                    elif d[0][0] == 'R' and w == 0: # predlozka
                        continue
                    elif d[0][0] == 'C': # cislovka
                        subdefinition.append(d) # puvodne tu bylo continue
                    elif d[0][0] == 'N' and c == 0: # podstatne jmeno, v definici nebyl nalezen N1
                        if not noun_processed:
                            d = morph_fall(d, o)
                            noun_processed = True
                        subdefinition.append(d)
                    elif d[0][0] == 'N': # v definici byl N1
                        subdefinition.append(d)                         
                    elif d[0][0] == 'P' and w == 0: # zajmeno na prvnim miste definice
                        continue
                    elif d[0][0] == 'Z' and (d[2] == '/' or d[2] == '-'):
                        subdefinition.append(d)
                    else:
                        continue # BUG: tady bylo break
                    i += 1
                if len(subdefinition) > 1: # odstranit posledni slovo, pokud je to adjektivum
                    if subdefinition[-1][0][0] == 'A':
                        subdefinition.remove(subdefinition[-1])

                if len(subdefinition) > 0:
                    if not(len(subdefinition) == 1 and subdefinition[0][0][0] == 'A'): # pokud jednoslovne ajdektivum, odstranit
                        subdefinitions.append(subdefinition)
                w = 0
                a = 0
                i = 0
            c = 0
            n = 0
            noun_processed = False
            fall_is_ok = False

        subdefinition = []

    return subdefinitions

###########################################################################

def get_definitions(words_list,setup,title,whole_sentence,o):

    definitions = [] # extrakce definicnich celych bloku k dalsimu zpracovani
    def_temp = [] # docasna jednotliva definice
    def_saver = False # jeste nebylo nalezeno sloveso "byt"

    for words in words_list: # nacteni definic
        for word in words:
            if not def_saver: # dokud nenajde prvni 'byt'
                if word[1].encode('utf-8') == 'být':
                    def_saver = True
                    continue
            if def_saver:
                if word[0][0] == 'J': # pokud je tahle spojka na zacatku vety a def_temp je prazdny tak nedelej nic
                    if len(def_temp) == 0: # pokud je list pred spojkou 'a' prazdny
                        continue
                    else: # pripojovani vety pres spojku 'a' k druhe vete
                        def_temp.append(word)
                else:
                    def_temp.append(word)
        if def_saver:
            definitions.append(def_temp)
            def_temp = []

    skip = False # defaultne nepreskakovat zadne kroky, predpoklad ze len(definitions) != 0

    ##################
    ##  FILTROVANI  ##
    ##################

    if len(definitions) != 0:
        definitions = definitions_postprocessing(definitions) # odstran podle zacatku definice
    if not skip and len(definitions) == 0:
        o.rr.write('0 po definitions postprocessing\t')
        skip = True

    if not skip:
        definitions = limit_definitions(definitions) # odstran podle obsahu definice
    if not skip and len(definitions) == 0:
        o.rr.write('0 po limit definitions)\t')
        skip = True

    if not skip:
        definitions = cut_by_act_adjective(definitions) # pokud definice s AG neobsahuje N17, vystrihni ven, jinak ji bez AG pouzij
    if not skip and len(definitions) == 0:
        o.rr.write('0 po cut adjective\t')
        skip = True

    if not skip:
        definitions = cut_by_preposition(definitions) # smaz vse po R, pokud pred R neni N17 tak celou definici
    if not skip and len(definitions) == 0:
        o.rr.write('0 po cut by preposition)\t')
        skip = True

    ## DIVIDE ##

    if not skip:
        definitions = divide_definitions(definitions) # vsechno rozdel podle spojek
    if not skip and len(definitions) == 0:
        o.rr.write('0 po divide definitions\t')
        skip = True

    if not skip:
        connect_definitions(definitions, title, o)  # otec Sidney a Alice -> otec Sidney, otec Alice
    if not skip and len(definitions) == 0:
        o.rr.write('0 po connect definitions\t')
        skip = True

    if not skip:
        definitions = connect_single_adverbs(definitions) # spojit single A s N z dalsi vety
    if not skip and len(definitions) == 0:
        o.rr.write('0 po conenct single adverbs\t')
        skip = True

    if not skip:
        definitions = leave_disconnected(definitions) # ustrihni to co bylo pred rozdelenim spojeno predlozkou
    if not skip and len(definitions) == 0:
        o.rr.write('0 po cut by conjunction)\t')
        skip = True

    if not skip:
        definitions = cut_by_n2(definitions) # N1 A A A N2 |cut
    if not skip and len(definitions) == 0:
        o.rr.write('0 po cut by n2\t')
        skip = True

    if not skip:
        subdefinitions = create_subdefinitions(definitions, o) # vytvor z definitic i subdefinice
    if not skip and len(subdefinitions) == 0:
        o.rr.write('0 po create subdefinitions\t')
        skip = True

    ##################
    ##  PRINTOVANI  ##
    ##################

    print_type(setup,o)

    if not skip:
        print_subdefinitions(subdefinitions,o)
    else: # len(subdefinitons)=0
        o.f.write('-\t') # "-" = zastupny znak misto definic v souboru result
        o.rr.write(title.encode('utf-8')) 
        o.rr.write('\t')

        if setup == 'L':
            o.rr.write('location\t')
        elif setup == 'A':
            o.rr.write('art\t')
        elif setup == 'O':
            o.rr.write('organization\t')
        elif setup == 'R':
            o.rr.write('product\t')
        elif setup == 'P':                   
            o.rr.write('person\t')
        elif setup == 'E':                   
            o.rr.write('event\t') 

        o.rr.write('\t')
        o.rr.write(whole_sentence.encode('utf-8'))
        o.rr.write('\n')     

    del definitions[:]

###########################################################################

def get_setup(words_list, whole_sentence, title_lemmas_list, title_tags_list, o):

# radit od nejspecifictejsich po nejobecnejsi, kvuli presnosti

## PRODUCT
    foundAjd = False
    foundVerb = False # pokud to naslo sloveso
    analyse = False # co nasleduje po frazi ktery/jenz
    oneSentence = False # rozsah klicove fraze pouze v jedne vete    
    for words in words_list: # analyza Product
        for word in words:
            if re.match(o.re_connect, word[1]) and not oneSentence: # ktery/jenz..
                oneSentence = True
                analyse = True
                continue
            if analyse:
                if foundAjd:
                    if re.match(o.re_product_maker, word[1]):
                        return 'R'
                    break                    
                            
                if word[0][0] == 'V': # je tam sloveso, alespon melo by tam byt
                    foundVerb = True # bylo tam mezi tim nalezeno sloveso
                    continue
                elif word[0][0] == 'A': # nalezeno adjektivum, e.g. 'vyvinuty'
                    foundAjd = True
                    continue
                if re.match(o.re_product_maker, word[1]) and foundVerb: #..vyrobila firma/spolecnost
                    return 'R'
        if analyse:
            break
    n = 0 # pocet podst. jmen mezi 'byt' a klicovym podst. jmenem
    analyse = False # co nasleduje po slove 'byt'
    oneSentence = False # rozsah klicove fraze pouze v jedne vete    
    for words in words_list: # analyza Product
        for word in words:
            if word[1].encode('utf-8') == 'být' and not oneSentence:
                oneSentence = True
                analyse = True
                continue
            if analyse:
                if word[0][0] == 'N':
                    n += 1
                if re.match(o.re_product, word[1]) and (word[0][4] == '1' or word[0][4] == '7') and n == 1: #and not matchPerson:
                     return 'R'
        if analyse:
            break

    ## ART
    n = 0  # pocet podst. jmen mezi 'byt' a klicovym podst. jmenem
    analyse = False  # co nasleduje po slove 'byt'
    oneSentence = False  # rozsah klicove fraze pouze v jedne vete
    for words in words_list:  # analyza Art
        for word in words:
            if word[1].encode('utf-8') == 'být' and not oneSentence:
                oneSentence = True
                analyse = True
                continue
            if analyse:
                if word[0][0] == 'N':  # and word[0][4] != '7' nektere 7. pady se tam pouzivaji
                    n += 1
                if re.match(o.re_art, word[1]) and (
                        word[0][4] == '1' or word[0][4] == '7') and n == 1:  # and not matchPerson:
                    return 'A'
        if analyse:
            break

    ## ORGANIZATION
    exc1 = False # vyjimka 1, maloobchodni prodejce a obchodni retezec
    analyse = False # co nasleduje po slove 'byt'
    for words in words_list: # analyza Organization
        for word in words:
            if word[1].encode('utf-8') == 'být':
                analyse = True
                continue
            if analyse:
                if exc1:
                    if word[1].encode('utf-8') == 'prodejce' or word[1].encode('utf-8') == 'řetězec':
                        return 'O'
                    exc1 = False
                if re.match(o.re_company, word[1]) and word[0][4] == '1':
                    return 'O'       
                elif word[1].encode('utf-8') == 'maloobchodní' or word[1].encode('utf-8') == 'obchodní':
                    exc1 = True
                    continue  
        if analyse:
            break

    ## EVENT
    n = 0  # pocet podst. jmen mezi 'byt' a klicovym podst. jmenem
    analyse = False  # co nasleduje po slove 'byt'
    oneSentence = False  # rozsah klicove fraze pouze v jedne vete

    for words in words_list:  # analyza Event
        for word in words:  # test na frazi je 'necim/neco'
            if word[1].encode('utf-8') == 'být' and not oneSentence:
                oneSentence = True
                analyse = True
                continue
            if analyse:
                if word[0][0] == 'N':
                    n += 1
                if re.match(o.re_event, word[1]) and (
                        word[0][4] == '1' or word[0][4] == '7') and n == 1:  # and not matchPerson:
                    return 'E'
        if analyse:
            break

    cntAnalysis1 = False
    cntAnalysis2 = False
    cntAnalysis3 = False
    cntAnalysis4 = False
    for word in words_list[0]:  # analyza frazi v prvni subvete
        if cntAnalysis4:
            if word[1].encode('utf-8') == '    dojít':
                return 'E'
        elif cntAnalysis3:
            cntAnalysis3 = False
            if word[1].encode('utf-8') == '    který':
                cntAlanysis4 = True
                continue
        elif cntAnalysis2:
            cntAnalysis2 = False
            if word[1].encode('utf-8') == 'zaznamenat_:W':
                return 'E'
        elif cntAnalysis1:
            cntAnalysis1s = False
            if word[1].encode('utf-8') == 'stát-2_^(něco_se_přihodilo)' or word[1].encode('utf-8') == 'odehrát':
                return 'E'

        if word[1].encode('utf-8') == 'se_^(zvr._zájmeno/částice)':
            cntAnalysis = True
            continue
        elif word[1].encode('utf-8') == 'proběhnout_:W':
            return 'E'
        elif word[1].encode('utf-8') == 'být':
            cntAnalysis2 = True
        elif word[1].encode('utf-8') == 'k-1':
            cntAnalysis3 = True

    ## LOCATION
    n = 0 # pocet podst. jmen mezi 'byt' a klicovym podst. jmenem
    analyse = False # co nasleduje po slove 'byt'
    oneSentence = False # rozsah klicove fraze pouze v jedne vete
    for words in words_list: # analyza Location
        for word in words:
            if word[1].encode('utf-8') == 'být' and not oneSentence:
                oneSentence = True
                analyse = True
                continue
            if analyse:
                if word[0][0] == 'N': # and word[0][4] != '7'
                    n += 1
                if re.match(o.re_location, word[1]) and n == 1: #and not matchPerson:
                     return 'L'
        if analyse:
            break

    ## PERSON
    bad_fall = False # spatny pad ve jmenu
    analyse = False
    a = 0
    half = 0
    for title_lemma in title_lemmas_list:  # analyza Person
        if re.match(o.re_person_title, title_lemma):
            analyse = True
            half = half + 1
            break
    if analyse and (half > float(len(title_lemmas_list))/2): # spravne regexy jmen musi tvorit vic nez polovinu slov v nazvu
        for tag in title_tags_list:
            if (tag[0] == 'N' and (tag[4] == '1' or tag[4] == 'X')) or tag[0] == 'C' or tag[0] == 'R' or tag[0] == 'Z':  # momentalni povolene typy, pridat do budoucna pri zjisteni nejakych nestandartnich jmen, vylouceno (tag[0] == 'A' and tag[4] != 'U')
                a += 1
            if tag[0] != 'Z' and tag[0] != 'C' and tag[4] != '1' and tag[4] != 'X':  # zjistit, jestli neni ve spatnem padu
                bad_fall = True
        if a == len(title_tags_list) and not bad_fall:
            return 'P'

    # specialni produkt a organization override, pokud to dojelo sem
    prod = False
    komp = False
    some = False
    for title_lemma in title_lemmas_list:
        if re.match(o.re_product_title, title_lemma):
            prod = True
            some = True
        if re.match(o.re_company_title, title_lemma):
            komp = True
            some = True
    if some: # aby to neprobihalo pokazde
        if prod and komp:
            return 'R'
        elif prod:
            return 'R'
        else:
            return 'O'

    return ''

###########################################################################

def get_person_name(words_list, o):

    name = '' # promenna pro ulozeni jmena
    skip = False # bool pro preskakovani slov
    pre_word = ''  
    for word in words_list[0]: # zpracuj prvni vetu a dostan z ni jmeno. BETA: dostan synonyma jmen z druhe vety                       

        if skip: # pokud se bude preskakovat slovo, tak zjistit, jestli je to podstatne jmeno - pokud ne preskocit znovu
            if word[0][0] == 'N' and word[0][1] == 'N' and word[1].encode('utf-8') != 'být': # dalsi slovo je podstatne jmeno, preskoc ho
                skip = False                        
            continue
        if word[1].encode('utf-8') == 'být': # bere to vse do slova 'byt'
            break

        if word[0][0] == 'A': # pokud je prvni slovo adjektivum, nasleduje podstatne jmeno, ktere pujde pryc
            if re.match(o.re_person_title, pre_word): # pokud je to pridavne jmeno a pred nim _S | _Y, je to prijmeni, napr. 'bydzovsky'
                name += word[2]
                name += ' '
                pre_word = word[1]
                continue
            skip = True
            continue
        
        elif (word[0][14] != '8' and word[0][0] == 'N' and word[0][1] == 'N') or (word[0][0] == 'C' and re.match(o.re_person_title, pre_word)):                                         
        
            name += word[2]
            name += ' '
            pre_word = word[1]
            continue
                          
    o.f.write(name.encode('utf-8'))
    o.f.write('\t')

###########################################################################

def morph_fall(d, o): # 1. pady a pluraly

    result = o.morpho.analyze(d[2], o.morpho.GUESSER, o.lemmas) # BUG: pouze pokud uz neni v prvnim pade
    tag_template = d[0]
    tag_template = tag_template[:4] + '1' + tag_template[5:] # nahrazeni v tagu za prvni pad
    for lemma in o.lemmas:
        if d[0] == lemma.tag:
            d = (tag_template, d[1], lemma.lemma) #REDO tady byvalo d[2]
            return d
    return d

###########################################################################

def tokenize_title(title, o): # tokenizuje titulek, lepsi rozbor ve spojeni s prvni vetou - do budoucna rozvijet

    o.tokenizer.setText(title)
    if o.tokenizer.nextSentence(o.forms, o.tokens):
        o.tagger.tag(o.forms, o.lemmas)      

        title_lemmas_list = []
        title_tags_list = []

        for i in range(len(o.lemmas)):
        
            lemma = o.lemmas[i]
            token = o.tokens[i]
            
            title_tags_list.append(lemma.tag)
            title_lemmas_list.append(lemma.lemma)         

    return title_lemmas_list, title_tags_list                             

###########################################################################

def wiki_to_text(raw_text, title, o): # return 1 = chyba return 2 = blby obsah stranky return 0 = vypis slovo
    raw_text = re.sub(r'(?s)\[\[([^|]+?)\]\]', r'[[\1|\1]]', raw_text) # nahrad [[ ]]
    raw_text = removeParentheses(raw_text)
    parsed = parse_txt(raw_text, lang='cs')
    text = get_text(parsed, o)
    text = ''.join(text)    

    if text is not None and text != ' ':
        text = removeBraces(text)
        text = re.sub(r'\[\[.*\]\]', '', text) # zbav se vsech zbylych [[ ]]       
        
        o.tokenizer.setText(text)
        t = 0
        whole_sentence= '' # ostra prvni veta, kvuli pozdejsimu vypsani        
        subsentences_list = [] # seznam lemmovanych subsentences retezcu prvni vety  
        words_list = [] # seznam seznamu tuples (tag, lemma) prvni vety

        if o.tokenizer.nextSentence(o.forms, o.tokens): # pokud existuje prvni veta BUG: mozna prebytecna podminka
            o.tagger.tag(o.forms, o.lemmas)         

            words = []
            sentence = ''
    
            for i in range(len(o.lemmas)): # zpracovani konkretni vety
                
                lemma = o.lemmas[i]
                token = o.tokens[i]

                if lemma.lemma == ',' or lemma.lemma == ';' or lemma.lemma == ':':
                    words_list.append(words)                              
                    words = []
                    subsentences_list.append(sentence)
                    sentence = ''
                else:
                    word = (encode_entities(lemma.tag), encode_entities(lemma.lemma), encode_entities(text[token.start : token.start + token.length])) # word[0], word[1], word[2]
                    words.append(word)
                    sentence += encode_entities(text[t : token.start])
                    sentence += lemma.lemma

                # ukladani 1. vety do textoveho retezce, kvuli pozdejsimu pouziti ve vypisu
                original = encode_entities(text[token.start : token.start + token.length])
                whole_sentence += encode_entities(text[t : token.start]) 
                whole_sentence += original

                t = token.start + token.length
            # zpracovani posledni subsentence v prvni vete
            words_list.append(words)                              
            subsentences_list.append(sentence)         

            ## FILTROVANI V CELYCH SUBVETACH ##
            for subsentence in subsentences_list:
                if re.match(o.re_bad_sentence, subsentence):
                    return 2

            title_lemmas_list,title_tags_list = tokenize_title(title, o) # tokenizace titulku, vystup list tagu a list lemmat

            # presetup, pro zpresnovani vysledku pridavat podminky uz sem
            if re.match(o.re_event_title, title):
                setup = 'E'
            else:
                setup = get_setup(words_list, whole_sentence, title_lemmas_list, title_tags_list, o) # zjistit co je to za typ clanku, teoreticky          

            if setup != '':                         
                o.f.write(title.encode('utf-8'))
                o.f.write('\t')
                if setup == 'P':
                    get_person_name(words_list, o)
                else:
                    o.f.write(' \t')
                get_definitions(words_list,setup,title,whole_sentence,o)
                o.f.write(whole_sentence.encode('utf-8'))
                o.f.write('\n')

        return 0
    else:
        return 1

################################ FUNC_END #################################

# dodelat jen pokud to k necemu cele bude:
# zjistene problemy patek: jeden z + 2. pad = dodelat, prepsani pravidla o N17, celkovy override vsech funkci
# "ktery" na zacatku vety, pridat do filtru processing: zajmeno