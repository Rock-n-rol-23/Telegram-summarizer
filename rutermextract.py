
class TermExtractor:
    def __call__(self, text):
        words = text.split()[:20]
        terms = []
        for word in words:
            if len(word) > 3:
                term = type('Term', (), {'normalized': word, 'count': 1})()
                terms.append(term)
        return terms
