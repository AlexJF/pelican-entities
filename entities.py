#!/usr/bin/env python
# encoding: utf-8

"""
Entities Plugin for Pelican
===========================

A new generator for the Pelican static site generator that replaces the default
Page and Article generators, allowing the definition of arbitrary content types,
aka, entity types (e.g: projects, events) and associated indices/direct
templates.

Each entity type may have its own set of settings that override the ones
defined globally.
"""

from __future__ import unicode_literals, print_function
import os
import math
import random
import logging

from blinker import signal
from codecs import open
from collections import defaultdict
from functools import partial
from itertools import chain, groupby
from operator import attrgetter, itemgetter

import pelican.contents as contents
from pelican.utils import process_translations
from pelican.readers import METADATA_PROCESSORS

from pelican import signals, generators
import copy
import calendar
import six

logger = logging.getLogger(__name__)

entity_generator_init = signal('entity_generator_init')
entity_subgenerator_init = signal('entity_subgenerator_init')
entity_subgenerator_pretaxonomy = signal('entity_subgenerator_pretaxonomy')
entity_generator_finalized = signal('entity_generator_finalized')
entity_subgenerator_finalized = signal('entity_subgenerator_finalized')
entity_subgenerator_writer_finalized = signal('entity_subgenerator_writer_finalized')
entity_subgenerator_write_entity = signal('entity_subgenerator_write_entity')
entity_writer_finalized = signal('entity_writer_finalized')
entity_subgenerator_preread = signal('entity_subgenerator_preread')
entity_subgenerator_context = signal('entity_subgenerator_context')


def get_generators(pelican_object):
    return EntityGenerator


def register():
    signals.get_generators.connect(get_generators)


def attribute_list_sorter(attr_list, reverse=False):
    return lambda objects: objects.sort(key=attrgetter(*attr_list), reverse=reverse)


def get_default_entity_type_settings(entity_type):
    entity_type_upper = entity_type.upper()
    entity_type_lower = entity_type.lower()

    settings = {}
    settings['SUBGENERATOR_CLASS'] = EntityGenerator.EntitySubGenerator
    settings['PATHS'] = [entity_type_lower]
    settings['EXCLUDES'] = []

    settings['MANDATORY_PROPERTIES'] = ['title', 'date']
    settings['DEFAULT_TEMPLATE'] = entity_type_lower

    settings['FEED_ATOM'] = None
    settings['FEED_RSS'] = None
    settings['FEED_ALL_ATOM'] = None
    settings['FEED_ALL_RSS'] = None
    settings['CATEGORY_FEED_ATOM'] = None
    settings['CATEGORY_FEED_RSS'] = None
    settings['AUTHOR_FEED_ATOM'] = None
    settings['AUTHOR_FEED_RSS'] = None
    settings['TRANSLATION_FEED_ATOM'] = None
    settings['TRANSLATION_FEED_RSS'] = None

    settings['SORTER'] = attribute_list_sorter(["date"], True)

    settings[entity_type_upper + '_URL'] = entity_type_lower + '/{slug}.html'
    settings[entity_type_upper + '_SAVE_AS'] = os.path.join(entity_type_lower, '{slug}.html')
    settings[entity_type_upper + '_LANG_URL'] = entity_type_lower + '/{slug}-{lang}.html'
    settings[entity_type_upper + '_LANG_SAVE_AS'] = os.path.join(entity_type_lower, '{slug}-{lang}.html')
    #settings['ARCHIVE_TEMPLATE'] = 'archive'
    #settings['CATEGORY_TEMPLATE'] = 'category'
    settings['CATEGORY_URL'] = entity_type_lower + '/category/{slug}.html'
    settings['CATEGORY_SAVE_AS'] = os.path.join(entity_type_lower, 'category', '{slug}.html')
    #settings['TAG_TEMPLATE'] = 'tag'
    settings['TAG_URL'] = entity_type_lower + '/tag/{slug}.html'
    settings['TAG_SAVE_AS'] = os.path.join(entity_type_lower, 'tag', '{slug}.html')
    #settings['AUTHOR_TEMPLATE'] = 'author'
    settings['AUTHOR_URL'] = entity_type_lower + '/author/{slug}.html'
    settings['AUTHOR_SAVE_AS'] = os.path.join(entity_type_lower, 'author', '{slug}.html')

    settings['DIRECT_TEMPLATES'] = []
    settings['PAGINATED_DIRECT_TEMPLATES'] = []

    return settings


class Entity(contents.Page):
    pass


def EntityFactory(name, mandatory_properties, default_template, BaseClass=Entity):
    base_mandatory_properties = ['title']
    mandatory_properties = set(base_mandatory_properties + mandatory_properties)
    newclass = type(str(name), (BaseClass,),
                    {'type': name,
                     'mandatory_properties': mandatory_properties,
                     'default_template': default_template})
    return newclass


class EntityGenerator(generators.Generator):
    """ Generate entity pages for each defined entity type."""

    class EntitySubGenerator(generators.CachingGenerator):
        """Generate entity pages for a specific entity type."""

        def __init__(self, entity_type, *args, **kwargs):
            """initialize properties"""
            self.entity_type = entity_type
            self.entities = []  # only entities in default language
            self.translations = []
            self.tags = defaultdict(list)
            self.categories = defaultdict(list)
            self.authors = defaultdict(list)
            self.drafts = [] # only drafts in default language
            self.drafts_translations = []
            self.sort_attrs = []
            super(EntityGenerator.EntitySubGenerator, self).__init__(*args, cache_name=entity_type, **kwargs)
            entity_subgenerator_init.send(self)

        def generate_feeds(self, writer):
            """Generate the feeds from the current context, and output files."""

            if self.settings.get('FEED_ATOM'):
                writer.write_feed(self.entities, self.context,
                                  self.settings['FEED_ATOM'])

            if self.settings.get('FEED_RSS'):
                writer.write_feed(self.entities, self.context,
                                  self.settings['FEED_RSS'],
                                  feed_type='rss')

            if (self.settings.get('FEED_ALL_ATOM')
                    or self.settings.get('FEED_ALL_RSS')):
                all_entities = list(self.entities)
                for content in self.entities:
                    all_entities.extend(content.translations)
                all_entities.sort(key=attrgetter(*self.sort_attrs), reverse=True)

                if self.settings.get('FEED_ALL_ATOM'):
                    writer.write_feed(all_entities, self.context,
                                      self.settings['FEED_ALL_ATOM'])

                if self.settings.get('FEED_ALL_RSS'):
                    writer.write_feed(all_entities, self.context,
                                      self.settings['FEED_ALL_RSS'],
                                      feed_type='rss')

            for cat, entities in self.categories:
                if self.settings.get('CATEGORY_FEED_ATOM'):
                    writer.write_feed(entities, self.context,
                                      self.settings['CATEGORY_FEED_ATOM']
                                      % cat.slug, feed_title=cat.name)

                if self.settings.get('CATEGORY_FEED_RSS'):
                    writer.write_feed(entities, self.context,
                                      self.settings['CATEGORY_FEED_RSS']
                                      % cat.slug, feed_title=cat.name,
                                      feed_type='rss')

            for auth, entities in self.authors:
                if self.settings.get('AUTHOR_FEED_ATOM'):
                    writer.write_feed(entities, self.context,
                                      self.settings['AUTHOR_FEED_ATOM']
                                      % auth.slug, feed_title=auth.name)

                if self.settings.get('AUTHOR_FEED_RSS'):
                    writer.write_feed(entities, self.context,
                                      self.settings['AUTHOR_FEED_RSS']
                                      % auth.slug, feed_title=auth.name,
                                      feed_type='rss')

            if (self.settings.get('TAG_FEED_ATOM')
                    or self.settings.get('TAG_FEED_RSS')):
                for tag, entities in self.tags.items():
                    if self.settings.get('TAG_FEED_ATOM'):
                        writer.write_feed(entities, self.context,
                                          self.settings['TAG_FEED_ATOM']
                                          % tag.slug, feed_title=tag.name)

                    if self.settings.get('TAG_FEED_RSS'):
                        writer.write_feed(entities, self.context,
                                          self.settings['TAG_FEED_RSS'] % tag.slug,
                                          feed_title=tag.name, feed_type='rss')

            if (self.settings.get('TRANSLATION_FEED_ATOM')
                    or self.settings.get('TRANSLATION_FEED_RSS')):
                translations_feeds = defaultdict(list)
                for entity in chain(self.entities, self.translations):
                    translations_feeds[content.lang].append(entity)

                for lang, items in translations_feeds.items():
                    if self.settings.get('TRANSLATION_FEED_ATOM'):
                        writer.write_feed(
                            items, self.context,
                            self.settings['TRANSLATION_FEED_ATOM'] % lang)
                    if self.settings.get('TRANSLATION_FEED_RSS'):
                        writer.write_feed(
                            items, self.context,
                            self.settings['TRANSLATION_FEED_RSS'] % lang,
                            feed_type='rss')

        def generate_entities(self, write):
            """Generate the entities."""
            for entity in chain(self.translations, self.entities):
                entity_subgenerator_write_entity.send(self, content=entity)
                write(entity.save_as, self.get_template(entity.template),
                      self.context, url=entity.url, entity=entity,
                      entity_type=self.entity_type,
                      override_output=hasattr(entity, 'override_save_as'))

        def generate_period_archives(self, write):
            """Generate per-year, per-month, and per-day archives."""

            if not self.settings.get('ARCHIVE_TEMPLATE', None):
                return

            if 'date' not in self.settings.get('MANDATORY_PROPERTIES'):
                logger.warning("Cannot generate period archives on entity type "
                               "without mandatory date property: %s",
                               self.entity_type)
                return

            template = self.get_template(\
                self.settings['ARCHIVE_TEMPLATE'])

            period_save_as = {
                'year': self.settings['YEAR_ARCHIVE_SAVE_AS'],
                'month': self.settings['MONTH_ARCHIVE_SAVE_AS'],
                'day': self.settings['DAY_ARCHIVE_SAVE_AS'],
            }

            period_date_key = {
                'year': attrgetter('date.year'),
                'month': attrgetter('date.year', 'date.month'),
                'day': attrgetter('date.year', 'date.month', 'date.day')
            }

            def _generate_period_archives(entities, key, save_as_fmt):
                """Generate period archives from `dates`, grouped by
                `key` and written to `save_as`.
                """
                dates = sorted(entities, key=attrgetter('date'),
                               reverse=self.context['NEWEST_FIRST_ARCHIVES'])
                # `dates` is already sorted by date
                for _period, group in groupby(dates, key=key):
                    archive = list(group)
                    # arbitrarily grab the first date so that the usual
                    # format string syntax can be used for specifying the
                    # period archive dates
                    date = archive[0].date
                    save_as = save_as_fmt.format(date=date)
                    context = self.context.copy()

                    if key == period_date_key['year']:
                        context["period"] = (_period,)
                    else:
                        month_name = calendar.month_name[_period[1]]
                        if not six.PY3:
                            month_name = month_name.decode('utf-8')
                        if key == period_date_key['month']:
                            context["period"] = (_period[0],
                                                 month_name)
                        else:
                            context["period"] = (_period[0],
                                                 month_name,
                                                 _period[2])

                    write(save_as, template, context,
                          key=key,
                          url=save_as.replace('\\', '/'),
                          dates=archive, entity_type=self.entity_type)

            for period in 'year', 'month', 'day':
                save_as = period_save_as[period]
                if save_as:
                    key = period_date_key[period]
                    _generate_period_archives(self.entities, key, save_as)

        def generate_direct_templates(self, write):
            """Generate direct templates pages"""
            PAGINATED_TEMPLATES = self.settings['PAGINATED_DIRECT_TEMPLATES']
            for template in self.settings['DIRECT_TEMPLATES']:
                paginated = {}
                if template in PAGINATED_TEMPLATES:
                    paginated = {'entities': self.entities}
                save_as = self.settings.get("%s_SAVE_AS" % template.upper(),
                                            '%s.html' % template)
                if not save_as:
                    continue

                write(save_as, self.get_template(template),
                      self.context, entity_type=self.entity_type, paginated=paginated,
                      direct=True, url=save_as.replace('\\', '/'),
                      page_name=os.path.splitext(save_as)[0])

        def generate_tags(self, write):
            """Generate Tags pages."""

            if not self.settings.get('TAG_TEMPLATE', None):
                return

            tag_template = self.get_template(self.settings['TAG_TEMPLATE'])
            for tag, entities in self.tags.items():
                write(tag.save_as, tag_template, self.context, tag=tag,
                      entities=entities, paginated={'entities': entities},
                      entity_type=self.entity_type,
                      url=tag.url,
                      page_name=tag.page_name, all_entities=self.entities)

        def generate_categories(self, write):
            """Generate category pages."""

            if not self.settings.get('CATEGORY_TEMPLATE', None):
                return

            category_template = self.get_template(self.settings['CATEGORY_TEMPLATE'])
            for cat, entities in self.categories:
                write(cat.save_as, category_template, self.context,
                      category=cat, entities=entities,
                      paginated={'entities': entities},
                      entity_type=self.entity_type,
                      url=cat.url,
                      page_name=cat.page_name, all_entities=self.entities)

        def generate_authors(self, write):
            """Generate Author pages."""

            if not self.settings.get('Author_TEMPLATE', None):
                return

            author_template = self.get_template(self.settings['AUTHOR_TEMPLATE'])
            for aut, entities in self.authors:
                write(aut.save_as, author_template, self.context,
                      author=aut, entities=entities,
                      paginated={'entities': entities},
                      entity_type=self.entity_type,
                      url=author.url,
                      page_name=aut.page_name, all_entities=self.entities)

        def generate_drafts(self, write):
            """Generate drafts pages."""
            for draft in chain(self.drafts_translations, self.drafts):
                write(draft.save_as, self.get_template(draft.template),
                    self.context, entity=draft,
                    override_output=hasattr(draft, 'override_save_as'),
                    url=draft.url,
                    all_entities=self.entities)

        def generate_pages(self, writer):
            """Generate the pages on the disk"""
            write = partial(writer.write_file,
                            relative_urls=self.settings['RELATIVE_URLS'])

            # to minimize the number of relative path stuff modification
            # in writer, articles pass first
            self.generate_entities(write)
            self.generate_period_archives(write)
            self.generate_direct_templates(write)

            # and subfolders after that
            self.generate_tags(write)
            self.generate_categories(write)
            self.generate_authors(write)
            self.generate_drafts(write)

        def generate_context(self):
            """Add the entities into the shared context"""

            all_entities = []
            all_drafts = []
            for f in self.get_files(
                    self.settings['PATHS'],
                    exclude=self.settings['EXCLUDES']):
                entity_or_draft = self.get_cached_data(f, None)
                if entity_or_draft is None:
                    entity_class = EntityFactory(
                        self.entity_type,
                        self.settings['MANDATORY_PROPERTIES'],
                        self.settings['DEFAULT_TEMPLATE'])
                    try:
                        entity_or_draft = self.readers.read_file(
                            base_path=self.path, path=f, content_class=entity_class,
                            context=self.context,
                            preread_signal=entity_subgenerator_preread,
                            preread_sender=self,
                            context_signal=entity_subgenerator_context,
                            context_sender=self)
                    except Exception as e:
                        logger.error('Could not process %s\n%s', f, e,
                            exc_info=self.settings.get('DEBUG', False))
                        self._add_failed_source_path(f)
                        continue

                    if not contents.is_valid_content(entity_or_draft, f):
                        self._add_failed_source_path(f)
                        continue

                    known_statuses = ("published", "draft")

                    if entity_or_draft.status.lower() not in known_statuses:
                        logger.warning("Unknown status '%s' for file %s, skipping it.",
                                       entity_or_draft.status, f)
                        self._add_failed_source_path(f)
                        continue

                    self.cache_data(f, entity_or_draft)

                if entity_or_draft.status.lower() == "published":
                    all_entities.append(entity_or_draft)
                else:
                    all_drafts.append(entity_or_draft)

                self.add_source_path(entity_or_draft)

            self.entities, self.translations = process_translations(
                all_entities)
            self.drafts, self.drafts_translations = \
                process_translations(all_drafts)

            sorter = self.settings["SORTER"]
            sorter(self.entities)

            entity_subgenerator_pretaxonomy.send(self)

            for entity_or_draft in self.entities:
                # only main entities are listed in categories and tags
                # not translations
                if hasattr(entity_or_draft, 'category'):
                    self.categories[entity_or_draft.category].append(entity_or_draft)
                if hasattr(entity_or_draft, 'tags'):
                    for tag in entity_or_draft.tags:
                        self.tags[tag].append(entity_or_draft)
                for author in getattr(entity_or_draft, 'authors', []):
                    self.authors[author].append(entity_or_draft)

            # and generate the output :)

            # order the categories per name
            self.categories = list(self.categories.items())
            self.categories.sort(
                reverse=self.settings['REVERSE_CATEGORY_ORDER'])

            self.authors = list(self.authors.items())
            self.authors.sort()

            self.save_cache()
            self.readers.save_cache()
            entity_subgenerator_finalized.send(self)

        def generate_output(self, writer):
            self.generate_feeds(writer)
            self.generate_pages(writer)
            entity_subgenerator_writer_finalized.send(self, writer=writer)

        class SubGeneratorContext:
            def __init__(self, **kwds):
                self.__dict__.update(kwds)

        def get_context(self):
            context = self.SubGeneratorContext()
            context.type = self.entity_type
            context.entities = self.entities
            context.translations = self.translations
            context.tags = self.tags
            context.categories = self.categories
            context.authors = self.authors
            context.drafts = self.drafts
            context.drafts_translations = self.drafts_translations

            return context

    def __init__(self, *args, **kwargs):
        """ Initialize properties """
        self.entities = []
        self.entity_types = {}
        super(EntityGenerator, self).__init__(*args, **kwargs)

        entity_types_settings = self.settings['ENTITY_TYPES']

        for entity_type, custom_entity_type_settings in entity_types_settings.items():
            logger.debug("Found entity type: %s" % entity_type)
            entity_type_settings = get_default_entity_type_settings(entity_type)
            entity_type_settings.update(custom_entity_type_settings)

            custom_settings = self.settings

            entity_type_settings = copy.copy(self.settings)
            entity_type_settings.update(get_default_entity_type_settings(entity_type))
            entity_type_settings.update(custom_entity_type_settings)

            generator_factory = entity_type_settings.pop("SUBGENERATOR_CLASS")
            if not callable(generator_factory):
                import importlib
                module_name, class_name = generator_factory.rsplit('.', 1)
                module = importlib.import_module(module_name)
                generator_factory = getattr(module, class_name)

            kwargs['settings'] = entity_type_settings

            entity_type_generator = generator_factory(entity_type, *args, **kwargs)
            self.entity_types[entity_type] = entity_type_generator
        entity_generator_init.send(self)

    def generate_context(self):
        context_update_fields = ['entity_types']

        for entity_type, generator in self.entity_types.items():
            logger.debug("Generating context for entities of type {0}".format(generator.entity_type))
            generator.generate_context()
            setattr(self, entity_type.lower(), generator.get_context())
            context_update_fields.append(entity_type.lower())

            self.entities += generator.entities

        logger.debug("Context update fields: %s" % str(context_update_fields))

        self._update_context(context_update_fields)
        entity_generator_finalized.send(self)

    def generate_output(self, writer):
        for generator in self.entity_types.values():
            logger.debug("Generating output for entities of type {0}".format(generator.entity_type))
            generator.generate_output(writer)

        entity_writer_finalized.send(self, writer=writer)
