#!/usr/bin/python3
# -*- coding: UTF-8 -*-


from codecs import open
from contextlib import closing
from datetime import timedelta
from json import loads, load, dump
from re import match, IGNORECASE
from sys import stderr
from time import sleep
from typing import List, Dict
from urllib.error import URLError
from urllib.request import urlopen

from config import Config
from data_set import DataSet
from filter import Filter, FilterDecoder, ReplaceCatEntry
from utils import Utils


class ChannelHandler:

    @staticmethod
    def get_channel_list(data_set: DataSet) -> List[Dict[str, str]]:
        json_url: str = data_set.json_url
        resp_encoding: str = data_set.resp_encoding

        for attempt_number in range(1, Config.JSON_SRC_MAX_ATTEMPTS):
            print('Retrieving JSON file, attempt', attempt_number, 'of', Config.JSON_SRC_MAX_ATTEMPTS, end='\n\n')

            if attempt_number > 1:
                Utils.wait_for_internet()

            try:
                with closing(urlopen(json_url, timeout=Config.CONN_TIMEOUT)) as response_raw:
                    response = response_raw.read().decode(resp_encoding)

                channel_list = loads(response).get('channels')

                return channel_list
            except URLError as url_error:
                print('Can not retrieve JSON file.', file=stderr)
                print('Error:', url_error, file=stderr)

                if attempt_number < Config.JSON_SRC_MAX_ATTEMPTS:
                    print('Sleeping for', timedelta(seconds=Config.JSON_SRC_REQ_DELAY), 'before trying again.',
                          end='\n\n',
                          file=stderr)
                    sleep(Config.JSON_SRC_REQ_DELAY)
                else:
                    print('Raising an exception.', end='\n\n', file=stderr)
                    raise

        return [{'name': '', 'url': '', 'cat': ''}]

    @staticmethod
    def replace_categories(channel_list, data_set: DataSet) -> List[Dict[str, str]]:
        with closing(open(data_set.filter_file_name, 'r', data_set.filter_file_encoding)) as filter_file:
            filter_contents_raw: Dict[str, list] = load(filter_file)

        filter_contents: Filter = FilterDecoder.decode(filter_contents_raw)

        replace_cats: List[ReplaceCatEntry] = filter_contents.replace_cats

        replaced = False

        for replace_cat in replace_cats:
            target_name = replace_cat.for_name
            target_category = replace_cat.to_cat

            for channel in channel_list:
                current_name = channel.get('name')
                current_category = channel.get('cat')

                if match(target_name, current_name, IGNORECASE) and not current_category == target_category:
                    channel['cat'] = target_category
                    replaced = True
                    print('Replaced category for channel "' + current_name + '", from "' + current_category + '" to "' +
                          target_category + '".')

        if replaced:
            print('')

        return channel_list

    @staticmethod
    def is_channel_allowed(channel, data_set: DataSet) -> bool:
        with closing(open(data_set.filter_file_name, 'r', data_set.filter_file_encoding)) as filter_file:
            filter_contents = load(filter_file)

        exclude_cats = filter_contents.get('exclude_cats')

        if len(exclude_cats) > 0:
            categories_filter = '(' + ')|('.join(exclude_cats) + ')'

            if match(categories_filter, channel.get('cat'), IGNORECASE):
                return False

        exclude_names = filter_contents.get('exclude_names')

        if len(exclude_names) > 0:
            names_filter = '(' + ')|('.join(exclude_names) + ')'

            if match(names_filter, channel.get('name'), IGNORECASE):
                return False

        return True

    @staticmethod
    def write_entry(channel, data_set: DataSet, out_file) -> None:
        out_file_format = data_set.out_file_format

        entry = out_file_format \
            .replace('{CATEGORY}', channel.get('cat')) \
            .replace('{NAME}', channel.get('name')) \
            .replace('{CONTENT_ID}', channel.get('url'))

        out_file.write(entry)

    @staticmethod
    def clean_filter(src_channel_list, data_set: DataSet) -> None:
        with closing(open(data_set.filter_file_name, 'r', data_set.filter_file_encoding)) as filter_file:
            filter_contents = load(filter_file)

            cleaned = False  # TODO: Too deep nesting from this point?

            # Clean "replace_cats"
            replace_cats = filter_contents.get('replace_cats')

            for replace_cat in replace_cats[:]:
                name_in_filter = replace_cat.get('for_name')

                if all(not match(name_in_filter, src_channel.get('name'), IGNORECASE) for src_channel in
                       src_channel_list):
                    replace_cats.remove(replace_cat)
                    cleaned = True
                    print('Not found any match for category replacement: "' + name_in_filter + '" in source,',
                          'removed from filter.')

            if cleaned:
                cleaned = False
                print('')

            # Clean "exclude_cats"
            exclude_cats = filter_contents.get('exclude_cats')

            for exclude_cat in exclude_cats[:]:
                if all(not match(exclude_cat, src_channel.get('cat'), IGNORECASE) for src_channel in src_channel_list):
                    exclude_cats.remove(exclude_cat)
                    cleaned = True
                    print('Not found any match for category exclusion: "' + exclude_cat + '" in source,',
                          'removed from filter.')

            if cleaned:
                cleaned = False
                print('')

            # Clean "exclude_names"
            exclude_names = filter_contents.get('exclude_names')

            for exclude_name in exclude_names[:]:
                if all(not match(exclude_name, src_channel.get('name'), IGNORECASE) for src_channel in
                       src_channel_list):
                    exclude_names.remove(exclude_name)
                    cleaned = True
                    print('Not found any match for name exclusion: "' + exclude_name + '" in source,',
                          'removed from filter.')

            if cleaned:
                print('')

        # Write changes
        with closing(open(data_set.filter_file_name, 'w', data_set.filter_file_encoding)) as filter_file:
            dump(filter_contents, filter_file, indent=2, ensure_ascii=False)
