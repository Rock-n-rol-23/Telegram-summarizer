
class Segmenter:
    pass

class MorphVocab:
    pass
    
class NewsEmbedding:
    pass
    
class NewsMorphTagger:
    def __init__(self, emb):
        pass
        
class NewsNERTagger:
    def __init__(self, emb):
        pass
        
class NewsSyntaxParser:
    def __init__(self, emb):
        pass
        
class NamesExtractor:
    pass
    
class DatesExtractor:
    def __call__(self, text):
        return []
        
class MoneyExtractor:
    def __call__(self, text):
        return []

class Doc:
    def __init__(self, text):
        self.text = text
        self.spans = []
    
    def segment(self, segmenter):
        pass
        
    def tag_morph(self, tagger):
        pass
        
    def tag_ner(self, tagger):
        pass
