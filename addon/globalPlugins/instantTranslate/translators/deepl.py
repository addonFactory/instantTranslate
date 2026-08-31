# Copyright (C) 2026 Beka Gozalishvili <beqaprogger@gmail.com>
# This file is covered by the GNU General Public License.
# See the file COPYING for more details.

from uuid import uuid4

import addonHandler

from .base import BaseTranslator

addonHandler.initTranslation()

TRANSLATE_URL = "https://oneshot-free.www.deepl.com/v1/storefront/translate"
LANGUAGE_MODEL = "next-gen"
USAGE_TYPE = "Translate"
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko)"
    " Chrome/151.0.0.0 Safari/537.36 Edg/151.0.0.0"
)
HEADERS = {
    "Accept": "*/*",
    "Content-Type": "application/json",
    "Origin": "https://www.deepl.com",
    "Referer": "https://www.deepl.com/",
    "User-agent": USER_AGENT,
}

APP_INFORMATION = {
    "instance_id": str(uuid4()),
    "app_build": "Edge",
    "os": "Windows",
    "app_version": "any",
    "os_version": "any",
}


class Deepl(BaseTranslator):
    # Translators: the name of a translation service, presented when switching between services.
    providerName = _("DeepL")
    headers = HEADERS
    measureChunk = staticmethod(len)
    maxChunkSize = 500

    def translateChunk(self, chunk, langTo):
        body = {
            "text": [chunk],
            "source_lang": self.langFrom,
            "target_lang": langTo,
            "language_model": LANGUAGE_MODEL,
            "usage_type": USAGE_TYPE,
            "app_information": APP_INFORMATION,
        }
        response = self.session.post(TRANSLATE_URL, json=body).json()
        translations = (
            response.get("translations") if isinstance(response, dict) else None
        )
        if not translations:
            raise ValueError(
                "%s returned no translation: %r" % (self.providerId, response)
            )
        translation = translations[0] or {}
        detected = (
            translation.get("detected_source_language") or self.langFrom
        ).lower()
        return translation.get("text") or "", detected
