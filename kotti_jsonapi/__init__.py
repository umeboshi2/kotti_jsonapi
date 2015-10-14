# -*- coding: utf-8 -*-

"""
Created on 2015-10-14
:author: Joseph Rawson (joseph.rawson.works@gmail.com)
"""

from kotti.resources import File
from pyramid.i18n import TranslationStringFactory

_ = TranslationStringFactory('kotti_jsonapi')


def kotti_configure(settings):
    """ Add a line like this to you .ini file::

            kotti.configurators =
                kotti_jsonapi.kotti_configure

        to enable the ``kotti_jsonapi`` add-on.

    :param settings: Kotti configuration dictionary.
    :type settings: dict
    """

    settings['pyramid.includes'] += ' kotti_jsonapi'
    settings['kotti.alembic_dirs'] += ' kotti_jsonapi:alembic'
    settings['kotti.available_types'] += ' kotti_jsonapi.resources.CustomContent'
    settings['kotti.fanstatic.view_needed'] += ' kotti_jsonapi.fanstatic.css_and_js'
    File.type_info.addable_to.append('CustomContent')


def includeme(config):
    """ Don't add this to your ``pyramid_includes``, but add the
    ``kotti_configure`` above to your ``kotti.configurators`` instead.

    :param config: Pyramid configurator object.
    :type config: :class:`pyramid.config.Configurator`
    """

    config.add_translation_dirs('kotti_jsonapi:locale')
    config.add_static_view('static-kotti_jsonapi', 'kotti_jsonapi:static')

    config.scan(__name__)
