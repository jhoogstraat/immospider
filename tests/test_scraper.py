from types import SimpleNamespace

import scraper
from pages import fetch_options_for_url
from sources import immobilienscout24, immowelt, kleinanzeigen, source_for_url
from scraper import scrape_listing_page_groups


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

    listings = source_for_url("https://www.immobilienscout24.de/search").extract(
        html, "https://www.immobilienscout24.de/search"
    )

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

    listings = source_for_url("https://www.immobilienscout24.de/search").extract(
        html, "https://www.immobilienscout24.de/search"
    )

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

    listings = source_for_url("https://www.immobilienscout24.de/search").extract(
        html, "https://www.immobilienscout24.de/search"
    )

    assert len(listings) == 1
    listing = listings[0]
    assert listing.id == "42"
    assert listing.title == "Altbauwohnung in Pempelfort"
    assert listing.price_eur == 980.0
    assert listing.living_area_m2 == 61.4
    assert listing.rooms == 2.0



def test_extracts_immobilienscout24_visible_card_with_scrapling_selectors() -> None:
    html = """
    <div data-testid="result-list-entry">
      <a href="/expose/153902002?referrer=RESULT_LIST_LISTING">
        <h2>Loft am Medienhafen</h2>
      </a>
      <span data-testid="address">Speditionstraße 8, 40221 Düsseldorf</span>
      <span class="result-list-entry__primary-criterion">1.450 €</span>
      <span class="result-list-entry__primary-criterion">80 m²</span>
      <span class="result-list-entry__primary-criterion">2 Zimmer</span>
      <span data-testid="provider">Scout Makler GmbH</span>
      <time data-testid="date">Heute</time>
      <img data-src="/images/153902002.jpg" />
    </div>
    """

    listings = immobilienscout24.extract_listings(html)

    assert len(listings) == 1
    listing = listings[0]
    assert listing.id == "153902002"
    assert listing.title == "Loft am Medienhafen"
    assert listing.address == "Speditionstraße 8, 40221 Düsseldorf"
    assert listing.price_eur == 1450.0
    assert listing.living_area_m2 == 80.0
    assert listing.rooms == 2.0
    assert listing.provider == "Scout Makler GmbH"
    assert listing.published == "Heute"
    assert listing.image_url == "https://www.immobilienscout24.de/images/153902002.jpg"

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


def test_extracts_immowelt_visible_card_with_scrapling_selectors() -> None:
    html = """
    <section data-test="estate-card">
      <a href="/expose/5f6g7h">
        <h2>Stadthaus mit Garten</h2>
      </a>
      <div data-test="address">40545 Düsseldorf-Oberkassel</div>
      <strong>899.000 €</strong>
      <span>142 m²</span>
      <span>5 Zimmer</span>
      <span data-test="provider">Immowelt Partner</span>
      <span data-test="date">Gestern</span>
      <img src="/images/5f6g7h.jpg" />
    </section>
    """

    listings = immowelt.extract_listings(html)

    assert len(listings) == 1
    listing = listings[0]
    assert listing.id == "5f6g7h"
    assert listing.url == "https://www.immowelt.de/expose/5f6g7h"
    assert listing.title == "Stadthaus mit Garten"
    assert listing.address == "40545 Düsseldorf-Oberkassel"
    assert listing.price_eur == 899000.0
    assert listing.living_area_m2 == 142.0
    assert listing.rooms == 5.0
    assert listing.provider == "Immowelt Partner"
    assert listing.published == "Gestern"
    assert listing.image_url == "https://www.immowelt.de/images/5f6g7h.jpg"


def test_extracts_kleinanzeigen_listing_from_visible_card() -> None:
    html = """
    <li class="ad-listitem fully-clickable-card">
      <article class="aditem" data-adid="3425718263"
               data-href="/s-anzeige/moebilierte-2-zimmer-wohnung-in-pempelfort-zur-untermiete/3425718263-203-2082">
        <div class="aditem-image">
          <a href="/s-anzeige/moebilierte-2-zimmer-wohnung-in-pempelfort-zur-untermiete/3425718263-203-2082">
            <img src="https://img.kleinanzeigen.de/api/v1/prod-ads/images/00/example?rule=$_2.AUTO"
                 alt="Möbilierte 2 Zimmer Wohnung in Pempelfort zur Untermiete Düsseldorf - Pempelfort Vorschau" />
          </a>
        </div>
        <div class="aditem-main">
          <div class="aditem-main--top">
            <div class="aditem-main--top--left">
              <i class="icon icon-small icon-pin-gray" aria-hidden="true"></i> 40477 Pempelfort
            </div>
            <div class="aditem-main--top--right">
              <i class="icon icon-small icon-calendar-open" aria-hidden="true"></i> Heute, 08:42
            </div>
          </div>
          <div class="aditem-main--middle">
            <h2 class="text-module-begin">
              <a class="ellipsis"
                 href="/s-anzeige/moebilierte-2-zimmer-wohnung-in-pempelfort-zur-untermiete/3425718263-203-2082">Möbilierte 2 Zimmer Wohnung in Pempelfort zur Untermiete</a>
            </h2>
            <p class="aditem-main--middle--tags">65 m² &#183; 2 Zi.</p>
            <div class="aditem-main--middle--price-shipping">
              <p class="aditem-main--middle--price-shipping--price">1.800 €</p>
            </div>
          </div>
          <div class="aditem-main--bottom">
            <p class="text-module-end"><span class="simpletag">Von Privat</span></p>
          </div>
        </div>
      </article>
    </li>
    """

    listings = kleinanzeigen.extract_listings(
        html,
        base_url=(
            "https://www.kleinanzeigen.de/s-wohnung-mieten/duesseldorf/"
            "sortierung:neuste/anzeige:angebote/c203l2068+wohnung_mieten.swap_s:nein"
        ),
    )

    assert len(listings) == 1
    listing = listings[0]
    assert listing.id == "3425718263"
    assert listing.url == (
        "https://www.kleinanzeigen.de/s-anzeige/"
        "moebilierte-2-zimmer-wohnung-in-pempelfort-zur-untermiete/3425718263-203-2082"
    )
    assert listing.title == "Möbilierte 2 Zimmer Wohnung in Pempelfort zur Untermiete"
    assert listing.address == "40477 Pempelfort"
    assert listing.price_eur == 1800.0
    assert listing.living_area_m2 == 65.0
    assert listing.rooms == 2.0
    assert listing.provider == "Von Privat"
    assert listing.published == "Heute, 08:42"
    assert listing.source == "Kleinanzeigen"
    assert listing.source_color == 0x86B817
    assert listing.image_url == "https://img.kleinanzeigen.de/api/v1/prod-ads/images/00/example?rule=$_2.AUTO"
    assert listing.google_maps_url == "https://www.google.com/maps/search/?api=1&query=40477+Pempelfort"




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
        "https://www.kleinanzeigen.de/s-wohnung-mieten/duesseldorf": """
            <article class="aditem" data-adid="3"
                     data-href="/s-anzeige/klein/3-203-2068">
              <h2><a href="/s-anzeige/klein/3-203-2068">Klein</a></h2>
            </article>
        """,
    }

    def fake_fetch_listings(
        urls,
        *,
        limit: int,
        headless: bool,
        real_chrome: bool,
        concurrent_requests: int,
        concurrent_requests_per_domain: int,
    ):
        assert tuple(urls) == tuple(pages)
        assert limit == 10
        assert headless is True
        assert real_chrome is False
        assert concurrent_requests == 8
        assert concurrent_requests_per_domain == 2
        return [
            scraper._FetchedListings(
                position=position,
                listings=source_for_url(url).extract(pages[url], url)[:limit],
            )
            for position, url in enumerate(urls)
        ]

    monkeypatch.setattr(scraper, "_fetch_listings_concurrently", fake_fetch_listings)

    grouped = scrape_listing_page_groups([tuple(pages)], limit=10, concurrent_requests=8, concurrent_requests_per_domain=2)
    listings = grouped[0]

    assert [listing.url for listing in listings] == [
        "https://www.immobilienscout24.de/expose/1",
        "https://www.immowelt.de/expose/2",
        "https://www.kleinanzeigen.de/s-anzeige/klein/3-203-2068",
    ]
def test_scrapes_criteria_groups_with_one_concurrent_fetch(monkeypatch) -> None:
    pages = {
        "https://www.immobilienscout24.de/duesseldorf": """
            <script type="application/json">
            {"resultListModel":{"realEstates":[{"id":"1", "url":"/expose/1", "title":"Düsseldorf Scout"}]}}
            </script>
        """,
        "https://www.immowelt.de/duesseldorf": """
            <script type="application/json">
            {"classifieds":[{"classifiedId":"2", "url":"/expose/2", "headline":"Düsseldorf Welt"}]}
            </script>
        """,
        "https://www.immobilienscout24.de/cologne": """
            <script type="application/json">
            {"resultListModel":{"realEstates":[{"id":"3", "url":"/expose/3", "title":"Cologne Scout"}]}}
            </script>
        """,
    }
    requested_batches = []

    def fake_fetch_listings(
        urls,
        *,
        limit: int,
        headless: bool,
        real_chrome: bool,
        concurrent_requests: int,
        concurrent_requests_per_domain: int,
    ):
        requested_batches.append(tuple(urls))
        return [
            scraper._FetchedListings(
                position=position,
                listings=source_for_url(url).extract(pages[url], url)[:limit],
            )
            for position, url in enumerate(urls)
        ]

    monkeypatch.setattr(scraper, "_fetch_listings_concurrently", fake_fetch_listings)

    grouped = scrape_listing_page_groups(
        [
            ("https://www.immobilienscout24.de/duesseldorf", "https://www.immowelt.de/duesseldorf"),
            ("https://www.immobilienscout24.de/cologne",),
        ],
        limit=10,
    )

    assert requested_batches == [
        (
            "https://www.immobilienscout24.de/duesseldorf",
            "https://www.immowelt.de/duesseldorf",
            "https://www.immobilienscout24.de/cologne",
        )
    ]
    assert [[listing.title for listing in listings] for listings in grouped] == [
        ["Düsseldorf Scout", "Düsseldorf Welt"],
        ["Cologne Scout"],
    ]




def test_fetch_listings_preserves_configured_page_order(monkeypatch) -> None:
    created: list[object] = []

    class FakeSpider:
        def __init__(
            self,
            urls,
            limit,
            *,
            headless: bool,
            real_chrome: bool,
            concurrent_requests: int,
            concurrent_requests_per_domain: int,
        ) -> None:
            assert urls == ("https://a.test", "https://b.test")
            assert limit == 10
            assert headless is False
            assert real_chrome is True
            assert concurrent_requests == 6
            assert concurrent_requests_per_domain == 3
            created.append(self)

        def start(self):
            return SimpleNamespace(
                items=[
                    {"position": 1, "listings": [SimpleNamespace(id="b")]},
                    {"position": 0, "listings": [SimpleNamespace(id="a")]},
                ]
            )

    monkeypatch.setattr(scraper, "_ListingPagesSpider", FakeSpider)

    pages = scraper._fetch_listings_concurrently(
        ("https://a.test", "https://b.test"),
        limit=10,
        headless=False,
        real_chrome=True,
        concurrent_requests=6,
        concurrent_requests_per_domain=3,
    )

    assert [page.listings[0].id for page in pages] == ["a", "b"]
    assert len(created) == 1



def test_source_registry_supports_kleinanzeigen_urls() -> None:
    source = source_for_url(
        "https://www.kleinanzeigen.de/s-wohnung-mieten/duesseldorf/"
        "sortierung:neuste/anzeige:angebote/c203l2068+wohnung_mieten.swap_s:nein"
    )

    assert source.name == "Kleinanzeigen"
    assert source.host == "www.kleinanzeigen.de"






def test_default_page_modules_define_fetch_options() -> None:
    assert fetch_options_for_url("https://www.immobilienscout24.de/search")["google_search"] is True
    assert fetch_options_for_url("https://www.immobilienscout24.de/search")["solve_cloudflare"] is False
    assert fetch_options_for_url("https://www.immowelt.de/classified-search?order=DateDesc")["google_search"] is False
    assert fetch_options_for_url("https://www.immowelt.de/classified-search?order=DateDesc")["solve_cloudflare"] is False
    assert fetch_options_for_url("https://www.kleinanzeigen.de/s-wohnung-mieten/duesseldorf")["google_search"] is False
    assert fetch_options_for_url("https://www.kleinanzeigen.de/s-wohnung-mieten/duesseldorf")["solve_cloudflare"] is False
