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

###################################### VAR ################################

idx = 0

re_bad_sentence = re.compile(u'.*(moci_\^\(mít_možnost_\[něco_dělat\]\)\|být\s+zkratka|(hodně-2|několik)\s+význam|další\s+význam|hodně-2\s+místo|být\s+jednoznačný|hodně-2\s+místo-1_\^\(fyzické_umístění\)).*', re.UNICODE)

bad_title = re.compile(u'^(Nápověda|Wikipedie|Kategorie|Šablona|MediaWiki|Wikipedista|Modul|Portál):\s*[\w]+', re.UNICODE)
bad_date = re.compile(u'^\d\d?\d?\d?\s*(př\.\s*n\.\s*l\.\s*)?$', re.UNICODE)
bad_title_dir = re.compile(u'^[\w]+\s*\((rozcestník|příjmení)\)', re.UNICODE)
bad_title_list = re.compile(u'[S,s]eznam\s+[\w]+', re.UNICODE)
bad_letter = re.compile(u'^\w$', re.UNICODE)

re_event_title = re.compile(u'.*[M,m]istrovství.*', re.UNICODE)
re_product_title = re.compile(u'\w+_;R(_,t)?', re.UNICODE)
re_company_title = re.compile(u'\w+_;K(_,t)?', re.UNICODE)
re_person_title = re.compile(u'\w+_;[S,Y](_,t)?', re.UNICODE)
re_company = re.compile(u'^(společnost_\^\(\*3ý\)|firma|organizace|korporace|federace|koncern|církev|klub|pakt|podnik|spolek|aliance|iniciativa|družstvo|sdružení_\^\(\*3it\))$', re.UNICODE)
re_connect = re.compile(u'který|jenž_\^\(který\.\.\.\[ve_vedl\._větě\]\)|jenž_\^\(který_\[ve_vedl\.větě\]\)', re.UNICODE)
re_product_maker = re.compile(u'společnost_\^\(\*3ý\)|firma', re.UNICODE)
re_location = re.compile(u'^(město|obec|ulice|stát-1_\^\(státní_útvar\)|kraj|okres|republika|region|země|ostrov|řeka|potok|jezero|moře|poloostrov|záliv|průliv|pleso|kontinent|území|městys|knížectví|království|vádí_,t|údolí|prefektura)$', re.UNICODE)
re_art = re.compile(u'^(dílo_\^\(umělecké,_vědecké,\.\.\.\)|píseň|kniha|socha|balada|opera|opereta|album|trilogie|báseň|povídka|bible|deník|skladba|hymna|thriller|kresba|malba|olejomalba|román|komiks|obraz|komedie|film|seriál|drama|čtrnáctideník|týdeník|časopis|měsíčník-2\_\^\(časopis\))$', re.UNICODE)
re_event = re.compile(u'^(událost_,a_\^\(\*3ý\)|revoluce|akce|expedice|mise|šampionát|soutěž|mistrovství)$', re.UNICODE)
re_product = re.compile(u'^(výrobek|služba|produkt|model|značka|licence|série|hra_\^\(dětská;_v_divadle;\.\.\.\))$', re.UNICODE)

MW_NS = "{http://www.mediawiki.org/xml/export-0.10/}"

IGNORE = (nodes.ImageLink, nodes.Table, nodes.CategoryLink)

f = open('/tmp/xplsek03/result','w')
rr = open('/tmp/xplsek03/err','w')

if len(sys.argv) < 3:
    sys.stderr.write('Usage: %s tagger_file dict_file\n' % sys.argv[0])
    sys.exit(1)

tagger = Tagger.load(sys.argv[1])
if not tagger:
    sys.stderr.write("Cannot load tagger from file '%s'\n" % sys.argv[1])
    sys.exit(1)
forms = Forms()
lemmas = TaggedLemmas()
lemmas_forms = TaggedLemmasForms()
tokens = TokenRanges()
tokenizer = tagger.newTokenizer()
if tokenizer is None:
    sys.stderr.write("No tokenizer is defined for the supplied model!")
    sys.exit(1)
morpho = Morpho.load(sys.argv[2])
if not morpho:
  sys.stderr.write("Cannot load dictionary from file '%s'\n" % sys.argv[2])
  sys.exit(1)

class Args:
    def __init__(self, IGNORE, tokenizer, forms, tokens, tagger, lemmas, re_bad_sentence, re_connect, re_product_maker, re_company, re_art, re_person_title, re_event_title, re_location, re_event, re_product, f, morpho, rr, re_product_title, re_company_title):
        self.IGNORE = IGNORE
        self.tokenizer = tokenizer
        self.forms = forms
        self.tokens = tokens
        self.tagger = tagger
        self.lemmas = lemmas
        self.re_bad_sentence = re_bad_sentence
        self.re_connect = re_connect
        self.re_product_maker = re_product_maker
        self.re_company = re_company
        self.re_art = re_art
        self.re_person_title = re_person_title
        self.re_event_title = re_event_title
        self.re_location = re_location
        self.re_event = re_event
        self.re_product = re_product
        self.f = f
        self.morpho = morpho
        self.rr = rr
        self.re_product_title = re_product_title
        self.re_company_title = re_company_title

o = Args(IGNORE, tokenizer, forms, tokens, tagger, lemmas, re_bad_sentence, re_connect, re_product_maker, re_company, re_art, re_person_title, re_event_title, re_location, re_event, re_product, f, morpho, rr, re_product_title, re_company_title)

from wikifunc import *

# zpracovani obsahu dumpu

for title, raw_text in parse_dump('/tmp/xplsek03/wiki.xml.bz2', MW_NS):
    if title_sux(title, bad_title, bad_title_dir, bad_title_list, bad_date, bad_letter): 
        continue
    else:
        print str(idx)      
        rtn = wiki_to_text(raw_text, title, o)
        idx += 1

del o
f.close
rr.close
