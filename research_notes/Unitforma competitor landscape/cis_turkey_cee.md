# Regional competitors: CIS, Caucasus, Central Asia, Turkey, CEE (developer-sales platforms resembling Unitforma)

Research date: 2026-11-08. Method note: WebFetch was blocked by this session's network policy for most vendor hosts (profitbase.ru, clutch.co, 3destate.pl, eznewswire.com all failed DNS), so nearly every finding below comes from **search-engine snippets/summaries of the cited URL, not a full read of the page**. Treat figures as "reported by the cited page, not independently verified". Vendor self-claims are flagged as such. Re-verify pricing before using it externally; many prices come from third-party catalogues (crmindex.ru, a2is.ru, startpack.ru, 1cbit.kz) and may be stale.

## Q1. Who are the regional vendors, and what do they do? (Inventory creation, chooser, CRM, integrations, pricing, customers, countries)

### Takeaway
The region has three kinds of vendor. (a) **Russian developer-CRM/ERP SaaS** with a "шахматка" inventory grid and a site widget: Profitbase, MacroCRM, Domoplaner, Allio, Plan7, EstateCRM, 1C and Bitrix24 add-ons. (b) **Ukrainian and Kazakh developer CRMs plus selector agencies**: G-PLUS CRM, Smart Orange/SpinHouse+DevBase, Amanix Build. (c) **CEE/Turkish 3D-visualisation studios and developer CRMs**: Realpad, 3D Estate, Maverick Frame, ArchiCGI. Two classified-style marketplaces, Korter and DOM.RIA, sell listing and lead tools to developers. None of the vendors found builds the unit inventory automatically from CAD/BIM or PDF drawings with human review. In every case the inventory is entered or imported by staff, and the visual chooser is drawn by an agency or studio.

### Cited Findings

**Russia (the most mature cluster)**
- **Profitbase**: a "цифровая экосистема застройщика" that automates the client cycle "от первого обращения до передачи ключей" (from first contact to key handover) — [1cbit.kz reseller page](https://www.1cbit.kz/1csoft/profitbase-dlya-nedvizhimosti/). Platform launched 2016; "сотни застройщиков" (hundreds of developers) use its services. This appeared in a search summary; the exact page was not isolated, but the candidates are [retail.ru/rbc company profile](https://www.retail.ru/rbc/company/profitbase) and the [1cbit.kz reseller page](https://www.1cbit.kz/1csoft/profitbase-dlya-nedvizhimosti/). Mark as unverified.
- Profitbase price on the Bitrix24 marketplace: **2,900 RUB per user per month** for the CRM app — [Bitrix24 app: Profitbase для недвижимости](https://www.bitrix24.ru/apps/app/profitbase.crm/).
- Profitbase prices at the Kazakhstan reseller 1cbit.kz: CRM access **3,335 per user per month**, Smart Catalog **17,250 per month**. Currency and date are not stated; the page may show RUB — [1cbit.kz](https://www.1cbit.kz/1csoft/profitbase-dlya-nedvizhimosti/).
- Profitbase add-on modules under "Profitbase.ai": dynamic pricing, a competitor map and "расценка шахматки" (AI pricing of the chessboard) — [1cbit.kz](https://www.1cbit.kz/1csoft/profitbase-dlya-nedvizhimosti/). Profitbase.ai dynamic pricing and Profitbase Office (online apartment sales) won the Skolkovo "BuildUp" accelerator — [ComNews, 2025](https://www.comnews.ru/digital-economy/content/238602/2025-04-02/2025-w14/1012/eksperty-profitbase-ocenili-uroven-cifrovizacii-prodazh-developerov). The award was attributed from a search summary across ComNews items.
- Profitbase's site widget pulls the site plan (генплан) and the list of houses into the developer's website automatically. The site plan and units are first laid out inside Profitbase by staff or a partner agency — [workspace.ru case, KamaStroyInvest](https://workspace.ru/cases/kamastroyinvest-razrabotka-sayta-zastroyschika-s-vnedreniem-profitbase/). Apartment statuses, images, floors and entrance numbers are exported to the site automatically, and plan data is fetched by API — [ruward.ru case](https://ruward.ru/cases/7890/).
- Profitbase partner channel: realtor/agent portal. Developer "Порадом" onboarded 300 realtors through Profitbase — [ComNews 2024-12-18](https://www.comnews.ru/digital-economy/content/236932/2024-12-18/2024-w51/1012/dk-poradom-organizovala-rabotu-300-rieltorami-pomoschyu-profitbase).
- Third-party Bitrix24 connector for Profitbase: requires a separately purchased Profitbase account and API key. Sync runs daily by hand or every 15 minutes from the change log — [Bitrix24 app: Коннектор Profitbase](https://www.bitrix24.ru/apps/app/metod_tsifry.konnektor_profitbase/).
- A user on Habr Q&A calls Profitbase "совсем не дешевая штука" (not cheap at all) for drawing site plans together with Bitrix24 — [qna.habr.com/q/566249](https://qna.habr.com/q/566249).
- Profitbase and Planoplan jointly studied Kazakhstan developers' websites, which signals interest in the Kazakh market — [Kursiv.kz](https://kz.kursiv.media/?p=5480181).
- **MacroCRM / MACRO**: a Russian sales, marketing and inventory system for developers. MACRO's own presentation claims use at **200+ developers** — [MACRO presentation PDF, erzrf.ru](https://profi.erzrf.ru/upload/iblock/466/9kwyyjzdhhwefmiwvj27x1z01741gwpm/MACRO-Nigmatulin-TSifrovaya-evolyutsiya-developmenta.pdf). Catalogue price: "Базовый" tier **12,500 RUB per month for up to 5 users** — [a2is.ru MacroCRM](https://a2is.ru/catalog/programmy-dlya-stroitelstva-i-remonta/macro-crm) / [startpack.ru](https://startpack.ru/application/macrocrm). MACRO also sells a "MacroCatalog" product — [a2is.ru macrocatalog](https://a2is.ru/catalog/programmy-dlya-stroitelstva-i-remonta/macrocatalog). A Kazakh competitor's promotional post argues that MacroCRM's finance module is tied to Russian accounting standards — [dev.to (Amanix promo; biased)](https://dev.to/tech_insider_kz/the-first-native-crm-for-kazakhstan-property-developers-how-amanix-build-works-j99).
- **Plan7**: apartment-catalog and chessboard web service. It can pull areas, prices, statuses and plans from MacroCRM to build the site catalog and chessboard, and it is sold as a Bitrix24 app — [Bitrix24 app: Каталог квартир Plan7](https://www.bitrix24.ru/apps/app/plan7.plan7_shakhmatka_novostroyki/); [startpack publications](https://startpack.ru/@dev_sp_75261718857/publications).
- **Domoplaner**: CRM tiers DP free (1 user), DP light **15,000 RUB/mo**, DP pro **30,000 RUB/mo**, DP max **60,000 RUB/mo**, plus "Шахматка на сайт (для любой CRM)" (a site chessboard that works with any CRM) at **10,000 RUB/mo** — [crmindex.ru Domoplaner](https://crmindex.ru/products/domoplaner). A freelance case shows a residential-complex site with real-time availability from Domoplaner — [freelancehunt](https://freelancehunt.com/showcase/work/kvartira/2050463.html).
- **ALLIO**: describes itself as the "first source of data" on a developer's units, an apartment-accounting and sales ERP. Born in 2013 from exchanging chessboards between head office and sales. Automatic price management and amoCRM / Bitrix24 / 1C integrations arrived in 2018 (vendor's own article). Catalogue price **50,000/month** (currency and scope not stated) — [crmindex.ru ALLIO](https://crmindex.ru/products/allio); [App Store: Allio mobile](https://apps.apple.com/ru/app/allio-mobile/id1592123121).
- **EstateCRM**: 1C integration for deals, payments and documents on the "Корпорация" tier — [toolfox.ru EstateCRM](https://toolfox.ru/services/s/estatecrm). **iPROFi house** is another developer CRM — [crmindex.ru](https://crmindex.ru/products/iprofi).
- **Bitrix24 partner industry solutions**: e.g. "CRM для строительной компании" with an interactive apartment catalog, chessboard booking and 1C sync — [Bitrix24 partner case](https://www.bitrix24.ru/partners/case/21610618/); [Bitrix24 app: CRM для строительной компании застройщика](https://www.bitrix24.ru/apps/app/karpov_i_partnery.crm_dlya_stroitelnoy_kompanii_zastroyshchika/).
- **1C**: industry products include "1С:Девелопмент и управление недвижимостью 1.3" and "1С:Риэлтор. Управление продажами недвижимости" (functional description dated 2026). No native interactive chessboard was confirmed — [infostart 1C development solutions](https://infostart.ru/soft1c/otraslevye_resheniya/stroitelstvo_i_nedvizhimost/development_industry/); [1C:Риэлтор functional spec PDF](https://solutions.1c.ru/upload/reestr/053/1ai82cb4a40oj27gr7ef4ny6q47d5tcr/Funktsionalnye-kharakteristiki-Rieltor.pdf).
- **Planoplan**: positions itself as "a scalable platform for the production of 3D and VR content for mass housing" and has a developer-package page. No prices were visible — [planoplan.com/en/developer/details](https://planoplan.com/en/developer/details).

**Ukraine**
- **G-PLUS CRM (G-PLUS.SOLUTIONS)**: a Ukrainian developer CRM with a built-in interactive chessboard, integration with property sites, "3D-демонстрація ЖК" (3D presentation of the residential complex) and built-in telephony. It **"успішно працює на ринку Казахстану, Грузії, Туреччини та України"** (works successfully in Kazakhstan, Georgia, Turkey and Ukraine) — [Interfax-Ukraine press release](https://interfax.com.ua/news/press-release/870761-amp.html). A chat widget is included at no extra cost, along with messenger, social and Google Sheets integrations — [finance.ua (sponsored)](https://news.finance.ua/ua/g-plus-crm-suchasne-profesiyne-rishennya-dlya-ukrains-kyh-zabudovnykiv); [Forbes.ua, 2024-07-19](https://forbes.ua/innovations/sila-ukrainskikh-tekhnologiy-it-rishennya-vid-g-plussolutions-dopomagayut-zabudovnikam-zaroblyati-bilshe-yak-tse-pratsyue-19072024-22437). No official price was found. A freelancer quoted "10k" (currency unstated) to set it up — [freelancehunt](https://freelancehunt.com/en/project/nalashtuvannya-crm-g-plus/1502582.html).
- **Smart Orange (smarto.agency / smarto.com.ua; Kyiv, founded 2009)**: websites, the **SpinHouse** cloud 3D masterplan plus apartment chessboard (filter by floor, area, price and status; compare; 360° tours; personalised PDF), renders, "AI content" and **DevBase CRM**, "built from the same 3D model". It claims contracts with developers in **16 countries including Georgia since 2024** and gives a Georgian example, polosignature.ge. It also claims that developers who order its sites built ">52% of apartments in Kyiv" (2021 rating; self-reported) — [Clutch: smart-orange](https://clutch.co/profile/smart-orange); [Clutch: smartorange](https://clutch.co/profile/smartorange); [The Manifest](https://themanifest.com/company/smart-orange). Moldovan example: 3d.dmz.md — same sources. The search tool inferred that "Smarto" = Smart Orange from the domains. This is likely but unverified.
- **DOM.RIA** new-build packages for developers include a "CRM integration" option, a business cabinet and call tracking. There is a free tier for one new-build project at 0 UAH — [dom.ria.com newbuild packages](https://dom.ria.com/react/newbuild-packages/).
- LUN (lun.ua): no developer-tool information was found in this pass (gap).

**Kazakhstan / Central Asia**
- **Amanix Build**: a "first native CRM for Kazakhstan property developers". Hierarchy developer → complex → building → floor → apartment, with a colour-coded chessboard as its centrepiece and an open API for website lead submission. No price found; promotional source only — [dev.to](https://dev.to/tech_insider_kz/the-first-native-crm-for-kazakhstan-property-developers-how-amanix-build-works-j99).
- **Appartex**: Kazakh CRM for business centres, malls and developers that tracks buyers' payment discipline after the contract — [kapital.kz](https://kapital.kz/business/70911/kak-avtomatizirovat-arendu-kvartir-i-ofisov.html).
- **Creatio** (generic CRM) is used by Kazakhstan's "Estate Management Company" for sales automation — [Creatio KZ news](https://www.creatio.com/kz/business/news/66988).
- Profitbase is resold in Kazakhstan by 1C-Bitrix integrator 1cbit.kz — [1cbit.kz](https://www.1cbit.kz/1csoft/profitbase-dlya-nedvizhimosti/).

**Marketplace with developer tools across the region: Korter**
- Korter: "service for buying property directly from real estate developers in Azerbaijan, Georgia, Kazakhstan, Poland and Romania". Features include construction-progress photos, layouts and an interactive 3D map — [App Store listing](https://apps.apple.com/us/app/korter-property-apartments/id1425788411). HQ is reported as Estonia, founded 2016; the country count is reported as 10 in other sources (conflicting) — [bouncewatch](https://bouncewatch.com/company/korter); [business-review.eu](https://business-review.eu/?p=205783).
- Korter.ge has operated since at least 2019 ("All new residential buildings in Georgia only on Korter") — [finchannel 2019](https://finchannel.com/all-new-residential-buildings-in-georgia-only-on-korter/77524/b-schools-2/2019/09/). Other site-analysis pages give conflicting launch dates (gde.ge), so treat those as unreliable.
- Korter.ge lists **269 developments in Batumi, 36 in Kutaisi and 13 in Bakuriani** (snapshot from search, late 2026) — [Batumi](https://korter.ge/en/new-projects-in-batumi); [Kutaisi](https://korter.ge/en/new-projects-in-kutaisi); [Bakuriani](https://korter.ge/en/new-projects-in-bakuriani).
- Korter.ge launched analytics features, including an interactive property map and price-trend tracking — [Newsfile, Feb 2026](https://www.newsfilecorp.com/release/284018/Korter.ge-Launches-New-Analytics-Features-Including-Interactive-Property-Map-and-Price-Trend-Tracking). A March 2026 release describes tools combining construction timelines, price history and location data, with "AI to improve listing quality" — [EZ Newswire](https://www.eznewswire.com/newsroom/korter-georgia-residential-real-estate-transparency-construction-tracking).
- No Korter developer CRM, white-label chooser or developer API was found; Korter appears to be a lead-gen listing marketplace. A related Ukrainian-Polish startup raised $5M from Forum Capital — [Kyiv Post archive](https://archive.kyivpost.com/article/content/technology/ukrainian-polish-startup-attracts-5-million-investment-from-forum-capital-402233.html). It is unverified whether this is Korter.

**Georgia (local)**
- **FMG Soft**: Tbilisi Odoo partner (official 2024, Gold in its first year), described as "a leader in digitalisation of development companies in Georgia". It serves large and mid-size real-estate firms and offers an "FMG Community" app — [Property Georgia](https://propertygeorgia.ge/en/media/news/1790-fmg-soft-leader-digitalisation-development-companies-georgia); [Odoo customer story](https://www.odoo.com/blog/customer-reviews-6/fmg-soft-empowering-business-with-odoo-1716). It is not tied to a specific chessboard or chooser product.
- **Unitify**: a post-handover building OS (requests, billing, access, resident communications, AI tools), not sales. Present in Batumi (Ande Tower / Ande Group). It supports Georgian, Russian and English, planned a developer roadshow in Tbilisi and Batumi on May 28–31, 2026, and claims 10,000 management companies and 5M+ apartments — [unitify.com Georgia](https://unitify.com/smart-building/georgia); [Ande Group case](https://unitify.com/en/blog/how-ande-group-is-setting-a-new-standard-for-residential-projects-with-unitify); [roadshow blog](https://unitify.com/blog/unitify-goes-on-the-road-in-georgia-may-28-31). It is a possible partner or adjacent player rather than a direct competitor.
- Kommo (amoCRM international) has a case study of a US-run developer, Ruebush Group, operating in Georgia — [Kommo case](https://kommo.com/cases/crm-for-property-management-ruebush-group/).
- Makler.ge is a Georgian listings portal that claims "Georgia's most extensive real estate database" — [makler.ge about](https://makler.ge/en/about-us).
- Archi (Georgian developer) claims 19 years, 51 completed projects and 47,000+ residents — [metropolitan.realestate](https://metropolitan.realestate/tbilisi/grand-avenue-archi-tbilisi-georgia). The Tbilisi Gardens site features a scroll-driven 3D building with floor exploration (agency-built) — [DesignRush](https://www.designrush.com/best-design/tbilisi-gardens).

**Turkey**
- **Maverick Frame** (studio; pages in TR, PL, EN and other languages): its "daire seçici" (apartment selector) shows building → floor → apartment → finish package with live price and availability on the website or a sales-office touchscreen. The studio builds the renders, floor plans and selector itself from "one 3D model". It quotes a fixed price per project, and the developer supplies floor plans, unit list, price list and CRM details — [maverickframe.com/tr daire-secici](https://maverickframe.com/tr/hizmetler/daire-secici/); [EN service page](https://maverickframe.com/services/interactive-apartment-selector/); [roadmap PDF](https://maverickframe.com/lead-magnets/roadmap/en/interactive-apartment-selector.pdf).
- **Konutmatik**: Turkish "proje satış pazarlama sistemi" (project sales-marketing system) app — [App Store](https://apps.apple.com/us/app/id1268258114). Features were not verified.
- A vendor claims developers pay "50.000₺ τον χρόνο στο Sahibinden" (about 50,000 TRY per year) for portal listings. This is a competitor's marketing — [zunapro.com](https://www.zunapro.com/turkey/el/real-estate-website). Portal dependence (Sahibinden, Hepsiemlak, Emlakjet) is described as costly — [braverytechnology.com](https://braverytechnology.com/tr/?p=4647).
- No Turkish SaaS equivalent of Profitbase (a developer CRM with a chooser) was identified in this pass (gap).

**Central & Eastern Europe**
- **Realpad** (Prague, founded 2012): developer CRM, sales tablet app, customer portal, handover/defect management. Reported customer counts by date: >70 clients in 12 countries (2021), >100 (2022), 130+ and **150+ customers in 12 countries** (job posts). Local teams in Budapest, Lisbon and Belgrade; ~60% CZ/SK market share per a LinkedIn profile; expanding in Romania — [property-forum.eu](https://www.property-forum.eu/news/czech-proptech-brings-digital-solutions-to-residential-developers-in-romania/8196); [startupjobs.cz](https://www.startupjobs.cz/nabidka/80291/customer-success-manager-at-realpad); [LinkedIn R. Ptacek](https://cz.linkedin.com/in/romanptacek); [business-review.eu](https://business-review.eu/?p=213305).
- **3D Estate** (Mikołów, Poland): 3D walkthroughs, 360° panoramas and 3D plans **automatically generated from apartment cards (karty mieszkań)**, which lowers unit cost. Claims ~2,000 projects; licence fee per investment set in the order — [bank.pl](https://bank.pl/?p=399408); [3destate.pl/de](https://3destate.pl/de); [3destate.pl terms](https://www.3destate.pl/terms); [NAHB IBS press kit](https://www.buildersshow.com/assets/docs/ibs/pressKits/PK_44010_3DEstatepressrelase.pdf). It also sells an "interactive apartment search" — [3destate.pl/en/3d-real-estate](https://3destate.pl/en/3d-real-estate).
- **ArchiCGI** (visualisation studio): quotes **$8,000–$20,000 for a full interactive property platform with 50–200 units** — [archicgi.com](https://archicgi.com/interactive-real-estate-platform/).
- Polish portals rynekpierwotny.pl and tabelaofert.pl sell developer listing packages — [rynekpierwotny.pl/dla-dewelopera](https://rynekpierwotny.pl/dla-dewelopera/); [tabelaofert.pl](https://tabelaofert.pl/o-nas).
- **Getfloorplan** (AI 2D→3D floor plans, renders, tours; sells to developers): packages of about **$20–$69 per plan set**. Third-party listings conflict on exact prices — [G2 AI marketplace](https://ai.g2.com/marketplace/tools/getfloorplan); [LinkedIn](https://linkedin.com/company/getfloorplan); [toolbit.ai](https://www.toolbit.ai/ai-tool/getfloorplan).

### Inferences
- In this region the **CRM-plus-chessboard is commoditised**: there are many Russian and Ukrainian options at roughly 3–60k RUB per month. The **visual chooser** is mostly an agency deliverable priced per project: Smart Orange, Maverick Frame, ArchiCGI and 3D Estate.
- The closest analogues to Unitforma's combined offer (inventory + CRM-lite + branded chooser widget) are **Profitbase (Smart Catalog)**, **Smart Orange (SpinHouse + DevBase)** and **G-PLUS**. Only G-PLUS and Smart Orange show explicit Georgia claims.
- **Korter** is the most visible developer-facing digital platform in Georgia, but it is a listings marketplace. It is a lead channel to integrate with, a partner more than a head-on competitor.

### Gaps
- Official Profitbase, MacroCRM and Domoplaner pricing pages could not be fetched (host blocked), so catalogue prices may be outdated.
- No data on Korter's developer pricing or paid placement.
- LUN, RealtSoft, Intrum, "ReDIS", "Flatris", "Smartcat", Yandex/Avito new-build developer tools, Sahibinden Projeler, Inventi, Vizlab, Spaceflow and Romanian/Bulgarian vendors were not covered in this pass, for lack of tool budget and blocked fetches. ("Smartcat" is a translation platform; it is probably not relevant, but this is unverified.)

## Q2. Which generate the chooser automatically from CAD/BIM vs. manual polygon drawing by an agency?

### Takeaway
No regional vendor found generates the unit inventory or the clickable chooser automatically from DXF/IFC/PDF drawings. The pattern everywhere is to build the inventory by hand (or import a spreadsheet or 1C data) into the CRM, then have an agency model or draw the façade, site plan and floor polygons. The closest automation is 3D Estate's auto-generated 3D tours from apartment cards and Getfloorplan's AI 2D→3D plans, but both produce visuals, not inventory.

### Cited Findings
- Profitbase widget data (site plan, houses, statuses, plans) flows to the site automatically, but the site plan and layout are configured in Profitbase. Website integrators/agencies act as "official Profitbase partners" for implementation — [workspace.ru KamaStroyInvest](https://workspace.ru/cases/kamastroyinvest-razrabotka-sayta-zastroyschika-s-vnedreniem-profitbase/); [ruward.ru](https://ruward.ru/cases/7890/).
- A user asked about using Profitbase "для отрисовки генпланов" (to draw site plans), i.e. site plans are drawn — [qna.habr.com](https://qna.habr.com/q/566249).
- Maverick Frame: "3D render'ları, kat planlarını ve seçicinin kendisini biz hazırlıyoruz" (we prepare the 3D renders, floor plans and the selector ourselves). Every finish option needs its own render; inputs are floor plans, unit list, price list and CRM — [maverickframe.com/tr](https://maverickframe.com/tr/hizmetler/daire-secici/); [roadmap PDF](https://maverickframe.com/lead-magnets/roadmap/en/interactive-apartment-selector.pdf).
- Smart Orange: website, 3D selector, renders and CRM "built from the same 3D model" (agency-made) — [Clutch](https://clutch.co/profile/smart-orange).
- 3D Estate: 3D tours generated automatically from apartment cards (karty mieszkań) — [bank.pl](https://bank.pl/?p=399408).
- Custom one-off: a Telegram bot turns a vector PDF floor plan into an Excel quantity takeoff for a 97-apartment building in minutes instead of two weeks. It works best on vector PDFs and less well on scans. This is a construction-estimating use, not sales inventory — [workspace.ru case](https://workspace.ru/cases/telegram-bot-schitaet-vedomost-obemov-rabot-po-pdf-plana-etazha/).
- Research-level work: ML recognition of objects on PDF drawings, and conversion of listing photos to 2D plans — [workspace.ru](https://workspace.ru/cases/raspoznavanie-obektov-na-pdf-chertezhah-arhitektura-resheniya-i-prototip-na-python/); [ITMO paper](https://kmu.itmo.ru/file/download/application/50983).

### Inferences
- Unitforma's drawings-to-inventory pipeline (PDF/DXF/IFC → reviewed unit list → auto-generated chooser) appears **unmatched by any regional vendor found**. This is the clearest differentiator against Profitbase/MacroCRM and against the agencies. It is absence-of-evidence from a limited search; confirm by checking Profitbase, Smart Orange and Realpad docs directly.
- Agency-built choosers cost about $8k–20k per project (ArchiCGI), and Maverick Frame quotes per project. That sets a price anchor that Unitforma's automated chooser can undercut.

### Gaps
- Whether Smart Orange's "AI content", Profitbase's newer releases, or MACRO ingest IFC/ArchiCAD models directly is unknown.

## Q3. Which have AI features (auto floor-plan recognition, AI renders, chatbots)?

### Takeaway
Regional AI is mostly **pricing and analytics AI** (Profitbase.ai dynamic pricing and chessboard pricing), **marketplace listing-quality AI** (Korter.ge), **agency "AI content"** (Smart Orange) and **2D→3D plan AI** (Getfloorplan). No vendor found offers AI floor-plan recognition into inventory, an AI renovation/furnishing playground, or an MCP/assistant for buyers.

### Cited Findings
- Profitbase.ai: dynamic pricing, competitor map, "расценка шахматки" (AI pricing of the chessboard) — [1cbit.kz](https://www.1cbit.kz/1csoft/profitbase-dlya-nedvizhimosti/); Skolkovo BuildUp recognition — [ComNews 2025](https://www.comnews.ru/digital-economy/content/238602/2025-04-02/2025-w14/1012/eksperty-profitbase-ocenili-uroven-cifrovizacii-prodazh-developerov).
- Korter.ge uses AI "to improve listing quality" (March 2026 release) — [EZ Newswire](https://www.eznewswire.com/newsroom/korter-georgia-residential-real-estate-transparency-construction-tracking).
- Smart Orange markets "AI content" alongside its selector and CRM — [Clutch](https://clutch.co/profile/smart-orange).
- Getfloorplan: AI converts 2D plans or sketches into 2D/3D plans, renders and virtual tours, delivered within about 24 hours — [LinkedIn](https://linkedin.com/company/getfloorplan); [G2](https://ai.g2.com/marketplace/tools/getfloorplan).
- Unitify (Georgia) layers "AI tools" on building operations after handover — [unitify.com Georgia](https://unitify.com/smart-building/georgia).
- G-PLUS offers a chat widget, but it is a messaging channel; no AI is claimed — [finance.ua](https://news.finance.ua/ua/g-plus-crm-suchasne-profesiyne-rishennya-dlya-ukrains-kyh-zabudovnykiv).

### Inferences
- Unitforma's AI renders of plans, its renovation playground and its AI assistant/MCP server would be novel in the Georgian and regional developer-software market, based on what was found. Getfloorplan is the nearest substitute for AI plan renders and is cheap ($20–69 per plan), which caps what buyers will pay for that feature alone.

### Gaps
- No evidence was found for buyer-facing AI chatbots from Profitbase, MacroCRM or G-PLUS. The search was shallow, so absence is not proof.

## Q4. Pricing models and typical costs

### Takeaway
Russian SaaS is priced **per user per month** (CRM) plus a **flat monthly fee for the site chessboard or catalog**. Agencies charge a **fixed price per project**, about $8k–20k for a full platform. Marketplaces charge **per-project listing packages**, with free entry tiers. CEE 3D vendors use a **per-investment licence**.

### Cited Findings
| Vendor | Model | Price (as reported) | Source |
|---|---|---|---|
| Profitbase CRM (Bitrix24 app) | per user / month | 2,900 RUB | [Bitrix24](https://www.bitrix24.ru/apps/app/profitbase.crm/) |
| Profitbase CRM / Smart Catalog (KZ reseller) | per user / month; catalog per month | 3,335; 17,250 (currency unstated) | [1cbit.kz](https://www.1cbit.kz/1csoft/profitbase-dlya-nedvizhimosti/) |
| MacroCRM "Базовый" | per month, ≤5 users | 12,500 RUB | [a2is.ru](https://a2is.ru/catalog/programmy-dlya-stroitelstva-i-remonta/macro-crm) |
| Domoplaner | tiers per month | free / 15k / 30k / 60k RUB; site chessboard 10k RUB/mo | [crmindex.ru](https://crmindex.ru/products/domoplaner) |
| ALLIO | per month | 50,000 (currency unstated) | [crmindex.ru](https://crmindex.ru/products/allio) |
| G-PLUS | not public | integrator setup "10k" (unstated currency) | [freelancehunt](https://freelancehunt.com/en/project/nalashtuvannya-crm-g-plus/1502582.html) |
| DOM.RIA developer packages | per project package | free tier for 1 project (0 UAH) | [dom.ria.com](https://dom.ria.com/react/newbuild-packages/) |
| 3D Estate | licence fee per investment | not public | [3destate.pl terms](https://www.3destate.pl/terms) |
| Maverick Frame selector | fixed price per project | not public | [roadmap PDF](https://maverickframe.com/lead-magnets/roadmap/en/interactive-apartment-selector.pdf) |
| ArchiCGI interactive platform | per project | $8,000–$20,000 for 50–200 units | [archicgi.com](https://archicgi.com/interactive-real-estate-platform/) |
| Getfloorplan | per plan set | ~$20–$69 | [G2](https://ai.g2.com/marketplace/tools/getfloorplan) |
| Sahibinden (TR portal) | annual listing | ~50,000 TRY/yr (competitor claim) | [zunapro](https://www.zunapro.com/turkey/el/real-estate-website) |

- Average cost of CRM implementation and support in Tbilisi is listed as about 100,000–300,000 (currency unstated; Russian-language directory) — [workspace.ru Tbilisi CRM](https://workspace.ru/tbilisi/crm/).

### Inferences
- A Georgian mid-size developer pricing a Russian or Ukrainian stack would face roughly CRM $30–150 per user per month plus an agency chooser at about $8–20k per project. Unitforma can position as **one per-project or per-unit subscription that replaces the agency fee**.

### Gaps
- No verified GEL-denominated prices from any vendor in Georgia.

## Q5. Evidence of presence in Georgia (and Armenia, Azerbaijan, Kazakhstan); sanctions and geopolitics

### Takeaway
Confirmed or claimed Georgia presence: **Korter.ge** (marketplace, since about 2019, hundreds of projects listed), **G-PLUS CRM** (Ukrainian; claims Georgian developer clients), **Smart Orange** (Ukrainian agency; Georgian client polosignature.ge since 2024), **FMG Soft** (local Odoo integrator for developers) and **Unitify** (post-handover operations, Batumi). **No evidence was found of Profitbase, MacroCRM, Domoplaner or Allio clients in Georgia or Armenia.** Profitbase does have a Kazakhstan reseller and has published Kazakh market research. Korter covers Azerbaijan and Kazakhstan.

### Cited Findings
- G-PLUS works in Kazakhstan, Georgia, Turkey and Ukraine — [Interfax-Ukraine](https://interfax.com.ua/news/press-release/870761-amp.html); its users include "забудовники з Грузії, Туреччини, Казахстану" (developers from Georgia, Turkey and Kazakhstan) — [geoln.com](https://geoln.com/ua/ukraine-real-estate-market/ukrainian-it-soft-g-plus-crm).
- Smart Orange: Georgia among 16 countries since 2024; polosignature.ge example — [Clutch](https://clutch.co/profile/smartorange).
- Korter: Azerbaijan, Georgia, Kazakhstan, Poland, Romania — [App Store](https://apps.apple.com/us/app/korter-property-apartments/id1425788411); Georgian listing counts — [korter.ge Batumi](https://korter.ge/en/new-projects-in-batumi).
- FMG Soft: Odoo for Georgian development companies — [Property Georgia](https://propertygeorgia.ge/en/media/news/1790-fmg-soft-leader-digitalisation-development-companies-georgia).
- Unitify: Ande Tower, Batumi; Tbilisi/Batumi roadshow, May 2026 — [unitify.com](https://unitify.com/en/blog/how-ande-group-is-setting-a-new-standard-for-residential-projects-with-unitify).
- VRNET.IO (pre-construction 3D tours) has a review from a Georgian client — [Clutch review](https://clutch.co/go-to-review/vrnetio/432777).
- Profitbase in Kazakhstan: reseller 1cbit.kz — [1cbit.kz](https://www.1cbit.kz/1csoft/profitbase-dlya-nedvizhimosti/); joint study of Kazakh developer websites with Planoplan — [Kursiv](https://kz.kursiv.media/?p=5480181). Searches for Profitbase in Georgia, Armenia or Uzbekistan returned nothing.
- MacroCRM: no Georgia or Kazakhstan clients found. A Kazakh competitor claims its finance module is tied to Russian accounting — [dev.to (biased)](https://dev.to/tech_insider_kz/the-first-native-crm-for-kazakhstan-property-developers-how-amanix-build-works-j99).
- Kommo (amoCRM brand) is used by a developer operating in Georgia — [Kommo case](https://kommo.com/cases/crm-for-property-management-ruebush-group/).

### Inferences
- **Geopolitics (inference, not sourced in this pass):** Russian vendors (Profitbase, MacroCRM, Domoplaner, Allio, 1C) price in RUB, are built around Russian accounting, mortgage and escrow flows (e.g. a 1C dependency), and may face payment and data-residency friction in Georgia, plus reputational sensitivity among Georgian buyers. Ukrainian vendors (G-PLUS, Smart Orange) have taken the Georgian opening instead. Validate with a dedicated search on Russian SaaS sanctions and payments in Georgia and on Georgian personal-data law.
- The most direct threats in Tbilisi are likely **Ukrainian agency/CRM bundles (Smart Orange, G-PLUS)** and **local website agencies building one-off choosers**. Korter is a channel to integrate with, by pushing Unitforma inventory to Korter listings.

### Gaps
- No named Armenian or Azerbaijani developer-software vendors were identified.
- No Georgian-language search was performed. Local Georgian web agencies building choosers (e.g. for Archi, Tbilisi Gardens, Alliance, m2) were not catalogued.
- Sanctions and compliance facts for Russian SaaS in Georgia were not researched with sources.
- Session network restrictions blocked direct reads of profitbase.ru, clutch.co, 3destate.pl and eznewswire.com. To verify, allow those hosts and re-fetch.
