from typing import List

class RecursiveCharacterTextSplitter:
    def __init__(self, chunk_size: int = 1000, chunk_overlap: int = 200):
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap

    def split_text(self, text: str) -> List[str]:
        if not text:
            return []
        
        chunks = []
        start = 0
        text_len = len(text)
        
        while start < text_len:
            end = start + self.chunk_size
            if end >= text_len:
                chunks.append(text[start:])
                break
            
            # Simple splitting: find the nearest space before cut
            # Ideally use more sophisticated separators like langchain
            sub = text[start:end]
            # Try to find last space
            last_space = sub.rfind(' ')
            if last_space == -1:
                # No space, hard break
                chunks.append(sub)
                start = end - self.chunk_overlap
            else:
                chunks.append(sub[:last_space])
                start = start + last_space + 1 - self.chunk_overlap
                # Adjust start to handle overlap properly? 
                # Actually, simpler: just advance by (length - overlap)
                # But we want to backtrack from the break point.
                # If we broke at `last_space` (relative to start), the length is `last_space`.
                # Next chunk should start at `start + last_space - overlap`?
                # No, overlap is defined as number of common characters.
                # So if we outputted N chars, we advance by N - overlap.
                
                # Let's fix this logic to be simpler and robus
                chunk_len = last_space
                # start of next chunk
                start = start + chunk_len - self.chunk_overlap
                if start < 0: start = 0 # should not happen

        return chunks
