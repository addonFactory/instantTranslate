# Copyright (C) 2026 Beka Gozalishvili <beqaprogger@gmail.com>
# This file is covered by the GNU General Public License.
# See the file COPYING for more details.

import importlib
import pkgutil

from logHandler import log

from . import translators
from .translators.base import BaseTranslator

BASE_MODULE = BaseTranslator.__module__.rsplit(".", 1)[-1]


def discoverProviders():
    providers = {}
    for _finder, moduleName, _isPackage in pkgutil.iter_modules(translators.__path__):
        if moduleName == BASE_MODULE:
            continue
        try:
            module = importlib.import_module(".%s" % moduleName, translators.__name__)
        except Exception:
            log.exception(
                "Instant translate: cannot load the translators of %s" % moduleName
            )
            continue
        for member in vars(module).values():
            if not isinstance(member, type) or not issubclass(member, BaseTranslator):
                continue
            if member is BaseTranslator:
                continue
            providers[member.providerId] = member
    return dict(sorted(providers.items()))


DEFAULT_PROVIDER_ID = "google"

PROVIDERS = discoverProviders()
if not PROVIDERS:
    log.error("Instant translate: no translation service was found")
DEFAULT_PROVIDER = (
    DEFAULT_PROVIDER_ID
    if DEFAULT_PROVIDER_ID in PROVIDERS
    else next(iter(PROVIDERS), BaseTranslator.providerId)
)


def getProvider(providerId):
    return PROVIDERS.get(providerId) or PROVIDERS.get(DEFAULT_PROVIDER)


def nextProvider(providerId):
    providerIds = list(PROVIDERS)
    if not providerIds:
        return DEFAULT_PROVIDER
    try:
        index = providerIds.index(providerId)
    except ValueError:
        return DEFAULT_PROVIDER
    return providerIds[(index + 1) % len(providerIds)]
