
class TextRankSummarizer:
    def __call__(self, document, sentence_count):
        return document.sentences[:sentence_count]
