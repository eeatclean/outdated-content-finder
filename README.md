# outdated-content-finder

**Find the blog articles most likely to contain outdated facts, starting from the sitemap.**

A broken link checker won't catch a wrong version number. The page loads, the link works, and the article still tells readers to install version 2 of a tool that is now on version 5. This small command line tool reads every page listed in your sitemap. Then it ranks the pages by how many time-sensitive claims they contain, so you know which articles to check first.

It runs on Python 3.8 or newer and has no dependencies. It makes no AI calls, so it costs nothing to run.

```text
$ outdated-content-finder https://example.com --include /blog/ --markdown report.md

  # score  age   title  stale future    ver  price    rel   year  url
  1    18   3y       1      1      1      1      1      2      1  https://example.com/blog/best-wordpress-hosting/
  2    15   2y       0      0      0      5      1      1      1  https://example.com/blog/php-requirements/
```

## How to find outdated content on a blog

The usual advice is "start with your oldest posts". That's a fair default, but it misses a lot. A two-year-old opinion piece can still be right. A three-month-old tutorial that quotes a price or a version can already be wrong.

When we checked 23 of our own articles by hand, only 1 correction in 4 came from a fact that had changed since publication. The rest were errors from day one, or claims that were never tied to a date. So this tool ranks pages by **risk**, not by age:

1. **List every page.** It reads `robots.txt`, finds the sitemap, follows sitemap indexes and skips images and PDFs.
2. **Read the main text.** It keeps the article and leaves out menus, headers, footers, sidebars and comments.
3. **Flag time-sensitive sentences.** It looks for the patterns below, in English, French, Spanish and German.
4. **Rank the pages.** Each signal has a weight, and the pages with the highest score come first.

| Signal | Example | Weight |
| --- | --- | --- |
| Past year in the title | "Best WordPress hosting in 2023" | 3 |
| Past year presented as current | "The best free plugins of 2023 are listed below." | 3 |
| Future event dated in a past year | "Google will launch the update in 2024." | 3 |
| Version or model number | "WordPress 6.1", "iOS 16", "version 2" | 2 |
| Price or plan | "$2.95 per month", "9,99 €", "free plan" | 2 |
| Time-relative wording | "currently", "the latest version", "this year" | 1 (2 if the page hasn't changed for 12 months) |
| Other dated reference | "In 2022, 43% of sites used WordPress." | 1 |

Some years are left alone on purpose. A founding date ("founded in 2015"), a release in the past ("Apple released the first iPad in 2010") or the year an article was written describe history, and history doesn't drift. The current year and future years are never flagged either.

## What it doesn't do

This tool finds **suspects**. It doesn't tell you whether a sentence is wrong, because only the source can do that.

For each flagged sentence, find the page that actually owns the fact: the vendor's release notes, the pricing page, the standard body's site or the regulator's page. A blog that summarized it, or a chatbot answer, is not a source. Two rules keep this step honest:

1. **No source, no change.** If you can't find an official page that proves the sentence is wrong, leave it alone and note it.
2. **Record the source next to the fix.** Six months later, you will want to know why the sentence changed.

In our own audit, 62 of the 68 corrections that needed a source were proven by the official page of the vendor or the public body involved. In other words, the proof is almost always out there. You just have to go and read it. [We published the full results here.](https://eeatclean.com/blog/what-we-found-checking-our-own-articles.html)

## Install

```bash
git clone https://github.com/eeatclean/outdated-content-finder.git
cd outdated-content-finder
pip install .
```

You can also run it without installing it: `python3 -m outdated_content_finder https://example.com` from the cloned folder.

## Usage

```bash
# A whole site: the sitemap is found through robots.txt or the usual paths
outdated-content-finder https://example.com

# A sitemap URL, only the blog, at most 200 pages, with reports
outdated-content-finder https://example.com/post-sitemap.xml --include /blog/ --limit 200 \
  --csv pages.csv --markdown report.md

# Your own list of URLs, one per line
outdated-content-finder urls.txt --json findings.json
```

| Option | What it does |
| --- | --- |
| `--include REGEX` / `--exclude REGEX` | Keep or skip URLs, for example `--exclude '/(tag|category|author)/'` |
| `--limit N` | Analyze at most N pages, in sitemap order |
| `--csv FILE` | One row per page, with its score, last known change and counts |
| `--json FILE` | Every finding, with the full sentence |
| `--markdown FILE` | The top pages and the sentences to check first |
| `--top N` | Rows shown in the terminal and the Markdown report (default 20) |
| `--year YYYY` | Treat this as the current year |
| `--delay SECONDS` | Wait between requests (default 1 second) |
| `--ignore-robots` | Skip `robots.txt` rules. Use it only on a site you own. |

The Markdown report lists the sentences behind each score. Here is [an example](examples/sample-report.md).

## Be polite

The tool waits one second between requests and follows `robots.txt` by default. Some sites block every script, even polite ones. When that happens, the tool tells you why it got no page, and you can pass a list of URLs exported from your CMS instead.

## Limits

- The patterns are simple on purpose, so you can read them in [`signals.py`](outdated_content_finder/signals.py) and adapt them. Expect some noise. For example, an article that *explains* "Best laptops 2023" titles will be flagged.
- The last known change comes from the page's own metadata first, then from the sitemap's `lastmod`. Many CMSs update `lastmod` when a sidebar changes, so a recent date doesn't mean the facts were checked.
- Pages that need JavaScript to show their text are read as they arrive from the server.

## When you have more pages than time

Checking each claim against its source is the slow part. It takes hours per article, and that is why we built [EEATClean](https://eeatclean.com/). It does step 3 for you: it checks the key claims of the articles you pick against current sources, and it shows each correction next to the source that proves it.

## Tests

```bash
python3 -m unittest discover -s tests
```

The tests use sample pages and don't touch the network.

## License

MIT. See [LICENSE](LICENSE).
