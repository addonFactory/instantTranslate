# Copyright (C) 2013 - 2024 Mesar Hameed <mhameed@src.gnome.org>, Beka gozalishvili <beqaprogger@gmail.com>
# This file is covered by the GNU General Public License.
# See the file COPYING for more details.

import json
import os
import re
import threading
from time import time
from urllib.parse import urlencode

from logHandler import log

from ..httpClient import DEFAULT_TIMEOUT, Session

# Each group has to be a class of possible breaking points for the writing script.
# Usually this is the major syntax marks, such as: full stop, comma, exclaim, question, etc.
ARABIC_BREAKS = "[،؛؟]"
# Thanks to Talori in the NVDA irc room:
# U+3000 to U+303F, U+FE10 to U+FE1F, U+FE30 to U+FE6F, U+FF01 to U+FF60
CHINESE_BREAKS = "[　-〿︐-︟︰-﹯！-｠]"
LATIN_BREAKS = r"[.,!?;:]"
LINE_ENDING_PATTERN = re.compile(r"\r\n|\r")

LINE_RUN_PATTERN = re.compile(r"(\n+)")

SPLIT_PATTERN = re.compile("|".join((ARABIC_BREAKS, CHINESE_BREAKS, LATIN_BREAKS)))


def cachePath(fileName):
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), fileName)


def encodedLength(text):
    return len(urlencode({"q": text})) - 2


def splitChunks(text, chunkSize, measure=len):
    sizes = [0]
    for char in text:
        sizes.append(sizes[-1] + measure(char))

    def sizeOf(start, end):
        return sizes[end] - sizes[start]

    def emit(start, end):
        while start < end:
            stop = start + 1
            while stop < end and sizeOf(start, stop + 1) <= chunkSize:
                stop += 1
            yield text[start:stop]
            start = stop

    pos = potentialPos = 0
    for splitMark in SPLIT_PATTERN.finditer(text):
        if sizeOf(pos, splitMark.start() + 1) < chunkSize:
            potentialPos = splitMark.start()
            continue
        yield from emit(pos, potentialPos + 1)
        pos = potentialPos + 1
        potentialPos = splitMark.start()
    yield from emit(pos, len(text))


def normalizeLineEndings(text):
    found = LINE_ENDING_PATTERN.search(text)
    return LINE_ENDING_PATTERN.sub("\n", text), found.group() if found else "\n"


def splitLineRuns(text):
    return [part for part in LINE_RUN_PATTERN.split(text) if part]


def splitEdges(text):
    stripped = text.strip()
    if not stripped:
        return text, "", ""
    return text[: len(text) - len(text.lstrip())], stripped, text[len(text.rstrip()) :]


class LanguageCache:
    def __init__(self, path, ttl, fetch, getContext=None):
        self.path = path
        self.ttl = ttl
        self.fetch = fetch
        self.getContext = getContext or (lambda: "")
        self._lock = threading.RLock()
        self._refreshing = False
        self._languages = None
        self._timestamp = 0
        self._context = None
        self._load()

    def _load(self):
        try:
            with open(self.path, "r", encoding="utf-8") as cacheFile:
                cached = json.load(cacheFile)
        except FileNotFoundError:
            return
        except Exception:
            log.warning(
                "Instant translate: unreadable language cache %s" % self.path,
                exc_info=True,
            )
            return
        self._languages = cached.get("languages")
        self._timestamp = cached.get("timestamp", 0)
        self._context = cached.get("context")

    def _save(self):
        cached = {
            "timestamp": self._timestamp,
            "context": self._context,
            "languages": self._languages,
        }
        try:
            with open(self.path, "w", encoding="utf-8") as cacheFile:
                json.dump(
                    cached, cacheFile, ensure_ascii=False, indent="\t", sort_keys=True
                )
        except Exception:
            log.warning(
                "Instant translate: cannot write language cache %s" % self.path,
                exc_info=True,
            )

    @property
    def isStale(self):
        if self._languages is None:
            return True
        if self._context != self.getContext():
            return True
        return abs(time() - self._timestamp) > self.ttl

    def get(self, refresh=True):
        with self._lock:
            if refresh and self.isStale:
                self.refreshInBackground()
            return self._languages

    def refresh(self):
        try:
            languages = self.fetch()
        except Exception:
            log.warning(
                "Instant translate: cannot fetch the supported languages", exc_info=True
            )
            return False
        if not languages:
            log.warning(
                "Instant translate: the supported languages request returned nothing"
            )
            return False
        with self._lock:
            self._languages = languages
            self._timestamp = time()
            self._context = self.getContext()
            self._save()
        return True

    def refreshInBackground(self):
        with self._lock:
            if self._refreshing:
                return
            self._refreshing = True

        def run():
            try:
                self.refresh()
            finally:
                with self._lock:
                    self._refreshing = False

        threading.Thread(
            target=run, daemon=True, name="InstantTranslateLanguages"
        ).start()


class BaseTranslator(threading.Thread):
    providerId = "base"
    providerName = "base"
    headers = {}
    languageCache = None
    maxChunkSize = 12000
    measureChunk = staticmethod(encodedLength)
    legacyCodes = {"iw": "he", "jw": "jv"}
    timeout = DEFAULT_TIMEOUT

    def __init__(
        self,
        langFrom,
        langTo,
        text,
        langSwap=None,
        chunkSize=None,
        onSuccess=None,
        onError=None,
        onProgress=None,
        onFinished=None,
    ):
        super().__init__(name="InstantTranslate%s" % type(self).__name__, daemon=True)
        if langFrom != "auto" and langSwap is not None:
            raise ValueError(
                "langSwap=%r is only meaningful with langFrom='auto', got langFrom=%r"
                % (langSwap, langFrom)
            )
        self.langFrom = langFrom
        self.langTo = langTo
        self.text, self.lineEnding = normalizeLineEndings(text)
        self.langSwap = langSwap
        self.chunkSize = chunkSize or self.maxChunkSize
        self.onSuccess = onSuccess
        self.onError = onError
        self.onProgress = onProgress
        self.onFinished = onFinished
        self.chunks = []
        for part in splitLineRuns(self.text):
            if part.startswith("\n"):
                self.chunks.append(part)
            else:
                self.chunks.extend(splitChunks(part, self.chunkSize, self.measureChunk))
        self.completedChunks = 0
        self.translation = ""
        self.detectedLanguage = ""
        self.error = False
        self._stopEvent = threading.Event()
        self.session = Session(headers=self.headers, timeout=self.timeout)

    @property
    def totalChunks(self):
        return len(self.chunks)

    @property
    def remainingChunks(self):
        return self.totalChunks - self.completedChunks

    @property
    def percentDone(self):
        if not self.totalChunks:
            return 100
        return int(round(self.completedChunks * 100.0 / self.totalChunks))

    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)
        if "providerId" in cls.__dict__:
            return
        cls.providerId = cls.__name__.lower()

    def stop(self):
        self._stopEvent.set()
        try:
            self.session.close()
        except Exception:
            log.debug(
                "Instant translate: cannot abort the request of %s" % self.providerId,
                exc_info=True,
            )

    @property
    def shouldStop(self):
        return self._stopEvent.is_set()

    def run(self):
        try:
            self._translateChunks()
        finally:
            self._reportOutcome()

    def _translateChunks(self):
        isFirst = True
        for index, chunk in enumerate(self.chunks):
            if self.shouldStop:
                return
            leading, stripped, trailing = splitEdges(chunk)
            if not stripped:
                self.translation += chunk
                self.completedChunks = index + 1
                self._report(self.onProgress)
                continue
            try:
                translation, detected = self.translateChunk(stripped, self.langTo)
                self.detectedLanguage = self.legacyCodes.get(detected, detected)
                if isFirst and self.shouldSwap():
                    self.langTo = self.langSwap
                    translation, detected = self.translateChunk(stripped, self.langTo)
                isFirst = False
                translation = leading + translation + trailing
            except Exception:
                if self.shouldStop:
                    return
                log.exception(
                    "Instant translate: %s cannot translate %r"
                    % (self.providerId, chunk)
                )
                self.error = True
                return
            self.translation += translation
            self.completedChunks = index + 1
            self._report(self.onProgress)
        if self.lineEnding != "\n":
            self.translation = self.translation.replace("\n", self.lineEnding)

    def _reportOutcome(self):
        if not self.shouldStop:
            self._report(self.onError if self.error else self.onSuccess)
        self._report(self.onFinished)

    def _report(self, callback):
        if callback is None:
            return
        try:
            callback(self)
        except Exception:
            log.exception("Instant translate: a %s callback failed" % self.providerId)

    def shouldSwap(self):
        return (
            self.langSwap is not None
            and self.langFrom == "auto"
            and self.detectedLanguage == self.langTo
        )

    def translateChunk(self, chunk, langTo):
        raise NotImplementedError
