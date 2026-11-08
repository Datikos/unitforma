# Unitforma competitor landscape — Georgia (country)

Research date: 2026-11-08. Method note (important for the report writer): this session's network policy blocked direct
fetches of almost every target site (curl through the proxy returned `CONNECT tunnel failed, response 403` and WebFetch
returned `ENOTFOUND` for lisihouse.ge, korter.ge, domushub.io, alliancegroup.ge, archi.ge, m2.ge, etc.). The only
target that could be fetched directly was tas.ge. **No page-source / script-domain fingerprinting of developer sites was
possible.** All other findings below come from web-search result summaries of the cited pages (the pages themselves were
not opened), so treat quoted details as "per search snippet of the cited page". To finish the vendor-fingerprint work,
the hosts `lisihouse.ge`, `korter.ge`, `archi.ge`, `m2.ge`, `alliancegroup.ge`, `domushub.io` etc. must be allowed in
the session's network settings.

## 1. Which Georgian developer websites have an interactive apartment chooser, and who built them?

### Takeaway
Large Tbilisi developers run their own sites with at least a filterable unit list (Archi's "Find your home": floor, area,
rooms, price, unit-by-block list); full facade/floor SVG choosers exist (e.g. lisihouse.ge per the brief) but are built
bespoke by local web agencies or with WordPress image-map plugins, not by a dominant SaaS. The only documented use of a
foreign chooser/chessboard SaaS by a Georgian developer is Profitbase at Smart Development Georgia (Batumi). Vendor
attribution for Archi, m2, Alliance, Next, Domus, Axis, Black Sea Group, Orbi, Dirsi, King David, REG, Tbilisi Hills,
Iveria could not be verified (sites unreachable from this session).

### Cited Findings
- **Archi (archi.ge)** — complex pages (Archi Universe, Grand Avenue, Archi Alley, Archi Dighomi 2, Archi Guramishvili,
  Archi Gldani 2) have a "Find your home" section with filters for floor, area range, number of rooms and price, plus a
  property-type selector (home / parking / commercial) on Grand Avenue; units are listed by block and apartment number
  with floor and m²; pages carry "Request a call" / "Purchase an apartment" CTAs. No evidence found of online
  reservation/payment. — [Archi Universe](https://archi.ge/en/complex/archi-universe);
  [Grand Avenue](https://archi.ge/en/complex/grand-avenue); [Archi Universe A building page](https://archi.ge/en/building/archi-universe-a)
  - URL structure `/complex/` → `/block/` → `/building/` suggests a site → block → building hierarchy (inference from URLs
    only). — [archi.ge block page](https://archi.ge/en/block/archi-guramishvili)
- **Archi market position**: described at the Feb-2026 Georgia International Real Estate Forum as "#1 Real Estate
  Developer in Georgia with an 18 percent market share" (self-reported/unverified methodology). —
  [Breaking Travel News](https://www.breakingtravelnews.com/news/article/georgia-strengthens-investment-links-with-gulf-markets-at-2026-internationa/)
- **Gumbati Holding (gumbatiholding.ge)** — homepage has a "Choose Apartment" entry point (projects: Saburtalo Residence,
  Hippodrome Residence, Kipshidze St. complex); whether it is facade/floor-interactive is unknown. —
  [gumbatiholding.ge](https://gumbatiholding.ge/en)
- **VR Holding (vr.ge)** — project pages let buyers explore apartment formats per development. —
  [vr.ge blog](https://vr.ge/en/news/blog/apartments-for-sale-in-tbilisi-new-developments-from-a-developer)
- **Lisi Development (lisi.ge)** — offers an "interactive map" of available land plots with technical specs around Lisi
  Lake (land, not apartments); developing the Lisi Lake area since 2012. — [lisi.ge blog](https://lisi.ge/en/blog/miwis-shedzena-lisze)
- **Lisi House (lisihouse.ge)** — Korter lists "Lisi House" on Leo Kvachadze St., 83 apartments, 40–137 m². — [korter.ge](https://korter.ge/en/lisi-house-tbilisi).
  The "building_planner" WordPress plugin named in the brief is **not found** in public WordPress.org search; the closest
  public plugin is "Interactive Real Estate – Floor Plan & Building Visualizer" (slug `interactive-real-estate`), which
  draws clickable SVG polygons over building renders/floor plans linked to unit pages; free tier limited to 1 project
  and 25 flats; v2.3.0. — [WordPress.org](https://wordpress.org/plugins/interactive-real-estate/)
- **Smart Development Georgia (Batumi, 4 projects)** — uses **Profitbase** (Russian SaaS) for a business-class Batumi
  complex: chessboard ("шахматка") widget with live availability/prices, auto-reservation on CRM status change,
  dynamic repricing of similar units when lots sell; paired with **Bitrix24**. Case ~1.5 years old. —
  [Profitbase blog case](https://blog.profitbase.ru/tiepier-khaos-v-proshlom-kieis-smart-development-georgia/);
  [novostiitkanala.ru](https://www.novostiitkanala.ru/news/detail.php?ID=184009)
- **Alliance Group, Next Group** — search found only third-party project listings (Alliance Highline: 3 houses under
  construction, next delivery Q4 2026 vs Korter's Q4 2027 — conflicting; Next: Tbilisi Oriental Q4 2028, Cinema City Q3
  2029); no evidence of 3D chooser/virtual tour on their own sites was surfaced. —
  [korter.ge Alliance Highline](https://korter.ge/en/alliance-highline-tbilisi); [korter.ge Next Group](https://korter.ge/en/next-group)
- **Prostor (Tbilisi web agency)** built an "Interstellar — apartment selection" site; its developer sites include a
  chessboard by block and floor, filters by area/price/layout, a page per unit with plan + PDF, availability status,
  live statuses from CRM, up to 4 languages. — [prostor-agency.com/georgia/real-estate](https://en.prostor-agency.com/georgia/real-estate);
  [prostor-agency.com/georgia](https://en.prostor-agency.com/georgia)

### Inferences
- The Georgian "chooser" market is fragmented: bespoke agency builds (Prostor-type, $2.5k+) and WordPress image-map
  plugins with hand-drawn polygons (lisihouse.ge per brief) dominate, which is exactly the manual work Unitforma
  automates (polygon/plan extraction from PDFs/DXF/IFC).
- Russian-speaking SaaS (Profitbase) has a foothold in Batumi, where many developers sell to Russian/Israeli/CIS buyers;
  Tbilisi top-tier developers appear to build in-house.

### Gaps
- Script-domain/footer-credit fingerprints for m2, Alliance, Next, Domus, Axis, Black Sea Group, Orbi, Dirsi, King David,
  REG, Tbilisi Hills, Iveria, lisihouse.ge — not obtainable (network blocked). Needs direct fetch.
- Whether m2.ge has a facade/floor chooser — no search results surfaced.
- No evidence found of Korter-, MacroCRM- or Profitbase-powered choosers on Tbilisi developer sites (absence of evidence,
  not evidence of absence). MacroCRM: no Georgian mentions found at all.

## 2. Georgian real-estate portals and new-build marketplaces — developer pages, unit choosers, CRM/inventory tools?

### Takeaway
Portals (myhome.ge/TNET, ss.ge/house.ge, korter.ge, livo.ge) are lead-generation listing channels with project pages,
floor plans, prices and maps; none was found to sell developers a white-label buyer portal, unit chooser for the
developer's own domain, or an inventory CRM. Korter is reportedly free for developers. They are complements/channels to
Unitforma more than substitutes — but they set buyer expectations and could become feed targets.

### Cited Findings
- **Traffic (Semrush, Mar 2026)**: myhome.ge #1 Georgian real-estate site; ss.ge #2 (~404K visits, 95.8% desktop per
  Semrush); korter.ge #3 (~140K visits). Third-party estimates. — [Semrush](https://www.semrush.com/trending-websites/ge/real-estate)
- **myhome.ge (TNET)** — "Projects"/"Development companies" section (116 projects in one snapshot) for comparing offers
  and evaluating developers, plus a developers directory. — [myhome.ge projects](https://www.myhome.ge/en/developers/projects/);
  [myhome.ge developers](https://www.myhome.ge/en/developers/)
- **TNET** owns Myhome.ge and Livo.ge among 9 platforms; SuperApp claims 2M registered users. —
  [App Store SuperApp TNET](https://apps.apple.com/us/app/superapp-tnet/id6444474250); [Forbes Georgia](https://forbes.ge/en/the-technological-leader/)
- **livo.ge** — formerly allproperty.ge, bought by TBC Group and rebranded; now a joint TNET + TBC Tech platform offering
  valuation, surveying, auctions, registration, **3D scanning**, and a secure (escrow-like) transaction system; ranked #3
  myhome.ge competitor by Similarweb (Aug 2026). — [LinkedIn profile (Madona Kachkachashvili)](https://www.linkedin.com/in/madona-kachkachashvili/);
  [Similarweb](https://www.similarweb.com/website/myhome.ge/competitors/)
- **korter.ge** — new-build catalogue with interactive map, district pages (e.g. Gldani 42 developments; Isani 69 vs an
  older cache 63), installment-plan page listing 230 developments, developer profile pages (e.g. Code Development, NBG,
  Alliance Group), project pages with prices, floor plans, construction updates. — [map](https://korter.ge/en/new-projects-in-tbilisi-on-map);
  [installment](https://korter.ge/en/new-projects-tbilisi-installment); [Isani](https://korter.ge/en/new-projects-in-isani);
  [Gldani](https://korter.ge/en/new-projects-tbilisi-gldani-district); [developers in Tbilisi](https://korter.ge/en/developers-in-tbilisi)
  - "On Korter, everything is placed free of charge"; staff verify objects and update weekly; at that time 342 complexes
    from 239 developers (article undated, likely older). — [cbw.ge](https://cbw.ge/real-estate/korter-reliable-information-on-residential-real-estate-in-georgia)
- **ss.ge / house.ge** — SS.ge described as the most high-traffic real-estate platform; its House.ge collects all new
  finished and unfinished apartments in Tbilisi (article ~4 years old). — [cbw.ge](https://cbw.ge/real-estate/housege-new-platform-for-finished-and-unfinished-new-apartments).
  CB Insights: ss.ge offers property advertising, verified listings, financial calculators. — [CB Insights](https://www.cbinsights.com/company/ssge)
- **Other aggregators**: GEOLN (geoln.com — Tbilisi/Batumi new-build catalogue, developer directory, hosted **3D apartment
  tours** for Batumi projects like Galileo, Panorama, Accent, Sunway Suites) — [geoln Tbilisi](https://geoln.com/georgia/tbilisi);
  [geoln 3D Galileo](https://geoln.com/georgia/batumi/723/3d); [geoln developers](https://geoln.com/developers-tbilisi).
  Realting (international), Domik.io (developer rankings), tbilisi-property.com, residence-estate.ge, propertygeorgia.ge,
  gean.ge and findproperty.ge (aggregators — unverified auto-generated descriptions), 360trusty.com (Batumi listings with
  360° tours). — [realting](https://realting.com/georgia/tbilisi/new-buildings/apartments); [domik.io](https://domik.io/en/georgia/developers/);
  [tbilisi-property.com](https://tbilisi-property.com/complex-tbilisi/); [gde.ge gean.ge](https://gde.ge/domain/gean.ge);
  [gde.ge findproperty.ge](https://gde.ge/findproperty.ge.html); [360trusty](https://360trusty.com/)

### Inferences
- Portals monetise buyer traffic; a developer still needs its own site for the full chooser. Unitforma's portal could
  position as the "source of truth" that pushes inventory/prices to Korter/myhome/ss.ge (feed export would be a
  differentiator; not verified that portals accept feeds).
- livo.ge (TBC-backed) with 3D scanning + secure transactions is the portal most likely to move toward developer tooling.

### Gaps
- binebi.ge and area.ge: no results confirming them as active new-build portals.
- Korter/myhome developer pricing (paid placement, CPL) not found; Korter developer widgets/CRM in Georgia not found.
- Whether any portal exposes unit-level chessboards per project (Korter does elsewhere in CIS — unverified for .ge).

## 3. Georgian proptech startups, agencies, CRMs, 3D/virtual tour and AI tools — anyone building something like Unitforma?

### Takeaway
No Georgian startup was found that automates plan→inventory→branded chooser like Unitforma. The closest functional
competitors are foreign SaaS actively targeting Georgia — **DomusHub** (London, site→building→floor→unit master plan,
GEL, instalments, explicit Georgia page) and **WIZIO Verse** (UK, Georgian regional partner, planning a Georgian
interactive off-plan marketplace) — plus Profitbase (Batumi client). Local players are a small developer-CRM (NK
Solutions), web agencies (Prostor), Bitrix24 integrators (FMG Soft), viz/3D-tour studios, and an MVP AI sales-agent
startup (TwinO).

### Cited Findings
**Foreign SaaS serving/targeting Georgia**
- **DomusHub** (domushub.io) — "Real Estate Sales Platform for Georgian Developers" page: fits developers selling 50–500
  units/project in Tbilisi, Batumi, Kutaisi; EN + RU UI, USD/EUR/GEL display, interactive master plans, dynamic instalment
  payment plans, offer-by-URL with view analytics; positions itself alongside HubSpot ("HubSpot tracks the lead…
  DomusHub tracks the inventory, master plan, payment plan and offer"). Master plan navigation "General → Building →
  Floor → Unit" with breadcrumbs. Third-party listing: founded 2022, London. No named Georgian clients found. —
  [DomusHub Georgia](https://domushub.io/en/use-cases/georgia); [DomusHub master plan glossary](https://domushub.io/en/glossary/master-plan);
  [DomusHub home](https://domushub.io/)
- **WIZIO Verse** (WIZIO London) — cloud SaaS for off-plan sales, "go live in 3–5 days"; named Irakli Ustarashvili
  regional partner for Georgia; LinkedIn post (~108 days before search, i.e. ~July 2026) says it is "preparing to launch
  Georgia's dedicated interactive off plan marketplace early next year"; staff met developers at Georgia Real Estate
  Expo and expect to onboard partner projects. Unverified (LinkedIn/vendor). — [wizio.co.uk](https://wizio.co.uk/);
  [WIZIO London LinkedIn](https://uk.linkedin.com/company/bywizio); [Onur Guvenc LinkedIn](https://www.linkedin.com/in/onur-guvenc-6a61282a/);
  [Orkun Beyaz LinkedIn](https://www.linkedin.com/in/orkunbeyaz/); [Capterra WIZIO Verse](https://www.capterra.com/p/10053557/WIZIO-Verse/)
- **Profitbase** — ~600 clients, 17 countries; Georgian client Smart Development Georgia (see §1). —
  [profitbase.ru](https://profitbase.ru/); [case](https://blog.profitbase.ru/tiepier-khaos-v-proshlom-kieis-smart-development-georgia/)
- **Bitrix24** — Real Estate app (by partner InformUnity); Georgian gold partner **FMG Soft** claims 100+ projects in
  Georgia (no real-estate developer case found). — [FMG Soft](https://fmgsoft.ge/iluhcudolrhe/bitrix24-crm/);
  [Bitrix24 Real Estate app](https://www.bitrix24.com/about/blogs/bitrix24-tips-and-updates/transform-your-real-estate-business-with-the-new-bitrix24-real-estate-app.php)
- **Unitify** (adjacent, property-management/payments) — roadshow in Tbilisi and Batumi 28–31 May 2026 to meet
  developers and management companies. — [unitify.com](https://unitify.com/blog/unitify-goes-on-the-road-in-georgia-may-28-31)

**Local CRM / software**
- **NK Solutions** (nksolutions.ge, Tbilisi; operator is a Georgian individual entrepreneur) — sales CRM for property
  developers in Georgian: unit board (whole building on one screen, flats colour-coded free/held/sold), buyer files,
  payment plans, contracts, agents, reports; fixed price & delivery date agreed up front (no public price list); one
  named delivered project: sales CRM for a Tbilisi developer; founders claim ~20 years in property. —
  [nksolutions.ge](https://nksolutions.ge/en); [product](https://nksolutions.ge/en/product); [privacy](https://nksolutions.ge/en/privacy)
- **Hurain Technologies** — custom proptech builds in Tbilisi (brokerage CRM, legacy PMS integration); custom dev, not a
  product. — [huraintechnologies.com](https://www.huraintechnologies.com/industries/real-estate-proptech/georgia/tbilisi)

**Web agencies**
- **Prostor** (Tbilisi, ~12 people per GoodFirms; "most clients are real estate developers") — developer sales sites with
  chessboard, filters, unit pages, CRM-live statuses, up to 4 languages; from **$2,500** (landing page); one residence
  got 54 enquiries in 2 months; 50+ project presentations for Israeli developer Harey Zahav. A Moscow-HQ "PROSTOR agency"
  (founded 2023) on workspace.ru may be the same or a different entity — conflicting. —
  [prostor real estate](https://en.prostor-agency.com/georgia/real-estate); [GoodFirms](https://www.goodfirms.co/company/prostor);
  [Sortlist](https://www.sortlist.com/agency/prostor); [workspace.ru](https://workspace.ru/id/prostor-studio/)

**3D visualisation / virtual tours**
- **3D Tours Georgia** (3d-tours.ge, Tbilisi) — 3D scanning/digital twins for real estate & hotels, developer clients. — [3d-tours.ge](https://3d-tours.ge/)
- **Paralel Visualization Studio** (Tbilisi) — renders, animation, 360° panoramas, VR interiors. — [Behance](https://www.behance.net/paralel)
- **Artmakers Studio** — real-estate photo/video, interactive interior & aerial 3D tours. — [skyartmakers.com](https://skyartmakers.com/real-estate-photography-tbilisi/)
- **ModX** (modx.ge) — real-estate/architecture visualisation. — [modx.ge](https://modx.ge/)
- **livo.ge** 3D scanning (see §2); **GEOLN** hosted 3D apartment tours (see §2).

**AI / startups**
- **TwinO** (twino.estate, Tbilisi; founder & CEO Giorgi Intskirveli) — AI agents to automate customer communication,
  qualify leads 24/7 and manage sales for real-estate companies; MVP, founded 2026, undisclosed funding; claims $20K E2B
  credits and Google for Startups support. Self-reported. — [thestartup.ge TwinO](https://thestartup.ge/ecosystem/startup/twino);
  [Giorgi Intskirveli LinkedIn](https://www.linkedin.com/in/giorgi-intskirveli-69a54a229/)
- Events where such vendors appear: Realty Forum Tbilisi Invest 2026 (17–19 Nov 2026, Pullman Axis Towers, New
  Development Expo, ~2,000 attendees claimed); Georgia International Real Estate Forum (6–8 Feb 2026); Property Exclusive
  2026 (FIABCI-Georgia, 26 Apr 2026); Real Estate Expo Tbilisi (5–6 Dec 2025 edition). —
  [internationalinvestment.biz](https://internationalinvestment.biz/business/9049-16.html);
  [Breaking Travel News](https://www.breakingtravelnews.com/news/article/georgia-strengthens-investment-links-with-gulf-markets-at-2026-internationa/);
  [FIABCI](https://www.fiabci.org/en/news-room/view/621); [entrepreneur.com/ka](https://www.entrepreneur.com/ka/siakhleebi-da-tendentsiebi/eqspo-jorjiashi-5-6/500399)

### Inferences
- Competitive set for a Georgian developer today: (a) agency-built site + spreadsheet/Bitrix24/NK Solutions CRM +
  render/3D-tour studio + portal listings (status quo, multi-vendor, manual polygon drawing); (b) foreign all-in-one
  off-plan SaaS (DomusHub, WIZIO, Profitbase). Unitforma's differentiators vs (b): automated extraction from
  PDF/DXF/IFC with human review, Georgian-language focus, tas.ge permit import, renovation playground/AI renders, MCP/AI
  assistant. DomusHub is the most direct feature overlap (master plan → unit, GEL, instalments) and WIZIO the most
  active go-to-market in Georgia in 2026.
- TwinO overlaps only with Unitforma's AI assistant/inquiry handling; potential partner rather than competitor.

### Gaps
- Pricing for DomusHub, WIZIO Verse, Profitbase in Georgia; any named Georgian DomusHub/WIZIO clients.
- Whether Korter offers paid developer tools in Georgia (it does in other markets — unverified here).
- GITA / Startup Georgia-funded proptech: no results surfaced; thestartup.ge active-startups list only surfaced TwinO. —
  [thestartup.ge](https://thestartup.ge/georgia-startups/active-startups)
- No Georgian AI floor-plan render / renovation-playground product found.

## 4. Use of tas.ge / Tbilisi architecture permit data by other products

### Takeaway
No third-party product was found that productises tas.ge permit data for developers or buyers; it is used as an
aggregate statistics source (Galt & Taggart permit series). This makes Unitforma's tas.ge import apparently unique in
Georgia (absence of evidence).

### Cited Findings
- Direct fetch of https://tas.ge on 2026-11-08 (HTTP 200) returned the Tbilisi Municipality Architecture Service portal
  (page title "Architect.Tbilisi.Gov.Ge - არქიტექტურა"), with menu items for an interactive map (ინტერაქტიული რუკა),
  expedited service, electronic applications, "search for the Service's response" (სამსახურის პასუხის მოძებნა), and ID-card
  login/registration. — [tas.ge](https://tas.ge/) (own fetch)
- Galt & Taggart's Tbilisi residential reports use TAS permit data: permitted residential living area in Tbilisi fell
  4.2% y/y in 2025 to 1.7mn m², with a sharp Q4 drop (−32.1% y/y); permits still ~32% above the "healthy" 2015–2022
  average. — [G&T Dec 2025 PDF](https://ramad.bog.ge/galt/mbmsFtZb-Tbilisi-Residential-Real-Estate_ENG_Dec-2025.pdf);
  [gbc.ge](https://gbc.ge/en/news/Economics-news/construction-permits-down-by-42-in-2025)
- GeoStat: 11,578 building permits nationwide in 2025, Tbilisi 46.2% of planned construction; Q1 2026: 2,472 permits,
  Tbilisi 48.7%. — [gbc.ge](https://gbc.ge/en/news/Economics-news/construction-permits-down-by-42-in-2025);
  [Business Insider Georgia](https://www.businessinsider.ge/Society/construction-permits-in-georgia-rise-in-january-march-amid-decline-in-facilities-commissioned-geostat-35522?lng=eng)
- FactCheck.ge story on Tbilisi permits ("permits for 6.5 million m² issued… building another Tbilisi") — older, context
  only. — [factcheck.ge](https://factcheck.ge/en/story/30818-construction-permits-for-6-5-million-m2-are-issued-in-tbilisi-this-means-building-another-tbilisi)

### Inferences
- Permit data is public but locked in a municipal portal (document responses, interactive map); scraping/structuring it
  is a moat-like onboarding shortcut no competitor appears to offer.

### Gaps
- Whether tas.ge has an API or terms restricting automated access — not checked.
- Whether Korter/myhome import project data from permits — no evidence found.

## 5. Market context — sizing the Tbilisi new-build opportunity

### Takeaway
Tbilisi records ~42K apartment transactions/year (2025), with primary (new-build) sales growing and average primary
turnkey prices ~$1,865/m² (2025); Korter lists a few hundred active complexes from ~240 developers (older figure), and
G&T's survey of the ~20 largest "systematic" developers covers only ~50% of the primary market — i.e. a long tail of
small/mid developers who are the natural Unitforma target. Batumi adds ~17.5K sales/year.

### Cited Findings
- 2025 Tbilisi apartment sales (Public Registry): **42,388 units, +4.3% y/y**. — [bm.ge](https://bm.ge/en/news/over-42000-apartments-sold-in-tbilisi-in-2025)
- Primary market 2025: +5.2% y/y per registry (delayed registrations) vs **+27.3% y/y per G&T developer survey**;
  primary turnkey avg price **$1,865/m², +9.4% y/y**; G&T expects 2026 demand broadly flat with single-digit price
  growth and oversupply risk; primary sales +24.1% y/y in 2M26 (low base). — [gbc.ge G&T 2026 outlook](https://gbc.ge/en/news/Economics-news/galttaggart-predicts-single-digit-growth-in-apartment-prices-in-tbilisi-in-2026);
  [bm.ge](https://bm.ge/en/news/over-42000-apartments-sold-in-tbilisi-in-2025) (figures from search summary across these; verify exact attribution)
- 2M26: 6,786 transactions registered in Tbilisi, market value US$595mn (G&T). — [gbc.ge](https://gbc.ge/en/news/Economics-news/demand-in-tbilisis-real-estate-market-is-growing-while-the-issuance-of-construction-permits-has-been-decreasing-for-the-5th-month)
- Value: headline "GEL? 3.1 billion worth of apartments sold in Tbilisi in 11 months of 2025" (currency not confirmed from
  title — likely US$ given 2M26 $595mn run-rate; unverified). — [gbc.ge](https://gbc.ge/en/news/Economics-news/gt-31-billion-worth-of-apartments-sold-in-tbilisi-in-11-months-of-2025)
- 83% of apartments in Tbilisi projects due for completion in 2025 already sold, mostly via developers' internal
  instalment plans. — [bm.ge](https://bm.ge/en/news/83-of-apartments-in-tbilisi-projects-set-for-completion-in-2025-already-sold-gt);
  [commersant.ge (81% earlier)](https://commersant.ge/en/news/society/81-of-apartments-are-already-sold-in-the-projects-finishing-in-2025-galttaggart)
- G&T developer survey coverage: Apr 2024 — 14 systematic developers, 68 ongoing Tbilisi projects; May 2025 — 20
  developers, 90+ projects (~40% of primary market); Jan 2026 — systematic developers with 100+ ongoing projects (~50%
  of primary market). — [G&T Apr 2024](https://api.galtandtaggart.com/sites/default/files/2024-05/report/tbilisi-residential-real-estate_eng_-march-2024.pdf);
  [G&T Dec 2025/Jan 2026](https://ramad.bog.ge/s3/galt/mbmsFtZb-Tbilisi-Residential-Real-Estate_ENG_Dec-2025.pdf);
  [G&T Apr 2025](https://galtandtaggart.com/files/galt/Tbilisi-Residential-Real-Estate_ENG_April-2025.pdf)
- Korter: 342 residential complexes from 239 developers (undated, likely older); 230 Tbilisi developments with
  instalment plans (current page). — [cbw.ge](https://cbw.ge/real-estate/korter-reliable-information-on-residential-real-estate-in-georgia);
  [korter installment](https://korter.ge/en/new-projects-tbilisi-installment)
- Colliers 2026: Sep-2026 Tbilisi sales 4,245 apartments (+6.4% y/y) but primary sales fell sharply (base effect from
  bulk registrations in Sep-2025); Jul-2026 4,486 units (+22.8% y/y); primary prices −10.7% vs resale +9.9% in Sep;
  weighted avg new-build price up in all areas Jul-2026 vs Jul-2025 (centre ~+13%). A "Jan–Jun 2026: 7,838 transactions
  (+11.4%)" figure appeared in the same summary and is inconsistent with monthly ~4K totals — likely a sub-segment;
  unverified. — [internationalinvestment.biz](https://internationalinvestment.biz/en/real-estate/8970-georgias-property-market-apartment-sales-rise-in-tbilisi-fall-in-batumi.html);
  [Georgia Today Colliers Feb-2026](https://georgiatoday.ge/colliers-tbilisi-apartment-sales-and-prices-rise-in-february-2026/);
  [recov.ge (Colliers)](https://recov.ge/en)
- TBC Capital forecast ~3.2% avg Tbilisi price growth in 2026 and warns potential supply keeps growing, intensifying
  competition (→ developers need better sales tooling). — [internationalinvestment.biz Colliers/TBC](https://internationalinvestment.biz/en/real-estate/6570-colliers-forecast-georgias-housing-prices-to-remain-stable-in-2026.html)
- Colliers: ~23% y/y decrease in newly launched residential units nationally, concentrated in large outer-district
  Tbilisi high-rises; banks reduced financing for new projects in 2025. — [internationalinvestment.biz](https://internationalinvestment.biz/en/real-estate/6570-colliers-forecast-georgias-housing-prices-to-remain-stable-in-2026.html)
- Batumi: 17,478 apartments sold in 2025 (+15% y/y); "over 250 active developers" in Batumi per a Georgian agency
  (unverified). — [gbc.ge](https://gbc.ge/en/news/Economics-news/batumi-residential-real-estate-market-grows-15-in-2025-galt-taggart);
  [DomusHub search snippet / dazhomes context](https://domushub.io/en/use-cases/georgia)
- Israeli buyers ~12% of sales in 7M 2025 (G&T-based report). — [ynetnews](https://www.ynetnews.com/real-estate/article/bjgibzetzg)

### Inferences
- Rough sizing: if Tbilisi has on the order of 200–300 active developers and several hundred live projects (Korter
  counts), and the top ~20 build ~50% of supply, the long tail of ~200+ small developers is the realistic SaaS
  segment; top developers (Archi, m2, Alliance, Next) already have in-house/agency sites. Combined Tbilisi + Batumi
  ~60K transactions/yr. (Inference, not a sourced figure.)
- Rising supply + flat demand + developer instalment financing → stronger need for direct-to-buyer sales channels,
  supporting Unitforma's value proposition.

### Gaps
- Precise current count of active developers/projects in Tbilisi (2026) — no authoritative source found.
- Knight Frank Georgia data — none found.
- Exact primary-market share of total sales in 2025–2026 not confirmed.
