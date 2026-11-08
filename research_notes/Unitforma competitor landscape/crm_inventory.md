# Developer sales-inventory / CRM platforms (back-office layer) — competitor & integration landscape

Research date: 2026-11-08. Method: web search (snippet-level) plus page fetches. **Limitation:** page fetches to most vendor domains failed in this session because the hosts are not on the network allowlist (spark.re, sell.do, propspace.com, bitrix24.ru, propertygeorgia.ge). Many findings below therefore rest on search-engine snippets of the cited pages, not full-page reads. Treat prices especially as "as indexed", and re-check them on vendor pages before quoting. Third-party directory prices (Capterra, crmindex, startpack) are often stale or contradictory, and the notes say where they conflict.

## 1. Global / Western developer sales-inventory CRMs: features, pricing, target market

### Takeaway
Spark is the main Western new-development platform. It has an inventory/pricing matrix, allocation, options/upgrades, reservations/contracts and buyer-facing integrations, but it relies on partners such as Planpoint for the interactive visual chooser. The other Western options are either brokerage CRMs (Propertybase, Rex, onOffice/Propstack, Kommo, HubSpot) that need customisation or add-ons for developer inventory, or homebuilder CRMs for the US market (Lasso/ECI). Public pricing is rare. Most vendors sell on quotes with setup fees.

### Cited Findings
**Spark (Spark RE Technologies, Vancouver; new-development CRM, founded 2013)**
- Its inventory module offers a live pricing matrix meant to replace spreadsheets, customizable inventory statuses, real-time allocation views, parking/storage stall limits and revenue reporting, options and upgrades that buyers select at reservation or contract, floorplans linked to the matrix, and multiple buildings in one project database. Source: search snippet of the vendor page. — [Spark inventory](https://www.spark.re/product/inventory/); [Spark product overview](https://www.spark.re/product/)
- Pricing is not published. G2 says the vendor provides none. Third-party listings show "from CA$100/month" plus a one-time company setup fee and a per-project setup fee. Software Advice shows $25/month in one place, which conflicts with that. All of these are unverified. — [Capterra pricing](https://www.capterra.com/p/169855/Spark/pricing/); [G2 pricing](https://www.g2.com/products/spark-crm/pricing); [Software Advice](https://www.softwareadvice.com/product/231298-spark/)
- **Visual chooser comes from partners, not Spark itself.** Spark's partner page lists Planpoint's interactive selectors, which run on the developer's website and pull availability and pricing from Spark inventory. Zapier appears only as a "contact the dev team" entry, and Spark sends integration questions to Customer Success. — [Spark Integration Partners](https://www.spark.re/partner-integrations)
- A Zapier "Spark ↔ HubSpot" page exists, but it may not be Spark.re. Zapier also hosts Spark Hire, an unrelated HR product, so this is unverified. — [Zapier Spark–HubSpot](https://zapier.com/apps/spark/integrations/hubspot)

**Propertybase (Lone Wolf; Salesforce-based brokerage CRM)**
- There are two editions. "GO" is standalone and needs no Salesforce licence. The "Salesforce Edition" runs on the Salesforce platform, and its price includes the Salesforce licence. — [The Close review](https://theclose.com/propertybase-go-review/); [GetApp](https://www.getapp.co.uk/software/9613/propertybase)
- Pricing is not published. Third-party estimates put GO at about $79/user/month and the full platform at $100–200+/user/month (unverified). — [The Close](https://theclose.com/propertybase-review/); [SourceForge](https://www.sourceforge.net/software/product/Propertybase)
- The vendor's CRM page talks about MLS aggregation and portal syndication. Search found no evidence of new-development unit inventory, reservations or payment plans. — [Propertybase real estate CRM](https://www.propertybase.com/real-estate-crm/)

**Salesforce / HubSpot (generic CRMs configured for developers)**
- On HubSpot, developer-inventory needs (master unit inventory, booking/reserving units, picking a payment plan at booking) have no native answer. Community threads point to custom objects or custom-built portals. — [HubSpot Community thread](https://community.hubspot.com/t/inventory-control-for-real-estate/13393); [HubSpot Community: developers inventory](https://community.hubspot.com/t5/APIs-Integrations/Real-Estate-Developers-Inventory/m-p/257710)
- An Australian HubSpot agency recommends a custom-object model to track stock across developments, releases, buyer interest, reservations, contracts and settlement. — [clck.com.au](https://www.clck.com.au/blog/hubspot-property-development-inventory/)
- Real-estate apps on Salesforce AppExchange (Propertybase about $79, Rethink about $159/user/month per listing) are brokerage or commercial real-estate tools, not tools for new-development unit inventory. — [Magicfuse AppExchange list](https://magicfuse.co/blog/13-best-salesforce-appexchange-applications-for-real-estate)

**Lasso CRM (ECI Software Solutions; US/Canada new-home builders)**
- Lasso is part of ECI's residential home-construction suite, not ClickSoftware. G2 says it is used by 500+ home builders and developers in North America. — [Software Advice](https://www.softwareadvice.com/crm/lasso-crm-profile); [G2](https://g2.com/products/lasso-crm/reviews?page=2)
- Pricing is quote-based. Listings show "from $495" (per-feature model), while ITQlick says $49/user/month. These conflict and are unverified. — [Krowdbase](https://www.krowdbase.com/software/lasso-crm); [ITQlick](https://www.itqlick.com/lasso-crm/pricing)

**Rex (Australia/UK agency CRM)**
- Rex has a premium "Projects" add-on with project and stage records for developments and land estates and a "stock mode". Holds (reservations) are tracked from the listing's legal tab. — [Rex feature release: projects](https://rexsoftware.com/updates/feature-release-new-project-marketing-add)
- Rex describes itself as an estate-agency platform serving 10,000+ agents (CRM, Rex Reach marketing, websites). — [Rex sales & lettings CRM](https://www.rexsoftware.com/sales-and-lettings-crm)

**Kommo (formerly amoCRM; global SMB CRM)**
- Kommo's own guide says per-user pricing changes on 1 Sep 2026: Base goes from $15 to $25 and Advanced from $25 to $35/user/month. Capterra lists Enterprise at $45/user/month. — [Kommo pricing guide](https://www.kommo.com/blog/amocrm-pricing/); [Capterra Kommo pricing](https://www.capterra.com/p/120048/amoCRM/pricing/)

**onOffice / Propstack (DACH)**
- Search found no developer ("Bauträger") features for either. onOffice's AT site presents onOffice enterprise as broker software. — [onOffice AT](https://at.onoffice.com/en)
- DACH developers publish PDF price lists that colour-code status (e.g. yellow = reserved, red = sold). This suggests an export-to-PDF price list is an expected deliverable. — [infina.at price list example](https://www.infina.at/fileadmin/realestate/151/37764934/37764934.pdf)

### Inferences
- In the West, "developer CRM with inventory" is a narrow niche led by Spark. Most developers otherwise run Salesforce or HubSpot with custom objects, or brokerage CRMs. This favours Unitforma positioning itself as the inventory source of truth plus buyer portal that feeds whatever CRM the developer already uses.
- Spark's reliance on Planpoint for the chooser confirms that inventory CRMs and visual choosers are often separate products joined by an inventory sync API. Unitforma combines both layers.

### Gaps
- Not researched or not found this session (all unverified): Reapit (no "Reapit Developer" product found), Fusion CRM, Eloquent, Nurture Cloud, Yardi Breeze/Voyager development modules, Zoho real-estate templates, Salesmate, NoBroker, Realhub, "Urban Apartments". Search found no "Nurture Cloud" developer product.
- No official Spark price, no Spark public API documentation, and no confirmed Spark–Salesforce/HubSpot connector.
- The HubSpot Marketplace was not checked for a dedicated new-development inventory app. None appeared in search.

## 2. India / Gulf developer CRMs

### Takeaway
Sell.Do (India) and the UAE off-plan tools (PropSpace Developer, Asas) are the closest feature analogues to a full developer back office: inventory, cost sheets, booking, payment plans/milestones, and channel-partner (broker) portals with restricted inventory views. Pricing is mostly quote-based. UAE tools often show per-user AED pricing.

### Cited Findings
- **Sell.Do:** channel partners can be limited to a subset of inventory, with the rest shown as sold or unavailable. Partners can raise payment requests, track payment status toward a booking, and help customers complete online KYC. The platform covers partner onboarding with self-serve registration, KYC and approval, lead tracking and brokerage payout. — [Sell.Do inventory & booking](https://www.sell.do/real-estate-crm/inventory-booking); [Sell.Do channel partners](https://www.sell.do/real-estate-crm/channel-partners); [Channel partner management](https://www.sell.do/real-estate-crm/channel-partner-management)
- Sell.Do pricing is quote-based. One third-party estimate puts modules at about ₹2,599/user/month (about $31) (unverified). — [Prospeo](https://prospeo.io/s/selldo-pricing-reviews-pros-and-cons); [Capterra](https://www.capterra.com/p/151826/Sell-Do/pricing/)
- **PropSpace Developer (UAE):** described as software for off-plan marketing, sales, CRM, payment plans and invoicing. The Dubai CRM page mentions an off-plan inventory module covering unit types, pricing and availability. Brokerage-product pricing is AED 176/user/month per the vendor FAQ (snippet). — [PropSpace Developer Sales blog](https://www.propspace.com/blog/introducing-propspace-developer-sales); [PropSpace Dubai CRM](https://www.propspace.com/real-estate-crm-dubai)
- **Asas (UAE):** self-described as built for UAE developers, with multi-project inventory and price lists and off-plan payment plans and milestones. Priced per company, not per seat (vendor claim). — [Asas](https://asas.araneae.net/)
- **Reelly (UAE):** started as an off-plan project database for agents. The founder said a developer-facing tool launched about a month before his post (date not verified, no feature detail). — [LinkedIn post](https://ae.linkedin.com/in/khanevich)
- A UAE vendor blog argues that generic CRMs lack native payment-plan tracking, so developers build it or bolt it on (vendor opinion). — [Netsmartz/PropSmartz](https://www.netsmartz.com/blog/propsmartz-vs-traditional-crm-dubai-developers/)
- A Dubai CRM roundup gives a typical range of AED 200–1,500/month (aggregator, unverified). — [Codingclave](https://codingclave.com/blog/real-estate-crm-dubai)

### Inferences
- The features buyers expect in emerging off-plan markets (Dubai, India), and probably Georgia, include broker portals with restricted inventory, payment-plan milestones, and booking with KYC. These are on Unitforma's "later" list, and in these markets they are what decides the purchase.

### Gaps
- Nothing found on "Property Shell". Goyzer appears only in passing in comparison tables. No verified Sell.Do API or webhook docs (fetch blocked).

## 3. Regional (CIS/Caucasus) developer CRMs: MacroCRM, Profitbase, 1C, Bitrix24, amoCRM

### Takeaway
The Russian-speaking market has the most mature "chessboard" (шахматка) ecosystem. Profitbase is the de facto inventory/chessboard layer that plugs into Bitrix24 and amoCRM. MacroCRM is an all-in-one developer CRM. 1C covers accounting and ERP. Bitrix24's marketplace has many chessboard apps (DomXML, Ained, Plan7, Profitbase connector). Prices run from about 2,900 ₽/user/month (Profitbase) to about 12,500 ₽+ (MacroCRM entry). Russian vendors may face sanctions, payment or perception issues in Georgia (inference, not researched).

### Cited Findings
**Profitbase**
- Catalog prices: Profitbase for amoCRM or for Bitrix24 about 2,900 ₽/user/month. "Smart catalog" (website chessboard) about 15,000 ₽/month per domain. Profitbase.ai priced individually. These are directory figures, not checked against profitbase.ru/tariff. — [crmindex Profitbase](https://crmindex.ru/products/profitbase)
- A Kazakh 1C reseller lists one month of access for one user at 3,335 (currency not stated). — [1cbit.kz](https://www.1cbit.kz/1csoft/profitbase-dlya-nedvizhimosti/)
- Profitbase provides a manager workspace inside the CRM for the deal: reservation, mortgage, document signing, state registration (Rosreestr) and key handover. It visualises premises with status, price and area and syncs with 1C. — [1cbit.kz](https://www.1cbit.kz/1csoft/profitbase-dlya-nedvizhimosti/)
- The Bitrix24 "Profitbase connector" (by a third party) syncs premises from Profitbase into the Bitrix24 CRM. The base version is free but needs a paid Profitbase account and an API key. It keeps an operations log and warns on API-key failures. — [Bitrix24 app: Коннектор Profitbase](https://www.bitrix24.ru/apps/app/metod_tsifry.konnektor_profitbase/); [Profitbase for Bitrix24 app](https://www.bitrix24.ru/apps/app/profitbase.crm/)
- Profitbase has a public REST API documented at developer.profitbase.ru. A community PHP client notes a rate limit of about 1 request/second per client (unverified against the official docs). — [packagist profitbase-php-client](https://packagist.org/packages/Kenny-MGN/profitbase-php-client)
- Bitrix24 partner cases show Profitbase chessboard integrations, for example ART GROUP in Krasnodar, where managers work with the chessboard from the Bitrix24 deal card. — [Bitrix24 partner case](https://www.bitrix24.ru/partners/case/16914002/)

**MacroCRM**
- Startpack lists a minimum price of 12,500 (presumably ₽/month) with a trial (unverified). — [startpack MacroCRM](https://startpack.ru/application/macrocrm)
- The vendor says a website property catalogue and chessboard are built in. Plan7 can use MacroCRM as the master source of property data and build the website chessboard from it. — [Plan7 blog on spark.ru](https://spark.ru/startup/plan7/blog/336993/amocrm-i-macrocrm-dlya-zastrojschika-v-chyom-raznitsa-integratsij-s-plan7); [Kontur article](https://kontur.ru/articles/6263)
- An API Monster connector exists for MacroCRM. — [apimonster MacroCRM](https://apimonster.ru/connector/service/macrocrm/)
- One developer review reports leaving MacroCRM for Bitrix24 over lack of flexibility. — [crmindex reviews](https://crmindex.ru/products/macrocrm/reviews)

**1C**
- "1С:Девелопмент и управление недвижимостью" (v1.3 and v2) exists as a 1C-partner product. "1С:Риэлтор. Управление продажами недвижимости" covers primary and secondary sales. Search did not confirm a native chessboard, reservations or payment schedules in the 1C developer product. Visualisation is usually Profitbase on top. — [1C partner PDF](https://v8.1c.ru/upload/iblock/393/393bfd273bc91291194d0f82616af289.PDF); [1C:Риэлтор functional spec](https://solutions.1c.ru/upload/reestr/053/1ai82cb4a40oj27gr7ef4ny6q47d5tcr/Funktsionalnye-kharakteristiki-Rieltor.pdf)
- EstateCRM's "Корпорация" plan integrates with 1C for deals, payments and documents. — [toolfox EstateCRM](https://toolfox.ru/services/s/estatecrm)

**Bitrix24 developer solutions**
- The marketplace has industry solutions for developers (sales of new builds, "Sale" and "Sale with mortgage" pipelines) and chessboard apps. DomXML shows the chessboard and reservations inside the deal card. Ained Developer changes unit statuses dynamically as the deal moves. Plan7 offers an interactive apartment catalogue for the website plus Bitrix24. — [Bitrix24 developer collection](https://www.bitrix24.ru/apps/collection/19275292/); [DomXML app](https://www.bitrix24.ru/apps/app/samsusam.domxml/); [Ained Catalog](https://www.bitrix24.ru/apps/app/ained.ained_chess/); [Plan7 app](https://www.bitrix24.ru/apps/app/plan7.plan7_shakhmatka_novostroyki/); [CRM для застройщика app](https://www.bitrix24.ru/apps/app/karpov_i_partnery.crm_dlya_stroitelnoy_kompanii_zastroyshchika/)
- Bitrix24 global pricing is a flat fee per organisation with a user cap. Annual-billing figures commonly cited: Basic $49 (5 users), Standard $99 (50), Professional $199 (100), Enterprise from $399 (250). Monthly billing is about $69/$144/$289. A newer "Vibe+" tier is listed at $89/$199/$399/$799 (CostBench, Nov 2026). Sources conflict. — [Bitrix24 prices](https://www.bitrix24.com/prices/buy.php); [CostBench](https://www.costbench.com/software/crm/bitrix24/); [Capterra](https://www.capterra.com/p/113540/Bitrix24/pricing/)

**Other CIS**
- A Ukrainian vendor, G-PLUS, markets a "CRM for developers" (press release, not examined). — [Interfax-Ukraine](https://interfax.com.ua/news/press-release/870761-amp.html)

### Inferences
- Unitforma's verified inventory derived from drawings overlaps directly with Profitbase's and MacroCRM's chessboards. Their weakness is manual data entry, and Unitforma's differentiator is inventory generated from the drawings. In the CIS, the chessboard lives in a specialised inventory tool that syncs into Bitrix24 or amoCRM, which is the exact pattern Unitforma would follow.
- Intrum was not researched. No results came back on it.

### Gaps
- Profitbase API: no webhook or status docs read (developer.profitbase.ru was not indexed or fetched). Official current tariffs were not verified.
- Whether Profitbase or MacroCRM sell to Georgian developers, and in which currency or legal entity, was not found.

## 4. Georgia: which CRMs do Tbilisi developers use?

### Takeaway
Public evidence is thin. The strongest signals are FMG Soft's localised Georgian Odoo, marketed specifically to developers (apartment and parking management, contracts), and Bitrix24, through local partners and a Tbilisi job ad. No Georgian developer was found publicly naming its CRM vendor in a case study.

### Cited Findings
- FMG Soft (Tbilisi) built a localised Georgian Odoo for development companies, combining sales, facility, client and contract management with a single lead and client database and an apartment/parking-lot management module. Property Georgia calls it "a leader in digitalisation of development companies in Georgia". Read from the search snippet only, because the fetch was blocked. Article date not verified. — [Property Georgia: FMG SOFT](https://propertygeorgia.ge/en/media/news/1790-fmg-soft-leader-digitalisation-development-companies-georgia); [Odoo customer listing](https://www.odoo.com/customers/fmg-soft-llc-20134876)
- BSMGROUP in Tbilisi implements Bitrix24 in Georgia, including a booking platform with payment reminders and a Georgian/English/Russian/Ukrainian interface. — [BSMGROUP](https://en.bsmgroup.ge/services/bitrix24-danergva/)
- A Tbilisi CRM Manager job ad, attributed to Petra Group in the search snippet, requires recording leads, contacts, deals and communications in Bitrix24. Petra is believed to be a Tbilisi residential developer, but this was not verified. — [cv.ge job ad](https://www.cv.ge/en/announcement/480940/CRM-Manager)
- Tbilisi Hills Golf & Residences advertised a Client Relationship Manager role (CRM tool not confirmed from the snippet). — [cv.ge](https://www.cv.ge/announcement/410881)
- Russian-language directories list many CRM integrators in Tbilisi, mostly Bitrix24 and amoCRM partners. — [workspace.ru Tbilisi CRM](https://workspace.ru/tbilisi/crm/)

### Inferences
- Bitrix24 and amoCRM/Kommo are the likely incumbents among Tbilisi developers, given the Russian-speaking IT ecosystem, local partners and the job-ad evidence. Odoo via FMG Soft is a credible third. This is inference, and interviews with pilot developers are needed.

### Gaps
- No public statement from major Tbilisi developers (Archi, Next Group, Axis, m2, Dirsi, Alliance) on their CRM was found.

## 5. Visual chooser: built in or third party?

### Takeaway
Most back-office CRMs do not build the buyer-facing interactive chooser themselves. Spark partners with Planpoint. MacroCRM and Profitbase offer website chessboards or catalogues, which are grid or catalogue views, not true 3D or facade choosers. In the Bitrix24 and amoCRM ecosystems, Plan7, DomXML and Ained provide the website catalogue.

### Cited Findings
- Spark relies on Planpoint for interactive selectors. — [Spark partners](https://www.spark.re/partner-integrations)
- Profitbase sells a website "smart catalog" at about 15,000 ₽/month. DomoPlaner sells a "chessboard for website (any CRM)" at about 10,000 ₽/month. — [crmindex Profitbase](https://crmindex.ru/products/profitbase); [crmindex DomoPlaner](https://crmindex.ru/products/domoplaner)
- MacroCRM includes a website catalogue and chessboard, and Plan7 can render the frontend from MacroCRM data. — [Plan7 blog](https://spark.ru/startup/plan7/blog/336993/amocrm-i-macrocrm-dlya-zastrojschika-v-chyom-raznitsa-integratsij-s-plan7)
- In DACH, specialist agencies build 3D apartment finders separately from the CRM. — [Maverickframe](https://maverickframe.com/de/leistungen/interaktiver-wohnungsfinder/)

### Inferences
- The market structure is "CRM plus a separate chooser vendor synced by API". Unitforma can either compete as the chooser and inventory layer that syncs with CRMs, or partner with them.

### Gaps
- Whether Sell.Do or PropSpace ship a 3D or facade chooser was not verified.

## 6. Integration targets for Unitforma (Georgian market first)

### Takeaway
Integrate with Bitrix24 first (REST API plus webhooks and a marketplace app pattern already proven by Profitbase and DomXML connectors), then amoCRM/Kommo, then Odoo (the FMG Soft localisation). Consider a Profitbase-compatible inventory export or sync for developers who already use Profitbase. HubSpot and Salesforce matter for Western expansion, with Spark-style inventory partnerships later.

### Cited Findings
- Bitrix24 has an app marketplace (550+ apps) and a precedent for inventory connectors that sync units into deals. — [Bitrix24 real estate](https://www.bitrix24.eu/industry/real-estate-crm-software.php); [Profitbase connector](https://www.bitrix24.ru/apps/app/metod_tsifry.konnektor_profitbase/)
- amoCRM/Kommo has developer integrations (Profitbase for amoCRM, Plan7 for amoCRM). — [crmindex Profitbase](https://crmindex.ru/products/profitbase); [Plan7 blog](https://spark.ru/startup/plan7/blog/336993/amocrm-i-macrocrm-dlya-zastrojschika-v-chyom-raznitsa-integratsij-s-plan7)
- Odoo is used in Georgia via FMG Soft. — [Odoo customer listing](https://www.odoo.com/customers/fmg-soft-llc-20134876)
- For HubSpot, the recommended developer model is custom objects (units, reservations, contracts). — [clck.com.au](https://www.clck.com.au/blog/hubspot-property-development-inventory/)

### Inferences
- Suggested order: (1) push leads to Bitrix24 through an outgoing webhook or REST, with a sync of unit status and price from Bitrix24 deals back to Unitforma; (2) a Kommo/amoCRM lead push; (3) Odoo XML-RPC/JSON-RPC for FMG Soft clients; (4) generic outbound webhooks and Zapier/Make for everyone else. Lead push alone already replaces CSV export. Two-way unit-status sync needs a clear source-of-truth rule, because Profitbase-style CRMs assume they own the inventory.

### Gaps
- Bitrix24, Kommo and Odoo API specifics (rate limits, webhook events, custom entity support) were not fetched this session and need verification against their developer docs.
