from typing import List, Optional
import collections
import logging
logger = logging.getLogger(__name__)

class TrieNode:
    def __init__(self):
        self.children = collections.defaultdict(TrieNode)
        self.end: Optional[List[str]] = None

class Trie:
    def __init__(self):
        """
        Initialize your data structure here.
        """
        self.root = TrieNode()

    def insert(self, key: str, terminator: str) -> None:
        """
        Inserts a word into the trie.
        """
        current = self.root
        for letter in key:
            current = current.children[letter]

        if not current.end:
            current.end = [terminator]
        else:
            current.end.append(terminator)

        logger.info(f"item '{key}' inserted to trie, with terminator: {current.end}")

    def search(self, key: str) -> Optional[List[str]]:
        """
        Returns terminator for word if it exists in trie
        """
        current = self.root
        for letter in key:
            current = current.children.get(letter)
            if current is None:
                logger.debug(f"could not find key {key} in trie")
                return None

        logger.debug(f"key exists in trie, with terminator: {current.end}") 
        return current.end
    
    def list_keys(self, node: TrieNode) -> List[str]:
        """starting at the root or a provided node,
        list all keys in the trie
        """
        keys = []

        for key, value in node.children.items():
            if not value.end:
                r = self.list_keys(value)
                for el in r:
                    keys.append(key + el)
            else:
                keys.append(key)
        
        return keys
        
    def starts_with(self, prefix: str):
        """
        Returns if there is any word in the trie that starts with the given prefix.
        """
        current = self.root 
        
        for letter in prefix:
            current = current.children.get(letter)
            if not current:
                return None
        
        # drill to end of trie from current node.
        # add prefix to all returned values
        matches = self.list_keys(current)
        return [prefix + item for item in matches]
