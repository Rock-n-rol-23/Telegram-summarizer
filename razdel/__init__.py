
import re

class Sentence:
    def __init__(self, text, start=0, stop=None):
        self.text = text
        self.start = start
        self.stop = stop or len(text)

def sentenize(text):
    """Simple sentence splitting"""
    sentences = re.split(r'[.!?]+', text)
    result = []
    start = 0
    for sent in sentences:
        sent = sent.strip()
        if sent:
            result.append(Sentence(sent, start, start + len(sent)))
            start += len(sent) + 1
    return result
