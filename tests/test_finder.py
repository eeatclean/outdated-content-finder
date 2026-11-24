import contextlib
import io
import json
import os
import tempfile
import unittest
from datetime import date

from outdated_content_finder.cli import main
from outdated_content_finder.extract import extract, split_sentences
from outdated_content_finder.report import write_csv, write_json, write_markdown
from outdated_content_finder.signals import score_page, sentence_findings
from outdated_content_finder.sitemap import collect_pages, filter_pages, parse_sitemap, read_url_list

TODAY = date(2026, 11, 23)

ARTICLE = """<!doctype html><html><head>
<title>Best WordPress hosting in 2023 | Example</title>
<meta property="article:published_time" content="2023-02-10T08:00:00+00:00">
<meta property="article:modified_time" content="2023-03-01T08:00:00+00:00">
</head><body>
<header><nav><a href="/">Home</a> Updated for 2026!</nav></header>
<article>
<h1>Best WordPress hosting in 2023</h1>
<p>Currently, the Starter plan costs $2.95 per month. Our company was founded in 2015 in Lyon.</p>
<p>WordPress 6.1 is the latest version. Rated 4.5 stars by our readers.</p>
<p>Google will launch the new update in 2024. In 2022, 43% of all sites used WordPress.</p>
<p>The best free plugins of 2023 are listed below. Choose a host with good support.</p>
<p>Hosting matters for speed, security and support, so pick it carefully and test it before you move a
large site. This paragraph only adds enough words for the article region to be chosen as the main text,
which is what happens on a real blog post with several paragraphs of explanations, examples and advice.
We repeat the idea to reach the threshold: a fast host helps readers, a secure host protects them, and good
support saves hours when something breaks on a busy day. That is the whole point of this guide for you.</p>
</article>
<div class="comments"><p>Great post! In 2021 I paid $10 a month.</p></div>
<footer>© 2019 Example. All rights reserved.</footer>
</body></html>"""

SITEMAP_INDEX = """<?xml version="1.0" encoding="UTF-8"?>
<sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <sitemap><loc>https://example.com/post-sitemap.xml</loc></sitemap>
  <sitemap><loc>https://example.com/page-sitemap.xml</loc></sitemap>
</sitemapindex>"""
POST_SITEMAP = """<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <url><loc>https://example.com/blog/hosting/</loc><lastmod>2023-03-01</lastmod></url>
  <url><loc>https://example.com/wp-content/uploads/cover.jpg</loc></url>
  <url><loc>https://example.com/blog/hosting/</loc></url>
</urlset>"""
PAGE_SITEMAP = """<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <url><loc>https://example.com/about/</loc></url>
</urlset>"""


class SitemapTests(unittest.TestCase):
    def test_index_is_followed_and_duplicates_and_images_are_dropped(self):
        files = {
            "https://example.com/sitemap.xml": SITEMAP_INDEX,
            "https://example.com/post-sitemap.xml": POST_SITEMAP,
            "https://example.com/page-sitemap.xml": PAGE_SITEMAP,
        }
        pages = collect_pages("https://example.com/sitemap.xml", files.__getitem__)
        self.assertEqual([p.url for p in pages], ["https://example.com/blog/hosting/", "https://example.com/about/"])
        self.assertEqual(pages[0].lastmod, "2023-03-01")

    def test_broken_child_sitemap_is_reported_not_fatal(self):
        warnings = []
        files = {"https://example.com/sitemap.xml": SITEMAP_INDEX, "https://example.com/page-sitemap.xml": PAGE_SITEMAP}
        pages = collect_pages("https://example.com/sitemap.xml", files.__getitem__, warnings.append)
        self.assertEqual([p.url for p in pages], ["https://example.com/about/"])
        self.assertEqual(len(warnings), 1)

    def test_parse_sitemap_without_namespace_and_with_bom(self):
        kind, pages = parse_sitemap("﻿<urlset><url><loc> https://a.test/x </loc></url></urlset>")
        self.assertEqual(kind, "urlset")
        self.assertEqual(pages[0].url, "https://a.test/x")

    def test_url_list_and_filters(self):
        pages = read_url_list("# my list\nhttps://a.test/blog/1\n\nhttps://a.test/tag/x\nnot a url\n")
        self.assertEqual(len(pages), 2)
        self.assertEqual([p.url for p in filter_pages(pages, exclude="/tag/")], ["https://a.test/blog/1"])
        self.assertEqual(len(filter_pages(pages, include="/blog/", limit=5)), 1)


class ExtractTests(unittest.TestCase):
    def test_main_text_skips_menus_comments_and_footer(self):
        page = extract("https://example.com/blog/hosting/", ARTICLE)
        text = " ".join(page.sentences)
        self.assertIn("Starter plan costs $2.95", text)
        self.assertNotIn("Updated for 2026", text)
        self.assertNotIn("Great post", text)
        self.assertNotIn("All rights reserved", text)
        self.assertEqual(page.h1, "Best WordPress hosting in 2023")
        self.assertEqual(page.modified, "2023-03-01")
        self.assertEqual(page.published, "2023-02-10")

    def test_json_ld_dates(self):
        html = ('<html><head><script type="application/ld+json">{"@graph":[{"@type":"BlogPosting",'
                '"datePublished":"2024-01-05","dateModified":"2025-06-30T10:00:00Z"}]}</script></head>'
                "<body><p>Hello.</p></body></html>")
        page = extract("https://a.test/", html)
        self.assertEqual((page.published, page.modified), ("2024-01-05", "2025-06-30"))

    def test_sentences_do_not_split_inside_numbers(self):
        self.assertEqual(split_sentences("WordPress 6.1 is out. It costs $2.95 now."),
                         ["WordPress 6.1 is out.", "It costs $2.95 now."])


class SignalTests(unittest.TestCase):
    def kinds(self, sentence):
        return {f.kind for f in sentence_findings(sentence, 2026)}

    def test_past_year_presented_as_current(self):
        self.assertIn("past_year_as_current", self.kinds("The best free plugins of 2023 are listed below."))
        self.assertIn("past_year_as_current", self.kinds("Les meilleurs outils SEO en 2024 sont gratuits."))

    def test_future_event_in_a_past_year(self):
        self.assertIn("future_in_past", self.kinds("Google will launch the new update in 2024."))
        self.assertIn("future_in_past", self.kinds("La nouvelle norme sera obligatoire en 2025."))

    def test_history_is_left_alone(self):
        self.assertEqual(self.kinds("Our company was founded in 2015 in Lyon."), set())
        self.assertEqual(self.kinds("Apple released the first iPad in 2010."), set())
        self.assertEqual(self.kinds("Depuis 2018, nous publions un guide chaque mois."), set())
        self.assertEqual(self.kinds("A guide written in 2019 can still be useful today."), set())
        self.assertEqual(self.kinds("We ran it on two travel guides from 2012 and a new SEO article."), {"dated"})

    def test_current_and_future_years_are_not_flagged(self):
        self.assertEqual(self.kinds("The best tools of 2026 are listed below."), set())
        self.assertEqual(self.kinds("The law applies from 2027."), set())

    def test_versions(self):
        self.assertIn("version", self.kinds("WordPress 6.1 is the latest version."))
        self.assertIn("version", self.kinds("Install version 2 of the plugin."))
        self.assertIn("version", self.kinds("It runs on iOS 16 and Android 13."))
        self.assertNotIn("version", self.kinds("Rated 4.5 stars by our readers."))
        self.assertNotIn("version", self.kinds("Step 3 is the hardest one."))

    def test_prices_and_plans(self):
        self.assertIn("price", self.kinds("Currently, the Starter plan costs $2.95 per month."))
        self.assertIn("price", self.kinds("L'abonnement coûte 9,99 € par mois."))
        self.assertIn("price", self.kinds("There is a free plan for small teams."))
        self.assertNotIn("price", self.kinds("We have 12 people on the team."))
        self.assertNotIn("price", self.kinds("Review the whole site once per year, 150 pages per month."))

    def test_time_relative_wording(self):
        self.assertIn("time_relative", self.kinds("This is currently the fastest option."))
        self.assertIn("time_relative", self.kinds("C'est actuellement l'option la plus rapide."))
        self.assertNotIn("time_relative", self.kinds("This option is fast."))

    def test_years_inside_other_numbers_are_ignored(self):
        self.assertEqual(self.kinds("Call 0800 2023 456 or read section 12020."), set())
        self.assertEqual(self.kinds("Published on 2023-05-01 by the team."), set())


class ScoreTests(unittest.TestCase):
    def test_page_score_and_signals(self):
        page = extract("https://example.com/blog/hosting/", ARTICLE)
        score = score_page(page, "", TODAY)
        self.assertEqual(score.count("year_in_title"), 1)
        self.assertEqual(score.count("future_in_past"), 1)
        self.assertGreaterEqual(score.count("past_year_as_current"), 1)
        self.assertEqual(score.count("price"), 1)
        self.assertGreaterEqual(score.count("version"), 1)
        self.assertEqual(score.last_changed, "2023-03-01")
        self.assertEqual(score.age_months, 44)
        self.assertGreater(score.score, 10)
        # The founding year and the copyright line never count.
        self.assertFalse(any("founded" in f.sentence for f in score.findings))

    def test_time_relative_weighs_more_on_old_pages(self):
        html = "<html><body><article><p>This is currently the fastest option.</p></article></body></html>"
        page = extract("https://a.test/", html)
        recent = score_page(page, "2026-10-01", TODAY)
        old = score_page(page, "2024-01-01", TODAY)
        self.assertEqual(recent.score, 1)
        self.assertEqual(old.score, 2)

    def test_reports(self):
        page = extract("https://example.com/blog/hosting/", ARTICLE)
        scores = [score_page(page, "", TODAY)]
        csv_out, json_out, md_out = io.StringIO(), io.StringIO(), io.StringIO()
        write_csv(scores, csv_out)
        write_json(scores, json_out)
        write_markdown(scores, md_out)
        self.assertIn("https://example.com/blog/hosting/", csv_out.getvalue())
        self.assertEqual(json.loads(json_out.getvalue())[0]["counts"]["future_in_past"], 1)
        self.assertIn("Future event dated in a past year", md_out.getvalue())


class CliTests(unittest.TestCase):
    def test_local_url_list_with_fake_network(self):
        from outdated_content_finder import fetch

        pages = {"https://example.com/blog/hosting/": ARTICLE}
        original = fetch.Fetcher.get
        fetch.Fetcher.get = lambda self, url: pages[url]
        try:
            with tempfile.TemporaryDirectory() as tmp:
                urls = os.path.join(tmp, "urls.txt")
                with open(urls, "w") as handle:
                    handle.write("https://example.com/blog/hosting/\n")
                out_csv = os.path.join(tmp, "out.csv")
                with contextlib.redirect_stdout(io.StringIO()):
                    code = main([urls, "--quiet", "--delay", "0", "--csv", out_csv])
                self.assertEqual(code, 0)
                with open(out_csv) as handle:
                    self.assertIn("hosting", handle.read())
        finally:
            fetch.Fetcher.get = original


if __name__ == "__main__":
    unittest.main()
