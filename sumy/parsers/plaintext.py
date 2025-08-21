
class PlaintextParser:
    def __init__(self, text, tokenizer):
        self.text = text
        self.document = Document(text)
    
    @classmethod
    def from_string(cls, text, tokenizer):
        return cls(text, tokenizer)

class Document:
    def __init__(self, text):
        self.sentences = text.split('.')[:10]  # Simple split
