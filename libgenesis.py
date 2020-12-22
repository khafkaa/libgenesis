#!/Users/kafka/.local/share/virtualenvs/libgen-cli-nZzWF5lY/bin/python3

'''CLI FOR LIBRARY GENESIS

   USAGE:

      ./libgenesis.py query -d /downloads -v title year lang

   ARGUMENTS:

      query: str: the title, author, subject you're looking for.
      -d:--directory str: the target directory for downloaded content
      -v :--view str: displays specified attributes of the search results

   VIEW ATTRIBUTES:

      id
      size
      title
      author
      lang  (language)
      pub   (publisher)
      year  (year published)
      pages (number of pages)
      ext   (file type (extension))
'''
import re
import sys
import json
import textwrap
from os import getenv
from os import system
from math import trunc
from argparse import ArgumentParser

import pandas as pd
from requests import exceptions
from requests_html import HTMLSession

from iter.accessories import cleave
from iter.accessories import chunks
from telecom.webtoolkit import download, DOWNLOADS
from telecom.webtoolkit import random_user_agent
from system.tools import apply_extension, sysinfo

HERE = getenv('libpath', '')
THERE = DOWNLOADS

with open(f'{HERE}libgenesis.conf', 'r') as configuration:
    CONFIG = json.load(configuration)

URLS = CONFIG['urls']
SESSION = HTMLSession()
USER_AGENT = random_user_agent('desktop')

SYNOPSIS_WRAPPER = textwrap.TextWrapper(width=105)
OMISSIONS = ('[1]', '[2]', '[3]', '[4]', '[5]', '[edit]')

APROMPT = CONFIG['prompts']['A']
BPROMPT = ''.join(CONFIG['prompts']['B'])
CPROMPT = CONFIG['prompts']['C']
DPROMPT = CONFIG['prompts']['D']
EPROMPT = CONFIG['prompts']['E']
FPROMPT = CONFIG['prompts']['F']

DISPLAYD = ['Title', 'Size', 'Extension']
VIEWOPTS = {
    'id': 'ID',
    'author': 'Authors(s)',
    'title': 'Title',
    'pub': 'Publisher',
    'year': 'Year',
    'pages': 'Pages',
    'lang': 'Language',
    'size': 'Size',
    'ext': 'Extension'
}


def render_args(opts):
    '''Argument Wrangling
    '''
    parser = ArgumentParser(prog='libgen', description='Library Genesis CLI')
    parser.add_argument(opts['q'][0], type=str, metavar=opts['q'][1], help=opts['q'][2])
    parser.add_argument('-d', '--directory', type=str, metavar=opts['d'][0], help=opts['d'][1])
    parser.add_argument('-v', '--view', nargs='+', type=str, metavar=opts['v'][0], help=opts['v'][1])
    arguments = vars(parser.parse_args())
    return arguments


def get_header(html):
    '''Returns the results page header text
    '''
    tables = html.find('table')
    return cleave(tables[1].text, '\n')


def gather_links(html, header):
    '''Collects the links to every page of search results
    '''
    links = []
    nextpage = [link for link in html.absolute_links if link.endswith('page=2')]
    if nextpage:
        link_template = nextpage[0][:-1]
        num_of_results = re.match(r'\d{1,6}', header).group(0)
        num_of_pages = trunc(int(num_of_results) / 50)
        page_numbers = list(range(1, num_of_pages + 2))
        for number in page_numbers:
            links.append(f'{link_template}{number}')
    return links


def extract_md5(link):
    '''Extract the book title hash from the book link
    '''
    pos = link.find('=') + 1
    return link[pos:]


def gather_books(html):
    '''Gather all titles and links from the current page...
    '''
    def gather_mirrors(elements, md5):
        mirrors = {}
        for element in elements:
            if md5 in element.attrs['href']:
                if not element.attrs['title']:
                    continue
                else:
                    mirrors.update({element.attrs['title']: element.attrs['href']})
        return mirrors

    table = html.find('.c')
    links = table[0].find('a')

    book_results = {}
    book_links = [link for link in links if 'book/index.php?md5=' in link.attrs['href']]

    for number, element in enumerate(book_links, 1):
        md5_hash = extract_md5(element.attrs['href'])
        result = {
            str(number): {
                'md5': md5_hash,
                'title': cleave(element.text, '\n'),
                'link': element.absolute_links.pop(),
                'mirrors': gather_mirrors(links, md5_hash)
            }}
        book_results.update(result)
    return book_results


def gather_data(html):
    table = html.find('.c')
    td = table[0].find('td')

    headers = [tag.text for tag in td[:9]]
    body = [tag.text for tag in td[11:] if tag.text not in OMISSIONS]

    chunked = chunks(body, 9)
    results = {item: [] for item in headers}
    for chunk in chunked:
        for number, item in enumerate(chunk):
            if number == 2:
                results[headers[number]].append(cleave(item, '\n'))
            else:
                results[headers[number]].append(item)

    return pd.DataFrame(results, index=range(1, len(results['Title']) + 1))


def harvest_data(html):
    head = get_header(html)
    books = gather_books(html)
    dataframe = gather_data(html)
    return {'header': head, 'df': dataframe, 'books': books}


def search(query):
    parameters = {'req': query.replace(' ', '+'), 'res': '50'}
    response = SESSION.get(URLS['3'], params=parameters, headers=USER_AGENT)
    response.raise_for_status()
    if response.ok:
        page1 = harvest_data(response.html)
        pages = gather_links(response.html, page1['header'])
        cache = {'1': page1}

    return cache, pages


def fetch_page(url, cache):
    pnum = url[-1] if re.search(r'\d{1,6}$', url) else '1'
    if pnum in cache:
        result = cache[pnum]
    else:
        page = SESSION.get(url, headers=USER_AGENT)
        result = harvest_data(page.html)
        cache.update({pnum: result})
    return result


def display_results(dataframe, pageheader, pagenumber):
    system('clear')
    print(f'PAGE {pagenumber}:')
    print(f'\n{pageheader.upper()}\n')
    # display(dataframe[['Author(s)', 'Title', 'Extension']])
    with pd.option_context('display.max_colwidth', 100):
        print(dataframe[DISPLAYD])


def select_title(selection, cache):

    md5 = cache['books'][selection]['md5']
    title = cache['books'][selection]['title']
    url = cache['books'][selection]['mirrors']['Libgen.lc']

    response = SESSION.get(url)

    html = response.html
    textobjs = [td for td in html.find('td') if 'colspan' in td.attrs]
    dload = [link for link in html.absolute_links if md5.lower() in link]

    system('clear')
    print(f'{title}\n')

    synopsis = textobjs[1].text
    if synopsis:
        print(SYNOPSIS_WRAPPER.fill(text=synopsis))
    else:
        print('No Synopsis')

    return dload[0], title.replace(' ', '-')


def app(book, local):
    '''The Application Interface
    '''
    try:
        page_number = '1'
        webcache, all_pages = search(book)

    except exceptions.RequestException as error:
        print(f'An error has occured.\n{error}')

    else:
        webpage = webcache[page_number]
        display_results(webpage['df'], webpage['header'], page_number)

        numpages = len(all_pages)
        prompt = APROMPT if numpages <= 1 else BPROMPT.format(numpages)

        while True:
            choice = input(prompt).strip()
            if choice in ('q', 'quit', 'exit'):
                system('clear')
                break

            elif choice.isdigit() and int(choice) in range(1, numpages + 1):
                page_number = choice
                pnumber = int(choice) - 1
                webpage = fetch_page(all_pages[pnumber], webcache)
                display_results(webpage['df'], webpage['header'], choice)

            elif choice in ('s', 'select'):
                choice = input(CPROMPT)
                dnlink, doc = select_title(choice, webcache[page_number])

                while True:
                    choice = input(DPROMPT).strip()
                    if choice not in ('y', 'yes', 'n', 'no'):
                        print('Invalid option. Please type y or n: ')

                    elif choice in ('n', 'no'):
                        display_results(webpage['df'], webpage['header'], page_number)
                        break

                    elif choice in ('y', 'yes'):
                        _ = download(dnlink, filename=doc)
                        apply_extension(f"/Users/kafka/Downloads/{doc}")
                        display_results(webpage['df'], webpage['header'], page_number)
                        break
            else:
                print('Invalid Option')
                continue


def main(query, path):
    '''The Main Loop
    '''
    while True:
        app(query, path)
        system('clear')
        choice = input(EPROMPT).strip()
        if choice not in ('y', 'yes', 'n', 'no'):
            print('Invalid option. Please type y or n: ')
        elif choice in ('n', 'no', 'q', 'quit', 'exit'):
            break
        elif choice in ('y', 'yes'):
            query = input(FPROMPT).strip()

    SESSION.close()
    system('clear')
    sys.exit()


if __name__ == '__main__':
    sysinfo()

    CLIOPTS = render_args(CONFIG['args'])
    DIRPATH = THERE if CLIOPTS['directory'] is None else CLIOPTS['directory']
    if CLIOPTS['view'] is not None:
        DISPLAYD = [value for key, value in VIEWOPTS.items() if key in CLIOPTS['view']]
    try:
        main(CLIOPTS['query'], DIRPATH)

    except KeyboardInterrupt:
        SESSION.close()
        system('clear')
        print('Session Interrupt\nHTTPS Socket Closed')
        sys.exit()
