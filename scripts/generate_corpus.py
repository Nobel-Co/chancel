#!/usr/bin/env python3
"""
Repo-facing entry point for the synthetic corpus generator.

The implementation moved into ``chancel.corpus`` so it ships inside the wheel --
``chancel demo`` and ``chancel gen-corpus`` need the generator from site-packages,
where ``scripts/`` does not exist. This file remains as the repo-facing entry
point: ``python scripts/generate_corpus.py`` still works, and ``tests/conftest.py``
puts ``scripts/`` on ``sys.path`` so ``from generate_corpus import generate``
keeps resolving here.

All corpus content is fictional and synthetic; see ``chancel.corpus`` for the
full attribution note.
"""

from chancel.corpus import Corpus, CorpusDoc, generate, main, write_corpus

__all__ = ["Corpus", "CorpusDoc", "generate", "main", "write_corpus"]


if __name__ == "__main__":
    main()
