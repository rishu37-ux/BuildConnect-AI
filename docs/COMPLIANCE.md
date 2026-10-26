# Data collection & compliance

BuildConnect AI collects the **business contact details of professionals**
(architects, structural engineers, contractors). Under India's Digital
Personal Data Protection Act, 2023 (DPDP Act), a person's name, mobile number
and email are personal data even when they are used for business. The
platform is built so that the dataset stays defensible. These are engineering
controls, not legal advice. Have counsel review your sources and your
outreach process before going live.

## What the scraper does and doesn't do

| Control | Implementation |
|---|---|
| **robots.txt** | Checked for every URL (`politeness.RobotsCache`); `Crawl-delay` is honoured. |
| **Rate limiting** | One request per domain every `BC_MIN_DELAY` seconds (default 2s). `429 Retry-After` pauses the whole domain. |
| **Identifiable bot** | `BC_USER_AGENT` should name your company and a contact URL/email. |
| **Proxy rotation** | Used for *reliability* only: failing egress proxies are put on exponential cooldown and traffic moves to healthy ones. |
| **CAPTCHAs / bot walls** | **Not solved or bypassed.** A challenge, `401/403/451`, or CAPTCHA wall stops crawling of that domain for the run, and it is reported under `blocked_domains` in the run summary. A site that challenges bots has said it doesn't consent to automated collection; use its API, ask for a data-sharing agreement, or review it manually. |
| **Discovery** | Uses official search APIs (Brave/SerpAPI), not scraping of search-engine pages. Aggregators and marketplaces (Justdial, IndiaMART, Sulekha…), social networks, news and government sites are excluded, so agents only visit firms' own websites. |
| **Scope** | The crawl stays on the seed domains, and only leads matching the target professions and states (and a confidence threshold) are kept. |
| **Provenance** | Every lead stores `source_url`, `source_domain`, `scrape_run_id`, `first_seen_at` and `last_seen_at`. |

## Choosing sources

Prefer sources where professionals **publish their own contact details for
the purpose of being contacted about work**:

* Firm websites (contact / team pages)
* Professional association member directories that permit it (check terms)
* Business listings that allow automated access in their terms or via an API

Avoid: social networks, sites whose terms forbid scraping, anything behind a
login, and any personal (non-business) data.

## Opt-out and erasure

* **Dashboard → "Opt-out request"** (admin/manager) takes a mobile number or
  email, deletes every matching lead, and adds a SHA-256 hash of the contact to
  `suppression_list`.
* Ingest checks the suppression list, so a suppressed contact is never
  re-added by a later scrape.
* Include an opt-out route (reply STOP / link) in every outreach message, and
  record those requests here.

## Access & audit

* Role-based access: `admin`, `manager`, `sales`, `viewer` (see
  `backend/src/middleware/auth.js`). Only admins and managers can export.
* Exports, edits, deletes, user changes and suppressions are written to `audit_log`.
* CSV exports neutralise spreadsheet formula injection.

## Outreach

Indian telemarketing is regulated by TRAI's TCCCPR 2018 (DND / NCPR). Check
numbers against the DND registry before calling or sending SMS. Use registered
headers and templates for bulk SMS and WhatsApp Business.
