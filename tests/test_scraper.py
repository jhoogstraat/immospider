import scraper
from pages import fetch_options_for_url
from sources import immobilienscout24, immowelt
from scraper import extract_listings, scrape_listing_pages


def test_extracts_listing_from_embedded_json() -> None:
    html = """
    <html><head>
      <script id="__NEXT_DATA__" type="application/json">
      {"props":{"pageProps":{"resultListModel":{"realEstates":[{
        "id":"153902001",
        "url":"/expose/153902001",
        "title":"Helle Wohnung am Rhein",
        "address":{"street":"Rheinallee 1", "postcode":"40213", "city":"Düsseldorf"},
        "price":{"value":"1.250,50"},
        "livingSpace":{"value":"72,5"},
        "numberOfRooms":2.5,
        "companyName":"Beispiel Immobilien",
        "publishDate":"2026-06-03",
        "imageUrl":"/images/153902001.jpg"
      }]}}}}
      </script>
    </head></html>
    """

    listings = immobilienscout24.extract_listings(html)

    assert len(listings) == 1
    listing = listings[0]
    assert listing.id == "153902001"
    assert listing.url == "https://www.immobilienscout24.de/expose/153902001"
    assert listing.title == "Helle Wohnung am Rhein"
    assert listing.address == "Rheinallee 1, 40213, Düsseldorf"
    assert listing.price_eur == 1250.5
    assert listing.living_area_m2 == 72.5
    assert listing.rooms == 2.5
    assert listing.provider == "Beispiel Immobilien"
    assert listing.published == "2026-06-03"
    assert listing.source == "ImmobilienScout24"
    assert listing.source_color == 0x00AEEF
    assert listing.image_url == "https://www.immobilienscout24.de/images/153902001.jpg"
    assert listing.google_maps_url == "https://www.google.com/maps/search/?api=1&query=Rheinallee+1%2C+40213%2C+D%C3%BCsseldorf"


def test_extracts_listing_from_inline_result_list_model() -> None:
    html = """
    <script>
    window.IS24 = {
      resultListModel: {"searchResponseModel":{"resultlist.resultlist":{"resultlistEntries":[{"resultlistEntry":[{
        "@id":"167128433",
        "@publishDate":"2025-12-18T17:32:44.000+01:00",
        "resultlist.realEstate":{
          "@id":"167128433",
          "title":"URBAN VIBES & REAL COMFORT",
          "address":{"description":{"text":"Ackerstraße 133, Flingern Nord, Düsseldorf"}},
          "price":{"value":2200,"currency":"EUR"},
          "livingSpace":84.87,
          "numberOfRooms":3,
          "contactDetails":{"company":"Benini Intermediation & Consulting GmbH"}
        }
      }]}]}}}
    };
    </script>
    """

    listings = extract_listings(html, "https://www.immobilienscout24.de/search")

    assert len(listings) == 1
    listing = listings[0]
    assert listing.id == "167128433"
    assert listing.url == "https://www.immobilienscout24.de/expose/167128433"
    assert listing.title == "URBAN VIBES & REAL COMFORT"
    assert listing.address == "Ackerstraße 133, Flingern Nord, Düsseldorf"
    assert listing.price_eur == 2200.0
    assert listing.living_area_m2 == 84.87
    assert listing.rooms == 3.0
    assert listing.provider == "Benini Intermediation & Consulting GmbH"
    assert listing.published == "2025-12-18T17:32:44.000+01:00"


def test_deduplicates_json_listings_by_id() -> None:
    html = """
    <script type="application/json">
    {"resultListModel":{"realEstates":[
      {"id":"1", "url":"/expose/1", "title":"First"},
      {"id":"1", "url":"/expose/1", "title":"Duplicate"},
      {"id":"2", "url":"/expose/2", "title":"Second"}
    ]}}
    </script>
    """

    listings = extract_listings(html, "https://www.immobilienscout24.de/search")

    assert [listing.id for listing in listings] == ["1", "2"]
    assert [listing.title for listing in listings] == ["First", "Second"]


def test_falls_back_to_visible_listing_card() -> None:
    html = """
    <article>
      <a href="/expose/42?referrer=RESULT_LIST_LISTING">
        <h2>Altbauwohnung in Pempelfort</h2>
        980 € 61,4 m² 2 Zimmer
      </a>
    </article>
    """

    listings = extract_listings(html, "https://www.immobilienscout24.de/search")

    assert len(listings) == 1
    listing = listings[0]
    assert listing.id == "42"
    assert listing.title == "Altbauwohnung in Pempelfort"
    assert listing.price_eur == 980.0
    assert listing.living_area_m2 == 61.4
    assert listing.rooms == 2.0


def test_extracts_immowelt_listing_from_embedded_json() -> None:
    html = """
    <script id="__NEXT_DATA__" type="application/json">
    {"props":{"pageProps":{"classifiedSearch":{"classifieds":[{
      "classifiedId":"1a2b3c",
      "url":"/expose/1a2b3c",
      "headline":"Doppelhaushälfte in Düsseldorf",
      "location":{"city":"Düsseldorf", "postcode":"40213"},
      "purchasePrice":{"value":"649.000"},
      "livingArea":{"value":"124,5"},
      "numberOfRoomsValue":5,
      "providerName":"Immowelt Makler GmbH",
      "datePublished":"2026-06-02",
      "coverImage":{"url":"/images/1a2b3c.jpg"}
    }]}}}}
    </script>
    """

    listings = immowelt.extract_listings(
        html,
        base_url=(
            "https://www.immowelt.de/classified-search"
            "?distributionTypes=Buy,Buy_Auction,Compulsory_Auction"
            "&estateTypes=House,Apartment"
            "&locations=AD08DE2112"
            "&order=DateDesc"
        ),
    )

    assert len(listings) == 1
    listing = listings[0]
    assert listing.id == "1a2b3c"
    assert listing.url == "https://www.immowelt.de/expose/1a2b3c"
    assert listing.title == "Doppelhaushälfte in Düsseldorf"
    assert listing.address == "40213, Düsseldorf"
    assert listing.price_eur == 649000.0
    assert listing.living_area_m2 == 124.5
    assert listing.rooms == 5.0
    assert listing.provider == "Immowelt Makler GmbH"
    assert listing.published == "2026-06-02"
    assert listing.source == "Immowelt"
    assert listing.source_color == 0xF05A28
    assert listing.image_url == "https://www.immowelt.de/images/1a2b3c.jpg"
    assert listing.google_maps_url == "https://www.google.com/maps/search/?api=1&query=40213%2C+D%C3%BCsseldorf"


def test_scrapes_multiple_configured_pages(monkeypatch) -> None:
    pages = {
        "https://www.immobilienscout24.de/search": """
            <script type="application/json">
            {"resultListModel":{"realEstates":[{"id":"1", "url":"/expose/1", "title":"Scout"}]}}
            </script>
        """,
        "https://www.immowelt.de/classified-search?order=DateDesc": """
            <script type="application/json">
            {"classifieds":[{"classifiedId":"2", "url":"/expose/2", "headline":"Welt"}]}
            </script>
        """,
    }

    def fake_fetch_pages(
        urls,
        *,
        headless: bool,
        real_chrome: bool,
        solve_cloudflare: bool,
        concurrent_requests: int,
        concurrent_requests_per_domain: int,
    ):
        assert tuple(urls) == tuple(pages)
        assert headless is True
        assert real_chrome is False
        assert solve_cloudflare is False
        assert concurrent_requests == 8
        assert concurrent_requests_per_domain == 2
        return [
            scraper._FetchedPage(position=position, requested_url=url, final_url=url, html=pages[url])
            for position, url in enumerate(urls)
        ]

    monkeypatch.setattr(scraper, "_fetch_pages_concurrently", fake_fetch_pages)

    listings = scrape_listing_pages(tuple(pages), limit=10, concurrent_requests=8, concurrent_requests_per_domain=2)

    assert [listing.url for listing in listings] == [
        "https://www.immobilienscout24.de/expose/1",
        "https://www.immowelt.de/expose/2",
    ]


def test_fetch_pages_preserves_configured_page_order(monkeypatch) -> None:
    def fake_fetch_page(
        position: int,
        url: str,
        *,
        headless: bool,
        real_chrome: bool,
        solve_cloudflare: bool,
    ):
        assert headless is False
        assert real_chrome is True
        assert solve_cloudflare is True
        return scraper._FetchedPage(position=position, requested_url=url, final_url=url, html=url[-6])

    monkeypatch.setattr(scraper, "_fetch_page", fake_fetch_page)

    pages = scraper._fetch_pages_concurrently(
        ("https://a.test", "https://b.test"),
        headless=False,
        real_chrome=True,
        solve_cloudflare=True,
        concurrent_requests=6,
        concurrent_requests_per_domain=3,
    )

    assert [page.requested_url for page in pages] == ["https://a.test", "https://b.test"]



def test_page_fetch_options_control_browser_options() -> None:
    options = scraper._browser_options(
        page_options={"google_search": False, "solve_cloudflare": True},
        headless=True,
        real_chrome=False,
        solve_cloudflare=False,
    )

    assert options["google_search"] is False
    assert options["solve_cloudflare"] is True


def test_cli_cloudflare_flag_overrides_page_default() -> None:
    options = scraper._browser_options(
        page_options={"solve_cloudflare": False},
        headless=True,
        real_chrome=False,
        solve_cloudflare=True,
    )

    assert options["solve_cloudflare"] is True


def test_default_page_modules_define_fetch_options() -> None:
    assert fetch_options_for_url("https://www.immobilienscout24.de/search")["google_search"] is True
    assert fetch_options_for_url("https://www.immobilienscout24.de/search")["solve_cloudflare"] is False
    assert fetch_options_for_url("https://www.immowelt.de/classified-search?order=DateDesc")["google_search"] is False
    assert fetch_options_for_url("https://www.immowelt.de/classified-search?order=DateDesc")["solve_cloudflare"] is False
